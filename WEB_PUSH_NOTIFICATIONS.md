# Web Push Notifications für Inventarsystem

## Überblick

Web Push Notifications ermöglichen es, Benutzer über wichtige Ereignisse in Echtzeit zu benachrichtigen, auch wenn sie die Anwendung nicht aktiv nutzen. Diese Implementierung nutzt:

- **Service Workers** für Hintergrundprozesse und Offline-Unterstützung
- **Web Push API** für Benachrichtigungen auf Desktop und Mobil
- **MongoDB** zur Speicherung von Subscriptions
- **VAPID-Authentifizierung** für sichere Push-Kommunikation

## Architektur

```
┌─────────────────────────────────────────────────────┐
│  Browser / Client-Side                              │
├─────────────────────────────────────────────────────┤
│  • Service Worker (static/service-worker.js)        │
│  • Push Notification Manager (js/push-notifications) │
│  • Web App Manifest (manifest.json)                 │
└─────────────────────────────────────────────────────┘
           ↕ (Push Subscriptions / Notifications)
┌─────────────────────────────────────────────────────┐
│  Server / Backend                                   │
├─────────────────────────────────────────────────────┤
│  • Flask API Endpoints (/api/push/*)                │
│  • Push Notification Manager (push_notifications.py)│
│  • MongoDB Collections (push_subscriptions)         │
│  • VAPID Key Management                             │
└─────────────────────────────────────────────────────┘
           ↕ (VAPID-signed push messages)
┌─────────────────────────────────────────────────────┐
│  Push Service (Firebase, Web Push Service)          │
├─────────────────────────────────────────────────────┤
│  • Stores subscriptions                             │
│  • Delivers push messages to browsers               │
└─────────────────────────────────────────────────────┘
```

## Setup & Konfiguration

### 1. VAPID-Schlüssel generieren

VAPID-Schlüssel sind erforderlich für die Authentifizierung mit dem Push-Dienst:

```bash
cd /path/to/Inventarsystem
bash generate-vapid-keys.sh
```

Dies erzeugt ein Schlüsselpaar. **Speichern Sie den Private Key sicher!**

Beispielausgabe:
```
PUBLIC KEY (share with browsers):
BBxyz...xyz

PRIVATE KEY (keep secret!):
AAabc...abc
```

### 2. Umgebungsvariablen setzen

Speichern Sie die Schlüssel als Umgebungsvariablen:

```bash
export VAPID_PUBLIC_KEY="BBxyz...xyz"
export VAPID_PRIVATE_KEY="AAabc...abc"
export VAPID_SUBJECT="mailto:admin@inventarsystem.local"
```

Für Docker:
```bash
# In .env oder docker-compose.yml
VAPID_PUBLIC_KEY=BBxyz...xyz
VAPID_PRIVATE_KEY=AAabc...abc
VAPID_SUBJECT=mailto:admin@inventarsystem.local
```

### 3. Abhängigkeiten installieren

```bash
pip install -r requirements.txt
# oder
pip install pywebpush
```

### 4. MongoDB Collection initialisieren

Die `push_subscriptions` Collection wird automatisch erstellt beim ersten Speichern einer Subscription. Indizes werden automatisch erstellt durch:

```python
from Web.push_notifications import ensure_push_subscriptions_collection
ensure_push_subscriptions_collection()
```

## API Endpoints

### `POST /api/push/subscribe`

Speichert eine Notification Subscription des Benutzers.

**Request:**
```json
{
    "subscription": {
        "endpoint": "https://fcm.googleapis.com/fcm/send/...",
        "keys": {
            "p256dh": "BCOA...",
            "auth": "kXA..."
        }
    }
}
```

**Response:**
```json
{
    "success": true,
    "message": "Successfully subscribed to push notifications"
}
```

---

### `POST /api/push/unsubscribe`

Deaktiviert eine Notification Subscription.

**Request:**
```json
{
    "endpoint": "https://fcm.googleapis.com/fcm/send/..."
}
```

**Response:**
```json
{
    "success": true,
    "message": "Successfully unsubscribed from push notifications"
}
```

---

### `GET /api/push/subscriptions`

Listet alle aktiven Subscriptions des aktuellen Benutzers auf.

**Response:**
```json
{
    "success": true,
    "count": 2,
    "subscriptions": [
        {
            "id": "507f1f77bcf86cd799439011",
            "endpoint": "https://...",
            "created_at": "2026-04-10T14:30:00",
            "last_used": "2026-04-10T15:45:00",
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)..."
        }
    ]
}
```

---

### `GET /api/push/vapid-key`

Ruft den öffentlichen VAPID-Schlüssel ab (erforderlich für Browser).

**Response:**
```json
{
    "success": true,
    "vapid_key": "BBxyz...xyz"
}
```

---

### `POST /api/push/test` (Admin only)

Sendet eine Test-Benachrichtigung.

**Request:**
```json
{
    "target_user": "username"  // optional, default: current user
}
```

**Response:**
```json
{
    "success": true,
    "message": "Test push sent to 2 subscription(s)"
}
```

## Frontend Integration

### Aktivierung in Settings

Fügen Sie einen Container in Ihre Einstellungsseite ein:

```html
<div id="push-notification-settings"></div>

<script src="{{ url_for('static', filename='js/push-notifications.js') }}"></script>
<script>
    document.addEventListener('DOMContentLoaded', function() {
        showPushNotificationSettings();
    });
</script>
```

Dies zeigt einen Button und Subscription-Status an.

### Manuelle Steuerung

```javascript
// Initialisieren
await pushNotificationManager.init();

// Benachrichtigungen aktivieren
await pushNotificationManager.subscribe();

// Benachrichtigungen deaktivieren
await pushNotificationManager.unsubscribe();

// Status prüfen
const isSubscribed = await pushNotificationManager.isSubscribed();

// Test-Benachrichtigung senden (Admin)
await pushNotificationManager.sendTestNotification();
```

## Backend Integration

### Benachrichtigungen versenden

```python
from Web import push_notifications as pn

# Benachrichtigung an einen Benutzer
pn.send_push_notification(
    'username',
    'Titel',
    'Nachricht',
    url='/my_borrowed_items',
    reference={'item_id': '123', 'type': 'borrowing'}
)

# Benachrichtigung an alle Admins
pn.send_push_to_all_admins(
    'Admin Alert',
    'Wichtiges Ereignis',
    url='/main_admin'
)
```

### Integration mit Notification-System

Benachrichtigungen werden automatisch über Push versendet, wenn erstellt:

```python
# In app.py
_create_notification(
    db,
    audience='user',
    notif_type='borrowing_activated',
    title='Ausleihung aktiviert',
    message='Ihre geplante Ausleihung ist jetzt aktiv',
    target_user='john_doe',
    reference={'url': '/my_borrowed_items', 'item_id': '123'}
)
# → Schreibt in DB + sendet Push-Benachrichtigung
```

## MongoDB Schema

### Collection: `push_subscriptions`

```json
{
    "_id": ObjectId("..."),
    "Username": "john_doe",
    "Endpoint": "https://fcm.googleapis.com/fcm/send/...",
    "Keys": {
        "p256dh": "BCOA...",
        "auth": "kXA..."
    },
    "SubscriptionHash": "abc123def456...",
    "IsActive": true,
    "CreatedAt": ISODate("2026-04-10T14:30:00Z"),
    "LastUsed": ISODate("2026-04-10T15:45:00Z"),
    "UserAgent": "Mozilla/5.0..."
}
```

**Indizes:**
- `Username` - Schnelle Abfrage nach Benutzer
- `{Username: 1, IsActive: 1}` - Abfrage aktiver Subscriptions
- `CreatedAt` - Zeitbasierte Bereinigung
- `SubscriptionHash` - Eindeutigkeit, Duplikat-Verhinderung

## Service Worker

### Funktionen

Die Service Worker (`static/service-worker.js`) behandelt:

1. **Push Events** - Empfängt und zeigt Benachrichtigungen an
2. **Click Handler** - Öffnet relevante URLs bei Benachrichtigungs-Klick
3. **Offline Caching** - Speichert statische Assets offline
4. **Background Sync** - Synchronisiert Daten im Hintergrund
5. **Installation** - Installiert sich selbst und lädt Cache vor

### Push-Payload-Format

```json
{
    "title": "Ausleihung aktiviert",
    "body": "Ihre geplante Ausleihung ist jetzt aktiv",
    "icon": "/static/img/logo-192x192.png",
    "badge": "/static/img/badge-72x72.png",
    "tag": "notification-borrowing_activated",
    "url": "/my_borrowed_items",
    "reference": {
        "item_id": "123",
        "type": "borrowing"
    }
}
```

## Troubleshooting

### Benachrichtigungen werden nicht empfangen

1. **VAPID-Schlüssel nicht gesetzt**
   ```bash
   # Überprüfen
   curl http://localhost:5000/api/push/vapid-key
   # Sollte VAPID_PUBLIC_KEY zurückgeben, nicht "nicht konfiguriert"
   ```

2. **Service Worker nicht registriert**
   - Browser DevTools → Application → Service Workers
   - Sollte "activated and running" anzeigen
   - Überprüfen Sie Console auf Fehler

3. **Notification Permission verweigert**
   - Browser-Einstellungen überprüfen
   - Site-Benachrichtigungsberechtigungen zurücksetzen
   - `chrome://settings/content/notifications` (Chrome)

4. **No active subscriptions**
   ```bash
   # MongoDB überprüfen
   db.push_subscriptions.find({Username: "username"})
   # Sollte aktive Subscriptions anzeigen
   ```

### Debug-Befehle

```bash
# Alle Subscriptions anzeigen
docker exec inventarsystem-mongodb mongosh --eval \
  'db.push_subscriptions.find({}).pretty()' Inventarsystem

# Test-Push senden
curl -X POST http://localhost:5000/api/push/test \
  -H "Content-Type: application/json" \
  -c cookies.txt -b cookies.txt

# Logs überprüfen
docker logs inventarsystem-app | grep -i "push\|notification"
```

## Browser-Unterstützung

| Browser | Desktop | Mobile | Service Worker | Push API |
|---------|---------|--------|-----------------|----------|
| Chrome | ✅ | ✅ | ✅ | ✅ |
| Firefox | ✅ | ✅ | ✅ | ✅ |
| Safari | ⚠️ | ✅ | ⚠️ | ⚠️ |
| Edge | ✅ | ✅ | ✅ | ✅ |

**Safari-Hinweis:** Verwendet Web Push über APNs mit Einschränkungen.

## Best Practices

### 1. Notification Häufigkeit
- Nicht mehr als 1 Benachrichtigung pro Minute pro Benutzer
- Sammelns Sie verwandte Events

### 2. Payload-Größe
- Halten Sie Nachrichten kurz (<100 Zeichen)
- Verwenden Sie `reference` für Kontext, nicht `body`

### 3. Sicherheit
- **Private Key**: Niemals in Code commiten!
- **Secrets**: Nur als Umgebungsvariablen speichern
- **Validate**: Server-seitig alle Subscription-Daten validieren

### 4. Datenschutz
- Dokumentieren Sie Push-Sammlung (DSGVO)
- Bieten Sie einfache Opt-out-Möglichkeit
- Speichern Sie keine PII in Push-Nachrichten

### 5. Wartung

Stale Subscriptions automatisch bereinigen:

```python
# In Scheduler oder Cron-Job
from Web.push_notifications import cleanup_inactive_subscriptions
cleanup_inactive_subscriptions()  # Entfernt inaktive Subs älter als 30 Tage
```

## Performance-Tipps

1. **Batch-Sends**: Senden Sie mehrere Pushes in einem Query
2. **Async**: Verwenden Sie Background Tasks für Push-Sending
3. **Redis**: Nutzen Sie Cache für häufig angeforderte VAPID-Keys
4. **Indexes**: MongoDB-Indexes auf `Username`, `IsActive` sollten vorhanden sein

## Zukünftige Erweiterungen

- [ ] Action Buttons in Benachrichtigungen (Approve/Deny)
- [ ] Benachrichtigungs-Kategorien und Gruppierung
- [ ] Rich-Media-Unterstützung (Bilder, Video)
- [ ] Scheduled Notifications
- [ ] Analytics & Delivery Tracking

---

**Version:** 1.0 (Inventarsystem v0.5+)
**Letzte Aktualisierung:** April 2026
