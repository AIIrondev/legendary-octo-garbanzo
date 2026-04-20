# Multi-Tenant Python Management API

This document explains how the multi-tenant architecture isolates data within Python, what the return values are, and how developers can build internal administrative scripts using native Python instead of the Docker CLI. 

## 1. Architectural Concept

In the system, each "tenant" is essentially a dedicated MongoDB database identified by a dynamically generated string based on a subdomain or header (`inventar_<tenant_id>`). 
App containers share a connection pool using `pymongo.MongoClient`, and requests are routed to specific databases dynamically based on the current Flask `g.tenant_context`.

All MongoDB administrative tasks (creating tenants, restarting apps, fetching lists) are done via standard MongoDB Python drivers because the core multi-tenancy happens at the **database level**.

## 2. Managing Tenants via Python

If you want to perform multi-tenant administrative operations without traversing through `manage-tenant.sh`, you can execute native Python scripts connecting to the system's `MongoClient`.

### Basic Connection Boilerplate
Whenever automating an administrative task in Python, you simply need to connect to MongoDB using the properties defined in `settings.py`.

```python
import sys
import os

# Append Web folder so we can access configuration
sys.path.insert(0, '/app/Web')
import settings
from pymongo import MongoClient

# Establish connection pooling
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
```

### A. Adding a New Tenant (Database Initialization)
A new tenant database isn’t provisioned until the first actual data insert happens. We trigger this manually by creating an `admin` user for them.

**Operation:**
```python
def create_tenant(tenant_id, admin_password="hashed_password_here"):
    db_name = f"{settings.MONGODB_DB}_{tenant_id}"
    db = client[db_name]
    
    # MongoDB creates the DB automatically on first insert
    result = db.users.insert_one({
        'username': 'admin',
        'password': admin_password,
        'role': 'admin'
    })
    return result.inserted_id # Returns the BSON ObjectId of the new user
```

### B. List Active Tenants
To find out how many isolated tenants have active databases, you query the raw `MongoClient` for all databases and search for your configured MongoDB prefix (default: `inventar_`).

**Operation:**
```python
def list_tenants():
    prefix = f"{settings.MONGODB_DB}_"
    
    # Returns a Python list of string database names
    all_dbs = client.list_database_names() 
    
    # Filter and strip the prefix to return just the tenant_ids
    active_tenants = [d.replace(prefix, "") for d in all_dbs if d.startswith(prefix)]
    
    return active_tenants # e.g., ['schule1', 'schule2', 'test']
```

### C. Soft-Restarting a Tenant (Invalidating Sessions)
"Restarting" a single tenant means signing out all of their users and forcing an application refresh. Because Session data is coupled to the tenant database, dropping their `sessions` collection achieves an instant sign-out.

**Operation:**
```python
def restart_tenant(tenant_id):
    db_name = f"{settings.MONGODB_DB}_{tenant_id}"
    db = client[db_name]
    
    # Drops the collection. All active user cookies immediately become invalid.
    result = db.sessions.drop() 
    
    return result # Returns None. Raises PyMongoError if connection fails.
```

### D. Removing a Tenant Completely (Wipe Data)
If a tenant is removed from the service or their lease expires, you can permanently obliterate their data container footprint.

**Operation:**
```python
def remove_tenant(tenant_id):
    db_name = f"{settings.MONGODB_DB}_{tenant_id}"
    
    # Erases the isolated database. Can't be undone.
    client.drop_database(db_name) 
    
    return True # Returns True. Raises PyMongoError if connection fails.
```

## 3. Resolving Context Inside Flask (app.py)

If you are building custom application endpoints inside `Web/app.py`, you shouldn't use the direct MongoDB `client` manually. Instead, you rely on the built-in Flask context manager (`Web/tenant.py`) to give you the correct isolated scope.

### The `get_tenant_db()` function
Every route must use `get_tenant_db(client)` to ensure users can only ever access their own school/domain's database.

```python
from pymongo import MongoClient
import settings
from tenant import get_tenant_db

# Example Route
@app.route('/api/items')
def get_items():
    # 1. Establish/reuse pooling connection
    client = MongoClient(settings.MONGODB_HOST, settings.MONGODB_PORT)
    
    # 2. Get the dynamically routed DB for THIS user 
    # (Based on Nginx Subdomain or X-Tenant-Id header)
    db = get_tenant_db(client) 
    
    # 3. Runs query solely on `inventar_schule1.items`
    items = list(db.items.find())
    
    return items # List of BSON Dictionaries
```

**What it returns internally:**
The `get_tenant_db` function queries `g.tenant_context` inside Flask, calculates the database name from the subdomain, and returns a live `pymongo.database.Database` object. 

This ensures that scaling is extremely cheap on resources because 1 Application Container connects to 100 separate Tenant Databases using just 1 shared `MongoClient` pool.

---


1. Das Kernkonzept: Wie funktioniert dein Multi-Tenant-System?
Du betreibst keinen separaten Docker-Container für jeden einzelnen Kunden (Tenant). Das wäre extrem speicherintensiv und schwer zu warten. Stattdessen nutzt du ein „Database-per-Tenant“ & „Shared-App“ Modell:

Der App-Pool: In Docker laufen z.B. 3 identische app-Container, die sich die Arbeit teilen (Load-Balancing).
Das Routing (Nginx): Ein Nutzer ruft https://schule1.deinedomain.de auf. Nginx leitet die Anfrage an irgendeinen der freien app-Container weiter.
Die Tenant-Weiche (Python): Deine Python-App greift die Subdomain (schule1) aus der URL ab und lenkt alle Datenbankabfragen dieses Nutzers ausschließlich auf die MongoDB-Datenbank inventar_schule1.
Das Ergebnis: 100% isolierte Daten für jeden Mandanten, aber maximale Ressourceneffizienz auf dem Server.
2. Der Praxis-Ablauf: Einen neuen Kunden anlegen
Um eine neue Schule oder einen neuen Kunden mit eigener Subdomain an den Start zu bringen, brauchst du nur zwei Schritte:

DNS einrichten (Domain-Ebene):
Erstelle bei deinem Domain-Provider einen A-Record oder CNAME für die Subdomain (z.B. schule1), der auf die IP deines Servers zeigt.

Pro-Tipp: Richte dir einen Wildcard-Record (*.deinedomain.de) ein. Dann musst du bei neuen Kunden nie wieder in die DNS-Einstellungen gehen. Jede fiktive Subdomain zeigt dann automatisch auf deinen Server!
Datenbank initialisieren (Server-Ebene):
Führe deinen Wrapper auf dem Server aus, um dem Kunden eine Datenbank und einen initialen Admin-Nutzer zu generieren:

Das System ist nun für diesen Kunden unter schule1.deinedomain.de voll einsatzbereit.

3. Performance anpassen (Skalieren statt Neustarten)
Wenn du plötzlich 20 neue Kunden hast und der Server langsamer wird, musst du keine neuen Instanzen für genau diese Kunden bauen. Du erhöhst einfach die allgemeine Arbeitskraft deines Docker-Compose-Netzwerks:

Nginx bemerkt sofort, dass es nun 5 statt vorher z.B. 2 Container gibt, und verteilt die Last aller aktiven Subdomains dynamisch auf alle 5 Container. Es gibt dabei keine Downtime.

4. Nützliche Zusatz-Infos & Pro-Tipps
Zero-Downtime Soft-Restarts (Session Invalidation):
Manchmal hängt ein Kunde fest oder du hast configs geändert. Anstatt den ganzen Server (und alle Kunden) neu zu starten, nutzt du .run-tenant-cmd.sh restart-tenant schule1. Das leert nur den Redis-Cache und die Sessions dieses einen Kunden. Seine Nutzer müssen sich neu einloggen, alle anderen Mandanten merken davon nichts.
Datensicherheit / Backups:
Da jeder Tenant eine eigene Datenbank hat (inventar_schule1, inventar_schule2), kannst du im Fall eines Datenverlusts (z.B. ein Lehrer löscht versehentlich das halbe Inventar) das Backup nur für diesen einen Kunden wiederherstellen (mongorestore --db inventar_schule1 ...), ohne die Bestandsdaten der anderen 50 Schulen zu überschreiben.
SSL-Zertifikate:
Damit HTTPS für alle Subdomains automatisch funktioniert, generiere beim Setup unbedingt ein Wildcard-Zertifikat via Let's Encrypt (z.B. certbot certonly --manual -d "*.deinedomain.de"). Sonst zeigt der Browser bei einem neu angelegten Tenant eine Sicherheitswarnung, bis du das Zertifikat manuell erneuerst.
Kostenersparnis:
Da alle Container geteilt werden, kannst du auf einem Standard 4GB RAM / 2 vCPU VPS (ca. 5-10 Euro im Monat) problemlos 10-20 verschiedene Schulen parallel hosten, was dieses Architekturmodell extrem skalierbar und günstig macht.
