# Multi-Tenant Integration in Flask App

Hier sind die konkreten Änderungen für `Web/app.py`, um Multi-Tenant Funktionalität zu aktivieren.

## Änderung 1: Imports hinzufügen

**VORHER** (Zeile 1-60 in app.py):
```python
from flask import Flask, render_template, request, ...
from werkzeug.utils import secure_filename
# ... weitere imports
```

**NACHHER** (Zusätzliche Imports):
```python
# Multi-Tenant Imports
from tenant import get_tenant_context, require_tenant, get_tenant_db
from session_manager import create_redis_session_interface
from query_cache import get_cache_manager, cached_query, invalidate_cache
```

---

## Änderung 2: Redis Session Backend konfigurieren

**NACH** `app = Flask(...)` (ca. Zeile 65):

```python
app = Flask(__name__, static_folder='static')
app.logger.setLevel(logging.WARNING)
app.secret_key = cfg.SECRET_KEY

# ========== MULTI-TENANT KONFIGURATION ==========

# Aktiviere Redis Session Backend statt Filesystem
if os.getenv('INVENTAR_SESSION_BACKEND') == 'redis':
    try:
        app.session_interface = create_redis_session_interface(app)
        app.logger.info("Redis session backend enabled")
    except Exception as e:
        app.logger.warning(f"Redis session backend failed, using default: {e}")

# ================================================
```

---

## Änderung 3: Health Check Endpoint hinzufügen

**Neuer Route** (nach allen anderen Routes, vor `if __name__ == '__main__'`):

```python
@app.route('/health')
def health_check():
    """
    Health check endpoint für Nginx Load Balancer.
    Wird regelmäßig von Nginx aufgerufen (30s interval).
    
    Rückgabe: 200 OK wenn app bereit, sonst 503
    """
    try:
        # Check Database Connection
        from settings import MongoClient
        mongo = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        mongo.admin.command('ping')
        
        # Check Redis Connection (falls Redis Session aktiv)
        if os.getenv('INVENTAR_SESSION_BACKEND') == 'redis':
            cache_mgr = get_cache_manager()
            if cache_mgr and cache_mgr.redis:
                cache_mgr.redis.ping()
        
        return {'status': 'healthy'}, 200
    
    except Exception as e:
        app.logger.error(f"Health check failed: {e}")
        return {'status': 'unhealthy', 'error': str(e)}, 503
```

---

## Änderung 4: Tenant Context in bestehende Database-Calls

**WICHTIG**: Alle `MongoClient` Zugriffe müssen durch Tenant-Context gehen.

### Beispiel 1: Bestehender Code (VORHER)

```python
# VORHER: Direkter DB-Zugriff
@app.route('/items')
def get_items():
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]  # ← PROBLEM: Alle Tenants teilen sich die gleiche DB
    items = db['items'].find().to_list(100)
    return jsonify(items)
```

### Beispiel 1: Mit Tenant-Routing (NACHHER)

```python
# NACHHER: Tenant-Isolierte DB
@app.route('/items')
@require_tenant  # ← Decorator setzt Tenant Context
def get_items():
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    ctx = get_tenant_context()
    
    # Richtige Datenbank für diesen Tenant
    db = client[ctx.db_name]  # z.B. "inventar_schule1"
    
    items = db['items'].find().to_list(100)
    return jsonify(items)
```

### Oder kürzere Variante:

```python
@app.route('/items')
@require_tenant
def get_items():
    db = get_tenant_db(MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT))
    items = db['items'].find().to_list(100)
    return jsonify(items)
```

---

## Änderung 5: Query Caching für häufige Abfragen

**VORHER**:
```python
def load_user_profile(user_id):
    db = client[cfg.MONGODB_DB]
    # Direkter DB-Zugriff bei jedem Request
    return db['users'].find_one({'_id': ObjectId(user_id)})
```

**NACHHER**:
```python
@cached_query(category='user', ttl=7*24*3600)  # 7 Tage Cache
def load_user_profile(user_id):
    db = get_tenant_db(MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT))
    return db['users'].find_one({'_id': ObjectId(user_id)})
```

Nach Update muss Cache invalidiert werden:

```python
def update_user_profile(user_id, updates):
    db = get_tenant_db(MongoClient(...))
    db['users'].update_one({'_id': ObjectId(user_id)}, {'$set': updates})
    
    # Cache invalidieren nach Write
    ctx = get_tenant_context()
    invalidate_cache(ctx.tenant_id, 'user')
    
    return True
```

---

## Änderung 6: Debugging - Tenant-Info in Logs

**Logging Helper** (am besten in einem bestehenden Logging-Block):

```python
def log_with_tenant(level, message):
    """Helper um Tenant-ID in Logs zu erfassen."""
    ctx = get_tenant_context()
    tenant_id = ctx.tenant_id if ctx else 'unknown'
    prefixed_msg = f"[{tenant_id}] {message}"
    
    if level == 'error':
        app.logger.error(prefixed_msg)
    elif level == 'warning':
        app.logger.warning(prefixed_msg)
    elif level == 'info':
        app.logger.info(prefixed_msg)
    else:
        app.logger.debug(prefixed_msg)

# Nutzung:
log_with_tenant('info', 'User login successful')
# Output: "[schule1] User login successful"
```

---

## Änderung 7: Test-Routes (optional, für Debugging)

```python
@app.route('/debug/tenant')
def debug_tenant_info():
    """Debug-Endpoint: Zeigt aktuellen Tenant-Context."""
    ctx = get_tenant_context()
    cache_mgr = get_cache_manager()
    
    return {
        'tenant_id': ctx.tenant_id if ctx else None,
        'db_name': ctx.db_name if ctx else None,
        'subdomain': ctx.subdomain if ctx else None,
        'cache_enabled': cache_mgr is not None,
        'cache_stats': cache_mgr.get_stats(ctx.tenant_id) if ctx and cache_mgr else None,
        'request_host': request.host,
        'request_headers': dict(request.headers)
    }

@app.route('/debug/cache/<action>', methods=['POST'])
def debug_cache_control(action):
    """Debug-Endpoint: Cache Kontrolle."""
    ctx = get_tenant_context()
    cache_mgr = get_cache_manager()
    
    if action == 'clear':
        if cache_mgr:
            cache_mgr.invalidate_tenant(ctx.tenant_id)
            return {'status': 'Cache cleared for tenant', 'tenant': ctx.tenant_id}
    
    return {'status': 'unknown action'}, 400
```

---

## Änderung 8: Umgebungsvariablen (.env)

```bash
# Multi-Tenant Konfiguration
INVENTAR_MULTITENANT_ENABLED=true
INVENTAR_SESSION_BACKEND=redis
INVENTAR_REDIS_HOST=redis
INVENTAR_REDIS_PORT=6379
INVENTAR_REDIS_DB=0

# Query Caching
INVENTAR_QUERY_CACHE_ENABLED=true
INVENTAR_CACHE_DB=1

# Logging (auf WARNING reduzieren)
INVENTAR_LOG_LEVEL=WARNING

# Performance
INVENTAR_WORKERS=4
INVENTAR_WORKER_CLASS=gevent
INVENTAR_WORKER_CONNECTIONS=100
```

---

## Migration-Strategie

### Phase 1: Compatibility Mode (Keine Breaking Changes)

- ✓ Beide Mode laufen gleichzeitig (Single + Multi)
- ✓ Alte Routes funktionieren ohne Änderung
- ✓ Neue Routes können `@require_tenant` nutzen
- ✓ Session-Fallback wenn Redis nicht verfügbar

### Phase 2: Graduelle Migration

1. Starten mit SINGLE Instance + Single Database
   ```bash
   docker-compose -f docker-compose-multitenant.yml up -d --scale app=1
   ```

2. Redis Session Backend aktivieren
   ```bash
   INVENTAR_SESSION_BACKEND=redis
   ```

3. Einzelne Routes mit `@require_tenant` decorator markieren

4. Query Caching für häufige Abfragen hinzufügen

5. Testing mit Multi-Subdomain (test1.local, test2.local)

6. Full Multi-Tenant in Production
   ```bash
   docker-compose -f docker-compose-multitenant.yml up -d --scale app=5
   ```

---

## Performance-Vergleich

### Single Instance (Vorher)
```
1 App Instance
- Memory: 200MB
- Startup: 8s
- Max Users: ~50 (gleichzeitig)
- DB Load: 100%
- Sessions: Filesystem I/O
```

### Multi-Instance (Nachher)
```
3 App Instances
- Memory: 3 × 100MB = 300MB (gesamt)
- Startup: 3s pro Instance
- Max Users: ~150 (gleichzeitig, 50 pro instance)
- DB Load: 30% (durch Caching)
- Sessions: Redis (keine I/O)
```

---

## Checkliste für Deployment

- [ ] Docker-compose-multitenant.yml durchgelesen
- [ ] Tenant-Module (tenant.py, session_manager.py, query_cache.py) im Web/ Ordner
- [ ] app.py mit Multi-Tenant Imports aktualisiert
- [ ] Redis Session Backend aktiviert (INVENTAR_SESSION_BACKEND=redis)
- [ ] Health Check Endpoint implementiert
- [ ] Nginx multitenant.conf konfiguriert
- [ ] SSL Wildcard Zertifikat erstellt
- [ ] DNS Wildcard Record konfiguriert (*.example.com)
- [ ] First Tenant als test registriert
- [ ] Health Checks funktionieren: curl https://test.example.com/health
- [ ] Cache Stats verfügbar: curl https://test.example.com/debug/tenant
- [ ] Load Test mit 2-3 Tenants durchgeführt
- [ ] Monitoring Setup (Docker Stats, Nginx Logs)

---

## Support & Debugging

**Fragen?**

1. Logs prüfen: `docker-compose -f docker-compose-multitenant.yml logs -f app`
2. Tenant-Info prüfen: `curl https://your-tenant.com/debug/tenant`
3. Cache Stats: `curl https://your-tenant.com/debug/cache-stats`
4. Redis Stats: `docker exec inventarsystem-redis redis-cli info stats`

**Häufige Fehler:**

- `X-Tenant-ID Header missing` → Nginx nutzt alte Konfiguration
- `Redis connection refused` → Redis Container nicht gestartet
- `Database not found` → Tenant nicht registriert (auto-create bei erstem Request)
- `Out of memory` → Memory Limit zu niedrig oder zu viele Instanzen

