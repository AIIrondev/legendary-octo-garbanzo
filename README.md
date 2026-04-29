# Inventarsystem

[![https://github.com/AIIrondev/legendary-octo-garbanzo](https://github.com/AIIrondev/legendary-octo-garbanzo/actions/workflows/release-docker.yml/badge.svg)](https://github.com/AIIrondev/legendary-octo-garbanzo/actions/workflows/release-docker.yml)

[![wakatime](https://wakatime.com/badge/user/30b8509f-5e17-4d16-b6b8-3ca0f3f936d3/project/8a380b7f-389f-4a7e-8877-0fe9e1a4c243.svg)](https://wakatime.com/badge/user/30b8509f-5e17-4d16-b6b8-3ca0f3f936d3/project/8a380b7f-389f-4a7e-8877-0fe9e1a4c243)

**Aktuelle Version: 3.2.1**

Ein modernes webbasiertes Inventarverwaltungssystem zur Verwaltung, Ausleihe, Reservierung und Rückgabe von Gegenständen.
Das System richtet sich insbesondere an Bildungseinrichtungen, Organisationen und Labore.

---

## Inhaltsverzeichnis

- [Systemübersicht](#systemübersicht)
- [Hauptfunktionen](#hauptfunktionen)
- [Installation](#installation)
- [Docker Betrieb](#docker-betrieb)
- [Erste Einrichtung](#erste-einrichtung)
- [Systembetrieb](#systembetrieb)
- [Benutzerverwaltung](#benutzerverwaltung)
- [Artikelverwaltung](#artikelverwaltung)
- [Buchungssystem](#buchungssystem)
- [Backup & Wiederherstellung](#backup--wiederherstellung)
- [Wartung & Updates](#wartung--updates)
- [Versionsverwaltung](#versionsverwaltung)
- [Konfiguration](#konfiguration)
- [Fehlerbehebung](#fehlerbehebung)
- [Systemanforderungen](#systemanforderungen)
- [Lizenz Rechtliches & Datenschutz](#lizenz-rechtliches--datenschutz)

---

## Systemübersicht

Das Inventarsystem stellt folgende Wartungsskripte bereit:

| Skript | Beschreibung |
|---|---|
| `update.sh` | Aktualisiert Docker-Deployment aus GitHub Releases |
| `fix-all.sh` | Intelligentes Reparaturskript |
| `rebuild-venv.sh` | Python-Umgebung neu erstellen (nur Quellcode-Entwicklung) |
| `start.sh` | Dienste starten |
| `stop.sh` | Dienste stoppen |
| `restart.sh` | Dienste neu starten |
| `build-nuitka.sh` | Standalone-Build der App mit Nuitka erstellen |
| `Backup-DB.py` | Manuelles DB-Backup |
| `restore.sh` | Backup wiederherstellen |
| `manage-version.sh` | Versionssteuerung |

---

## Hauptfunktionen

### Benutzeranmeldung

- Sichere Passwortregeln (mindestens 6 Zeichen)
- Rollenbasiertes System
  - Administrator
  - Standardbenutzer
- Session-basierte Authentifizierung

### Artikelverwaltung

- Artikel hinzufügen / löschen
- Ausleihen & Rückgabe
- Metadatenverwaltung
- Anschaffungsdaten (Jahr, Kosten)
- Mehrfach-Bildupload
- UUID-basierte Dateinamen
- Detaillierte Artikelansicht

### Buchungssystem

- Konfliktprüfung
- Automatische Aktivierung
- Automatische Beendigung
- Kalenderansicht
- Perioden-Unterstützung (Schulstunden)

### Barcode-Scanner

- Integrierter Scanner
- Schnelles Auffinden von Artikeln
- Mobile-optimiert

### Filtersystem

- Dreistufige Filter
- Kombinierbare Suche
- Kategorie-Management

### Administrator-Tools

- Benutzerverwaltung
- Ausleihprotokolle
- Artikel-Reset
- Standortverwaltung

### Responsive Design

- Mobil optimiert
- Touch-freundlich
- Desktop-fähig

---

## Installation

### Voraussetzungen

- Python >= 3.7
- MongoDB
- pip
- Linux-System (empfohlen)

### Installation (automatisch)

**Option 1**

```bash
wget -O - https://raw.githubusercontent.com/AIIrondev/legendary-octo-garbanzo/main/install.sh | sudo bash
```

**Option 2**

```bash
curl -s https://raw.githubusercontent.com/AIIrondev/legendary-octo-garbanzo/main/install.sh | sudo bash
```

Legacy-MongoDB uebernehmen und altes Host-System aufraeumen:

```bash
curl -s https://raw.githubusercontent.com/AIIrondev/legendary-octo-garbanzo/main/install.sh | \
  sudo bash -s -- --migrate-legacy-db --remove-legacy-system
```

Optional kann ein alter Systempfad nach erfolgreicher Migration entfernt werden:

```bash
sudo ./install.sh --migrate-legacy-db --remove-legacy-system --legacy-system-dir /opt/Inventarsystem-alt
```

Ab dieser Version wird nach der Installation standardmaessig ein Alt-System-Cleanup ausgefuehrt
(u. a. alte Inventarsystem/Admin-Systemd-Dienste stoppen/deaktivieren, Restprozesse und stale Sockets entfernen).

Optionales Verhalten beim Install:

```bash
# Alt-System-Cleanup komplett ueberspringen
sudo ./install.sh --skip-cleanup-old

# Beim Alt-System-Cleanup auch passende Cron-Eintraege entfernen
sudo ./install.sh --cleanup-old-remove-cron
```

---

## Docker Betrieb

Das System läuft produktiv Docker-first. Deployments und Updates erfolgen über Release-Artefakte (Build-only), nicht über Quellcode-Pulls.

- Laufzeit-Stack: [docker-compose-multitenant.yml](docker-compose-multitenant.yml)
- Build-Pipeline: [Dockerfile](Dockerfile)
- Release-Pipeline: [.github/workflows/release-docker.yml](.github/workflows/release-docker.yml)
- Frontend/Reverse Proxy: Nginx (Container)

### Voraussetzungen

- Docker Engine
- Docker Compose Plugin

### Starten (portabel auf jedem Docker-Host)

```bash
docker compose up -d
```

Oder mit Hilfsskript:

```bash
./start.sh
```

Danach ist die Web-App erreichbar unter:

```text
https://[SERVER-IP]
```

Wenn keine Zertifikate vorhanden sind, erstellt `start.sh` automatisch ein selbstsigniertes Zertifikat unter `certs/inventarsystem.crt` und `certs/inventarsystem.key`.

Wenn Docker/Compose/OpenSSL fehlen, installiert `start.sh` die benoetigten Pakete automatisch.
Dabei wird zuerst `docker.io` versucht. Falls das auf dem System nicht verfuegbar ist, richtet das Skript das Docker-Repository ein und installiert `docker-ce` inklusive Compose-Plugin.

Standardmaessig richtet `start.sh` zusaetzlich die taeglichen Cron-Jobs fuer Backup (02:30) und Update (03:00) ein.
Das kann bei Bedarf deaktiviert werden mit `./start.sh --no-cron` oder per Umgebungsvariable `INVENTAR_SETUP_CRON=0 ./start.sh`.

### App mit Nuitka neu bauen

Fuer einen Standalone-Build der Flask-App steht folgendes Skript bereit:

```bash
./build-nuitka.sh
```

Das Skript:

- verwendet die Python-Umgebung unter `.venv`
- installiert/aktualisiert Nuitka Build-Abhaengigkeiten
- baut `Web/app.py` als Standalone-Binary
- bindet `Web/templates`, `Web/static` und `uploads` als Laufzeitdaten ein
- schreibt das Ergebnis nach `dist/app.dist/`

### Stoppen

```bash
docker compose down
```

Oder mit Hilfsskript:

```bash
./stop.sh
```

### Logs ansehen

```bash
docker compose logs -f app
docker compose logs -f mongodb
docker compose logs -f nginx
```

### Persistente Daten

Die Volumes sind in [docker-compose-multitenant.yml](docker-compose-multitenant.yml) definiert:

- MongoDB Daten
- Uploads / Thumbnails / Previews / QRCodes
- Backups und Logs

Hinweis: Für Container-Deployments werden MongoDB- und Speicherpfade via Umgebungsvariablen in [Web/settings.py](Web/settings.py) überschrieben.

### Updates (nur aus Releases)

```bash
sudo ./update.sh
```

`update.sh` lädt ausschließlich das Release-Asset `inventarsystem-docker-bundle.tar.gz` aus dem neuesten GitHub Release, lädt das passende Release-Image lokal aus dem Release-Archiv und startet den Stack ohne lokalen Rebuild neu.
Wenn lokal ein passendes Image-Artefakt unter `dist/` liegt (`inventarsystem-image-<tag>.tar.gz` oder `inventarsystem-image-*.tar.gz`), wird dieses zuerst verwendet.
Zusätzlich wird ein Health-Check ausgeführt; bei Fehlern endet das Update mit Exit-Code ungleich 0 und protokolliert Container-Logs in `logs/update.log`.

### Release-Erstellung (Build-only)

Beim Push eines Tags `v*` erstellt GitHub Actions automatisch:

- Container-Image in GHCR: `ghcr.io/aiirondev/inventarsystem:<tag>`
- Release-Asset `inventarsystem-docker-bundle.tar.gz` (nur Docker-Deployment-Dateien)
- Release-Asset `inventarsystem-image-<tag>.tar.gz` (offline Docker image export)

Damit enthalten Releases nur Build-Artefakte für Docker, nicht den produktiven Updatepfad über Roh-Quellcode.

---

## Erste Einrichtung

Nach der Installation:

```bash
cd /opt/Inventarsystem
sudo ./start.sh
```

Öffnen Sie dann im Browser:

```
https://[SERVER-IP]
```

### Admin-User erstellen

Wenn die Datenbank leer ist (beim ersten Start), erstellen Sie einen Admin-User:

**Option 1: Interaktiv**
```bash
cd Web && python3 generate_user.py
```

**Option 2: Multitenant-Tenant erstellen**
```bash
sudo ./manage-tenant.sh add <tenant-name> <port>
```

Dieser Weg erzeugt beim Anlegen eines neuen Tenants einen Standard-Admin für den Tenant.

**Option 3: Direkt in MongoDB (Notlösung)**
```bash
docker exec inventarsystem-mongodb mongosh --eval "
db.users.insertOne({
  Username: 'admin',
  Password: '\$(python3 -c \"import hashlib; print(hashlib.sha512(b\\\"deinPassword123\\\").hexdigest())\")' ,
  Admin: true,
  active_ausleihung: null,
  name: 'Admin',
  last_name: 'User',
  favorites: []
})
" Inventarsystem
```

---

## Systembetrieb

### Starten

```bash
sudo ./start.sh
```

### Stoppen

```bash
sudo ./stop.sh
```

### Neustarten

```bash
sudo ./restart.sh
```

### Status prüfen

```bash
docker compose ps
docker compose logs -f app
```

---

## Benutzerverwaltung

### Erstes Admin-Konto erstellen

```bash
cd /pfad/zum/Inventarsystem
source .venv/bin/activate
python Web/generate_user.py
```

### Benutzer über GUI hinzufügen

1. Als Admin anmelden
2. Benutzer verwalten
3. Neuen Benutzer hinzufügen
4. Daten eingeben
5. Speichern

---

## Artikelverwaltung

### Artikel hinzufügen

1. Admin anmelden
2. Artikel hochladen
3. Formular ausfüllen
4. Bilder hochladen
5. Speichern

### Unterstützte Formate

- JPG / JPEG
- PNG
- GIF
- MP4
- MOV

### Artikel bearbeiten

1. Bearbeitungssymbol klicken
2. Änderungen speichern

### Artikel löschen

1. Mülleimer klicken
2. Bestätigen

---

## Buchungssystem

### Artikel ausleihen

1. Artikel öffnen
2. Ausleihen klicken

Das System protokolliert automatisch.

### Artikel zurückgeben

1. Meine ausgeliehenen Artikel öffnen
2. Zurückgeben klicken

### Buchung planen

1. Terminplan öffnen
2. Zeitraum wählen
3. Speichern

---

## Backup & Wiederherstellung

### Backup erstellen

Universell (empfohlen, erkennt Host/Docker automatisch):

```bash
sudo ./backup.sh --mode auto
```

Docker-only (gleiche Logik, optional):

```bash
sudo ./backup.sh --mode docker
```

Alternativ (Host-Backupskript):

```bash
sudo ./backup.sh
```

Backup-Pfad:

```
/var/backups/Inventarsystem-YYYY-MM-DD.tar.gz
```

Rechnungs-Archiv (separat, rechtssicher):

```
/var/backups/invoice-archive/invoices-YYYY-MM-DD_HH-MM-SS.jsonl
/var/backups/invoice-archive/invoices-YYYY-MM-DD_HH-MM-SS.csv
/var/backups/invoice-archive/invoices-YYYY-MM-DD_HH-MM-SS.meta.json
```

Standard-Aufbewahrung fuer Rechnungsarchive:

- 3650 Tage (10 Jahre)

Optional konfigurierbar:

```bash
sudo ./backup.sh --invoice-keep-days 3650
sudo ./backup.sh --invoice-archive-dir /var/backups/invoice-archive
```

### Backup wiederherstellen

```bash
sudo ./restore.sh --list
sudo ./restore.sh --date=latest
sudo ./restart.sh
```

---

## Wartung & Updates

### System aktualisieren

```bash
sudo ./update.sh
```

Hinweis: Updatepfad ist release-only. Es wird kein `git pull` verwendet.

### Virtuelle Umgebung neu erstellen

```bash
sudo ./rebuild-venv.sh
sudo ./restart.sh
```

### Komplettreparatur

```bash
sudo ./fix-all.sh
```

---

## Versionsverwaltung

Mit `manage-version.sh` können Sie gezielt Versionen steuern, Downgrades durchführen und Versionen pinnen.

### Beispiele

```bash
# Dauerhaft auf eine Version (Tag, Commit oder Branch) pinnen
./manage-version.sh pin v2.5.17 --restart

# Einmalig auf eine Version wechseln
./manage-version.sh use <ref> --restart

# Aktuellen Status anzeigen
./manage-version.sh status

# Pin entfernen und zur Hauptversion zurückkehren
./manage-version.sh clear --restart
```

### Wichtige Hinweise

- Pin wird in `.version-lock` gespeichert
- Unterstützt: Tags, Branches, Commits
- Erstellt automatische Backups vor jedem Wechsel
- Bewahrt Datenverzeichnisse über den Versionswechsel hinweg

---

## Konfiguration

### config.json bearbeiten

```bash
sudo nano config.json
```

Beispiel:

```json
{
  "dbg": false,
  "key": "IhrGeheimSchlüssel",
  "ver": "2.6.2",
  "host": "0.0.0.0",
  "port": 443
}
```

### SSL aktualisieren

```bash
sudo chmod 600 certs/inventarsystem.key
sudo chmod 644 certs/inventarsystem.crt
```

---

## Fehlerbehebung

### Webserver startet nicht

```bash
docker compose ps
docker compose logs -f nginx
docker compose logs -f app
```

### MongoDB-Probleme

```bash
docker compose restart mongodb
docker compose logs -f mongodb
```

### PyMongo/BSON-Konflikt

```bash
sudo ./fix-all.sh
```

oder

```bash
sudo ./rebuild-venv.sh
```

### Bild-Upload Probleme

```bash
sudo ./fix-all.sh
```

Verzeichnisse prüfen:

```bash
sudo ls -la Web/uploads
sudo ls -la Web/QRCodes
sudo ls -la Web/thumbnails
```

### Empfohlener Troubleshooting-Workflow

1. Status prüfen
2. Logs prüfen
3. `fix-all.sh` ausführen
4. Neustarten

Automatische Überwachung einrichten:

```bash
sudo ./fix-all.sh --setup-cron
```

---

## Systemanforderungen

- Moderner Webbrowser (Chrome, Firefox, Safari, Edge)
- Internetzugang
- Kamera für QR-Scan
- Desktop empfohlen für Admins

---

## Lizenz Rechtliches & Datenschutz

Dieses Projekt ist auf Transparenz und Datensparsamkeit ausgelegt. Um einen rechtskonformen Betrieb (insbesondere gemäß DSGVO) zu gewährleisten, wurden folgende Dokumente erstellt:

* **[Lizenz](./LICENSE)** 

* **[Datenschutzerklärung](./Legal/PRIVACY.md):** Erläutert, welche personenbezogenen Daten (z. B. Inventarzuordnungen, Logins) verarbeitet werden.
* **[Datenverarbeitung & Dokumentation](./Legal/DATA_PROCESSING.md):** Details zu den technischen Abläufen und Speichermechanismen innerhalb des Systems.
* **[Rechtsgrundlage](./Legal/LEGAL_BASIS.md):** Informationen für Administratoren zur rechtmäßigen Nutzung im geschäftlichen oder privaten Umfeld.
* **[Sicherheit & Mechanismen](./Legal/SECURITY.md):** Übersicht der implementierten Schutzmaßnahmen (Hashing, Zugriffskontrolle).

> **Wichtiger Hinweis:** Die bereitgestellten Dokumente dienen als Vorlage. Als Betreiber einer Instanz dieses Inventarsystems sind Sie selbst dafür verantwortlich, diese an Ihre spezifische Hosting-Umgebung und Ihre internen Prozesse anzupassen.

---

## Mitwirkende

**Maximilian Gründinger** — Projektgründer

Für technische Unterstützung oder Fragen bitte ein Issue im GitHub-Repository eröffnen.

---

Das Inventarsystem ist eine robuste, wartungsfreundliche Komplettlösung für Inventarverwaltung mit Fokus auf Bildungseinrichtungen.
Durch automatisierte Wartung, integrierte Backups und intelligente Diagnose lässt sich das System zuverlässig betreiben und skalieren.
