# Fehlersuche: Geplante Ausleihen werden nicht automatisch aktiviert

## 🔍 Mögliche Ursachen

### 1. **Termin wurde für falsches Datum erstellt**
Die meisten Probleme entstehen, weil der Termin für ein **falsches Datum** (z.B. morgen statt heute) erstellt wurde.

### 2. **Scheduler läuft nicht**
Der automatische Scheduler kann deaktiviert sein oder nicht starten.

### 3. **Zeitzonen-Problem**
Die Startzeit kann in einer anderen Zeitzone gespeichert sein als erwartet.

---

## ✅ SOFORT-FIX: Manuell aktivieren

Falls du eine geplante Ausleihe sofort aktivieren möchtest, nutze diesen Befehl auf dem Server:

```bash
docker exec inventarsystem-mongodb mongosh --eval "
db.ausleihungen.updateOne(
  {_id: ObjectId('BOOKING_ID_HIER')},
  {\$set: {Status: 'active', LastUpdated: new Date()}}
)" Inventarsystem
```

Ersetze `BOOKING_ID_HIER` mit der ID deiner Ausleihe.

---

## 🔧 DEBUG: Alle geplanten Ausleihen anschauen

Führe auf deinem Server aus:

```bash
docker exec inventarsystem-mongodb mongosh --eval "
db.ausleihungen.find({Status: 'planned'}).pretty()
" Inventarsystem
```

Das zeigt dir:
- **Start**: Das gespeicherte Startdatum/Uhrzeit
- **Periode**: Die Schulstunde (falls verwendet)
- **Erstellungs-Zeit vs. aktuelle Zeit**: Vergleich

---

## 🎯 PROBLEM 1: Falsches Datum beim Erstellen

**Symptom**: Start-Zeit ist in der Zukunft (z.B. morgen statt heute)

**Lösung**: 
1. In der Kalender-Ansicht das **richtige Datum** auswählen
2. Die **aktuelle Uhrzeit** für den Beginn nutzen (nicht eine zukünftige Zeit)
3. Für Schulstunden: Stelle sicher die **heutige Schulstunde** zu wählen

---

## 🎯 PROBLEM 2: Scheduler läuft nicht

**Symptom**: Keine Logs über Termin-Aktivierungen

**Überprüfung**:

```bash
# 1. Container-Logs anschauen
docker logs inventarsystem-app | grep -i "scheduler\|appointment\|status update"

# 2. Scheduler ist aktiviert?
docker exec inventarsystem-app python3 -c "
import sys
sys.path.insert(0, '/app/Web')
import settings as cfg
print(f'Scheduler aktiviert: {cfg.SCHEDULER_ENABLED}')
print(f'Scheduler Intervall: {cfg.SCHEDULER_INTERVAL_MIN} Minuten')
"
```

**Lösung wenn deaktiviert**:
- In `config.json` ändern:
  ```json
  "scheduler": {
    "enabled": true,
    "interval_minutes": 1
  }
  ```
- Container neu starten: `docker-compose restart app`

---

## 🎯 PROBLEM 3: Startzeit als nur-Zeit (kein Datum)

**Symptom**: Start-Zeit zeigt nur "13:30" ohne Datum

**Überprüfung**: In der Datenbank nach `{Start: {$type: "string"}}` suchen statt datetime

**Lösung**: Die Ausleihe muss mit einem vollständigen Datum+Uhrzeit erstellt werden.

---

## 🚀 AUTOMATISCHE AKTIVIERUNG TESTEN

Nach dem Fix: Erstelle eine Ausleihe für:
- **Heute** (das aktuelle Datum)
- **Schulstunde 7** (13:30-14:15)
- Startzeitpunkt sollte **jetzt oder in 1 Minute** sein

Warte 2 Minuten. Der Status sollte von `planned` zu `active` wechseln.

---

## 📊 SCHEDULER STATUS ÜBERPRÜFEN

```bash
# Zeige die letzten 50 Log-Zeilen
docker logs --tail 50 inventarsystem-app | tail -20

# Suche nach "Appointment status update"
docker logs inventarsystem-app 2>/dev/null | grep -i "Appointment status" | tail -5
```

Erwartete Log-Ausgabe:
```
Appointment status update finished: X changed (Y active, Z completed)
```

---

## 🔍 DETAILLIERTE DEBUG-INFOS

Wenn obiges nicht funktioniert, führe dies aus:

```bash
docker exec inventarsystem-app python3 -c "
from pymongo import MongoClient
import datetime

client = MongoClient('mongodb', 27017)
db = client['Inventarsystem']
aus = db['ausleihungen']

print('=== GEPLANTE AUSLEIHEN ===')
for b in aus.find({'Status': 'planned'}).limit(3):
    print(f\"Start: {b.get('Start')} | Typ: {type(b.get('Start')).__name__}\")
    print(f\"Periode: {b.get('Period')} | User: {b.get('User')}\")
    print(f\"Jetzt > Start? {datetime.datetime.now() > b.get('Start', datetime.datetime.max)}\")
    print()
"
```

---

## 💡 EMPFOHLENE EINSTELLUNG FÜR SCHULEN

In `config.json` verwende diese Werte:

```json
{
  "scheduler": {
    "enabled": true,
    "interval_minutes": 1,
    "backup_interval_hours": 24
  }
}
```

Dies checkt **jede Minute** ob Termine aktiviert werden sollen - perfekt für Schulstunden.

---

## Weitere Hilfe?

Falls das nicht funktioniert:
1. Schreib mir die **exakte Uhrzeit** wann du die Ausleihe erstellt hast
2. Und wann sie hätte aktiviert werden sollen
3. Zeige mir ein Beispiel aus der DB mit `docker exec inventarsystem-mongodb mongosh...`
