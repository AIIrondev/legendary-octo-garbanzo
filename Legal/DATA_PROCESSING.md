# Dokumentation der Datenverarbeitung (VVT)

## Systemübersicht
Das **Inventarsystem** ist eine Anwendung zur Erfassung und Verwaltung von physischen Gütern.

## Datenfluss
1. **Eingabe:** Nutzer gibt Daten über das Frontend/API ein.
2. **Speicherung:** Daten werden in einer lokalen Datenbank verschlüsselt abgelegt.
3. **Ausgabe:** Anzeige der Bestände für autorisierte Nutzer.

## Technische und Organisatorische Maßnahmen (TOM)
- **Zugangskontrolle:** Authentifizierung über Benutzerkonten.
- **Integrität:** Validierung der Eingabedaten zur Vermeidung von Datenbankfehlern.
- **Verfügbarkeit:** Empfohlene Backup-Strategien für die Datenbank.

## Empfänger der Daten
Die Daten verbleiben innerhalb der kontrollierten Umgebung der Installation. Es findet kein automatisierter Export an Dritte statt.