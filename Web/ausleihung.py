"""
Ausleihungssystem (Borrowing System)
====================================

Dieses Modul verwaltet sämtliche Ausleihungen im Inventarsystem.
Es bietet alle Funktionen, um Ausleihungen zu planen, zu aktivieren,
zu beenden und zu stornieren.

Hauptfunktionen:
- Erstellen neuer Ausleihungen (geplant oder sofort aktiv)
- Aktualisieren von Ausleihungsdaten
- Abschließen von Ausleihungen (Rückgabe)
- Suchen und Abrufen von Ausleihungen nach verschiedenen Kriterien
- Verwaltung des Ausleihungs-Lebenszyklus

Sammlungsstruktur:
- ausleihungen: Speichert alle Ausleihungsdatensätze mit ihrem Status
  - Status-Werte: 'planned' (geplant), 'active' (aktiv), 'completed' (abgeschlossen), 'cancelled' (storniert)
"""
'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
from pymongo import MongoClient
from bson.objectid import ObjectId
import datetime
import pytz
from datetime import timezone
import os
import json
import shutil
import settings as cfg

# Add this helper function after imports
def ensure_timezone_aware(dt):
    """Ensures a datetime is timezone-aware, using UTC if naive"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC
        return dt.replace(tzinfo=None)
    return dt

def get_current_status(ausleihung, log_changes=False, user=None):
    """
    Ermittelt den aktuellen Status einer Ausleihung basierend auf den Zeitstempeln
    und dem gespeicherten Status. Diese Funktion berücksichtigt das aktuelle Datum
    und aktualisiert den Status entsprechend dem realen Zustand.
    
    Status-Werte:
    - 'planned': Eine zukünftige Ausleihung, die noch nicht begonnen hat
    - 'active': Eine aktive Ausleihung, die gerade läuft
    - 'completed': Eine beendete Ausleihung
    - 'cancelled': Eine stornierte Ausleihung
    
    Args:
        ausleihung (dict): Der Ausleihungsdatensatz
        log_changes (bool): Ob Statusänderungen protokolliert werden sollen
        user (str): Der Benutzer, der die Prüfung durchführt (für Logs)
        
    Returns:
        str: Der aktuelle Status ('planned', 'active', 'completed', 'cancelled')
    """
    # Speichern Sie den ursprünglichen Status für Logging-Zwecke
    original_status = ausleihung.get('Status', 'unknown')
    
    # Bei stornierten Ausleihungen bleibt der Status immer storniert
    if original_status == 'cancelled':
        return 'cancelled'
    
    current_time = datetime.datetime.now()
    start_time = ausleihung.get('Start')
    end_time = ausleihung.get('End')
    
    # Wenn kein Startdatum vorhanden ist, Status auf 'planned' setzen
    if not start_time:
        new_status = 'planned'
    # Wenn die Ausleihung als 'completed' markiert wurde und ein Enddatum hat,
    # bleibt sie bei 'completed'
    elif original_status == 'completed' and end_time:
        new_status = 'completed'
    # Wenn die aktuelle Zeit vor dem Startdatum liegt, ist die Ausleihung geplant
    elif current_time < start_time:
        new_status = 'planned'
    # Wenn kein Enddatum gesetzt ist oder die aktuelle Zeit vor dem Enddatum liegt,
    # ist die Ausleihung aktiv
    elif not end_time or current_time < end_time:
        new_status = 'active'
    # Wenn die aktuelle Zeit nach dem Enddatum liegt, ist die Ausleihung beendet
    else:
        new_status = 'completed'
    
    # Protokollieren Sie Statusänderungen, wenn aktiviert und eine Änderung stattgefunden hat
    if log_changes and new_status != original_status and '_id' in ausleihung:
        try:
            # Importieren Sie das Modul nur bei Bedarf, um zirkuläre Importe zu vermeiden
            import ausleihung_log
            ausleihung_log.log_status_change(
                str(ausleihung['_id']), 
                original_status, 
                new_status,
                user
            )
        except Exception as e:
            print(f"Fehler beim Protokollieren der Statusänderung: {e}")
    
    return new_status

def create_backup_database():
    """
    Erstellt eine Sicherungskopie der Ausleihungsdatenbank.
    
    Returns:
        bool: True wenn Backup erfolgreich erstellt wurde, sonst False
    """
    try:
        # Verbindung zur Datenbank herstellen
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Backup-Verzeichnis erstellen, falls es nicht existiert
        backup_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backups')
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        # Aktuelles Datum für den Dateinamen
        current_date = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
        backup_file = os.path.join(backup_dir, f'ausleihungen_backup_{current_date}.json')
        
        # Ausleihungen abrufen und als JSON speichern
        all_ausleihungen = list(ausleihungen.find({}))
        
        # ObjectId in String umwandeln für JSON-Serialisierung
        for ausleihung in all_ausleihungen:
            ausleihung['_id'] = str(ausleihung['_id'])
            if 'Start' in ausleihung and ausleihung['Start']:
                ausleihung['Start'] = ausleihung['Start'].isoformat()
            if 'End' in ausleihung and ausleihung['End']:
                ausleihung['End'] = ausleihung['End'].isoformat()
            if 'LastUpdated' in ausleihung and ausleihung['LastUpdated']:
                ausleihung['LastUpdated'] = ausleihung['LastUpdated'].isoformat()
        
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(all_ausleihungen, f, ensure_ascii=False, indent=4)
        
        # Log-Eintrag erstellen
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, 'ausleihungen_backup.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{current_date}: Backup erstellt: {backup_file}, {len(all_ausleihungen)} Einträge\n")
        
        client.close()
        return True
    except Exception as e:
        # Fehler protokollieren
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        log_file = os.path.join(log_dir, 'ausleihungen_error.log')
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}: Backup-Fehler: {str(e)}\n")
        
        print(f"Fehler beim Erstellen des Backups: {e}")
        return False


# === AUSLEIHUNG MANAGEMENT ===

def add_ausleihung(item_id, user, start_date, end_date=None, notes="", status="active", period=None, exemplar_data=None):
    """
    Add a new borrowing record for an item.
    
    Args:
        item_id (str): ID of the item borrowed
        user (str): Username of the borrower
        start_date (datetime): Start date and time of the borrowing
        end_date (datetime, optional): End date and time if already returned
        notes (str, optional): Additional notes about the borrowing
        status (str, optional): Status of the borrowing (active, completed, planned)
        period (str, optional): School period for the borrowing
        exemplar_data (dict, optional): Information about specific exemplar borrowed
        
    Returns:
        ObjectId: ID of the new borrowing record or None if failed
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        ausleihung = {
            'Item': item_id,
            'User': user,
            'Start': start_date,
            'Status': status
        }
        
        if end_date:
            ausleihung['End'] = end_date
            
        if notes:
            ausleihung['Notes'] = notes
            
        if period:
            ausleihung['Period'] = period
            
        if exemplar_data:
            ausleihung['ExemplarData'] = exemplar_data
        
        result = ausleihungen.insert_one(ausleihung)
        ausleihung_id = result.inserted_id
        
        client.close()
        return ausleihung_id
    except Exception as e:
        print(f"Error adding ausleihung: {e}")
        return None

def update_ausleihung(id, item_id=None, user_id=None, start=None, end=None, notes=None, status=None, period=None):
    """
    Update an existing ausleihung record.
    
    Args:
        id (str): ID of the ausleihung to update
        item_id (str, optional): New item ID
        user_id (str, optional): New user ID
        start (datetime, optional): New start time
        end (datetime, optional): New end time
        notes (str, optional): New notes
        status (str, optional): New status
        period (int, optional): New period
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Build update data with only the fields that are provided
        update_data = {}
        
        if item_id is not None:
            update_data['Item'] = item_id
        if user_id is not None:
            update_data['User'] = user_id
        if start is not None:
            # Ensure timezone-aware datetime
            update_data['Start'] = ensure_timezone_aware(start)
        if end is not None:
            # Ensure timezone-aware datetime
            update_data['End'] = ensure_timezone_aware(end)
        if notes is not None:
            update_data['Notes'] = notes
        if status is not None:
            update_data['Status'] = status
        if period is not None:
            update_data['Period'] = period
            
        # Always update the LastUpdated timestamp
        update_data['LastUpdated'] = datetime.datetime.now()
        
        # Perform the update
        result = ausleihungen.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )
        
        client.close()
        
        # Log the update for debugging
        print(f"Updated ausleihung {id}: modified_count={result.modified_count}, update_data={update_data}")
        
        return result.modified_count > 0
        
    except Exception as e:
        print(f"Error updating ausleihung: {e}")
        return False

def complete_ausleihung(id, end_time=None):
    """
    Markiert eine Ausleihe als abgeschlossen, indem das Enddatum gesetzt 
    und der Status auf 'completed' geändert wird.
    
    Args:
        id (str): ID des abzuschließenden Ausleihungsdatensatzes
        end_time (datetime, optional): Endzeitpunkt (Standard: aktuelle Zeit)
        
    Returns:
        bool: True bei Erfolg, sonst False
    """
    try:
        if end_time is None:
            end_time = datetime.datetime.now()
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        item = db['items']
        
        result = ausleihungen.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'End': end_time,
                'Status': 'completed',
                'LastUpdated': datetime.datetime.now()
            }}
        )
        
        item.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'Verfuegbar': True,
                'LastUpdated': datetime.datetime.now()
            }}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        # print(f"Error completing ausleihung: {e}") # Log the error
        return False


def cancel_ausleihung(id):
    """
    Storniert eine geplante Ausleihe durch Änderung des Status auf 'cancelled'.
    
    Args:
        id (str): ID der zu stornierenden Ausleihe
        
    Returns:
        bool: True bei Erfolg, sonst False
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']

        # Mark the booking as cancelled
        result = ausleihungen.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'Status': 'cancelled',
                'LastUpdated': datetime.datetime.now()
            }}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        # print(f"Error cancelling ausleihung: {e}") # Log the error
        return False


def remove_ausleihung(id):
    """
    Entfernt einen Ausleihungsdatensatz aus der Datenbank.
    Hinweis: Normalerweise ist es besser, Datensätze zu markieren als sie zu löschen.
    
    Args:
        id (str): ID des zu entfernenden Ausleihungsdatensatzes
        
    Returns:
        bool: True bei Erfolg, sonst False
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        result = ausleihungen.delete_one({'_id': ObjectId(id)})
        client.close()
        return result.deleted_count > 0
    except Exception as e:
        # print(f"Error removing ausleihung: {e}") # Log the error
        return False


# === AUSLEIHUNG RETRIEVAL ===

def get_ausleihung(id):
    """
    Ruft einen bestimmten Ausleihungsdatensatz anhand seiner ID ab.
    
    Args:
        id (str): ID des abzurufenden Ausleihungsdatensatzes
        
    Returns:
        dict: Der Ausleihungsdatensatz oder None, wenn nicht gefunden
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        ausleihung = ausleihungen.find_one({'_id': ObjectId(id)})
        client.close()
        return ausleihung
    except Exception as e:
        # print(f"Error retrieving ausleihung: {e}") # Log the error
        return None


def get_ausleihungen(status=None, start=None, end=None, date_filter='overlap'):
    """
    Ruft Ausleihungen nach verschiedenen Kriterien ab.
    
    Args:
        status (str/list, optional): Status(se) der Ausleihungen ('planned', 'active', 'completed', 'cancelled')
        start (str/datetime, optional): Startdatum für Datumsfilterung
        end (str/datetime, optional): Enddatum für Datumsfilterung
        date_filter (str, optional): Art des Datumsfilters ('overlap', 'start_in', 'end_in', 'contained')
        
    Returns:
        list: Liste von Ausleihungsdatensätzen
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        collection = db['ausleihungen']
        
        # Query erstellen
        query = {}
        
        # Status-Filter hinzufügen
        if status is not None:
            if isinstance(status, list):
                query['Status'] = {'$in': status}
            else:
                query['Status'] = status
        
        # Datum parsen, wenn als String angegeben
        if start is not None and isinstance(start, str):
            try:
                from dateutil import parser
                start = parser.parse(start)
            except:
                start = None
                
        if end is not None and isinstance(end, str):
            try:
                from dateutil import parser
                end = parser.parse(end)
            except:
                end = None
        
        # Datumsfilter hinzufügen
        if start is not None and end is not None:
            if date_filter == 'overlap':
                # Überlappende Ausleihungen (Standard)
                query['$or'] = [
                    # Ausleihe beginnt im Bereich
                    {'Start': {'$gte': start, '$lte': end}},
                    # Ausleihe endet im Bereich
                    {'End': {'$gte': start, '$lte': end}},
                    # Ausleihe umfasst den gesamten Bereich
                    {'Start': {'$lte': start}, 'End': {'$gte': end}},
                    # Aktive Ausleihungen ohne Ende, die vor dem Ende beginnen
                    {'Start': {'$lte': end}, 'End': None}
                ]
            elif date_filter == 'start_in':
                # Nur Ausleihungen, die im Bereich beginnen
                query['Start'] = {'$gte': start, '$lte': end}
            elif date_filter == 'end_in':
                # Nur Ausleihungen, die im Bereich enden
                query['End'] = {'$gte': start, '$lte': end}
            elif date_filter == 'contained':
                # Nur Ausleihungen, die vollständig im Bereich liegen
                query['Start'] = {'$gte': start}
                query['End'] = {'$lte': end}
        
        results = list(collection.find(query))
        client.close()
        return results
    except Exception as e:
        # print(f"Error retrieving ausleihungen: {e}") # Log the error
        return []


def get_active_ausleihungen(start=None, end=None):
    """
    Ruft alle aktiven (laufenden) Ausleihungen ab.
    
    Args:
        start (str/datetime, optional): Startdatum für Datumsfilterung
        end (str/datetime, optional): Enddatum für Datumsfilterung
        
    Returns:
        list: Liste aktiver Ausleihungsdatensätze
    """
    return get_ausleihungen(status='active', start=start, end=end)


def get_planned_ausleihungen(start=None, end=None):
    """
    Ruft alle geplanten Ausleihungen (Reservierungen) ab.
    
    Args:
        start (str/datetime, optional): Startdatum für Datumsfilterung
        end (str/datetime, optional): Enddatum für Datumsfilterung
        
    Returns:
        list: Liste geplanter Ausleihungsdatensätze
    """
    return get_ausleihungen(status='planned', start=start, end=end)


def get_completed_ausleihungen(start=None, end=None):
    """
    Ruft alle abgeschlossenen Ausleihungen ab.
    
    Args:
        start (str/datetime, optional): Startdatum für Datumsfilterung
        end (str/datetime, optional): Enddatum für Datumsfilterung
        
    Returns:
        list: Liste abgeschlossener Ausleihungsdatensätze
    """
    return get_ausleihungen(status='completed', start=start, end=end)


def get_cancelled_ausleihungen(start=None, end=None):
    """
    Ruft alle stornierten Ausleihungen ab.
    
    Args:
        start (str/datetime, optional): Startdatum für Datumsfilterung
        end (str/datetime, optional): Enddatum für Datumsfilterung
        
    Returns:
        list: Liste stornierter Ausleihungsdatensätze
    """
    return get_ausleihungen(status='cancelled', start=start, end=end)


# === SEARCH FUNCTIONS ===

def get_ausleihung_by_user(user_id, status=None, use_client_side_verification=True):
    """
    Ruft Ausleihungen für einen bestimmten Benutzer ab und verifiziert den Status clientseitig.
    
    Args:
        user_id (str): ID oder Benutzername des Benutzers
        status (str/list, optional): Status(se) der Ausleihungen
        use_client_side_verification (bool, optional): Ob der Status clientseitig verifiziert werden soll
        
    Returns:
        list: Liste von Ausleihungsdatensätzen des Benutzers
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        query = {'User': user_id}
        
        # Wenn clientseitige Verifikation verwendet wird, holen wir ALLE Ausleihungen
        # und filtern später clientseitig
        if use_client_side_verification:
            # Bei clientseitiger Verifikation alle Ausleihungen holen (auch cancelled)
            # da wir den Status später neu berechnen
            pass  # query bleibt unverändert
        else:
            # Exclude only cancelled status by default - we want to see planned, active, and completed
            if status is not None:
                if isinstance(status, list):
                    query['Status'] = {'$in': status}
                else:
                    query['Status'] = status
            else:
                # Otherwise exclude only cancelled appointments
                query['Status'] = {'$ne': 'cancelled'}
            
        # Get appointments from database
        if not use_client_side_verification:
            results = list(ausleihungen.find(query))
            client.close()
            return results
        
        # Wenn clientseitige Statusverifikation aktiviert ist, holen wir alle Ausleihungen
        # des Benutzers und verifizieren den Status anschließend
        all_ausleihungen = list(ausleihungen.find(query))
        client.close()
        
        # Immer clientseitige Statusverifikation durchführen wenn aktiviert
        if use_client_side_verification:
            for ausleihung in all_ausleihungen:
                # Clientseitige Statusverifizierung für alle Ausleihungen
                current_status = get_current_status(ausleihung)
                ausleihung['VerifiedStatus'] = current_status
        
        # Wenn keine Filterung erforderlich ist, geben wir alle Ausleihungen zurück
        if status is None:
            return all_ausleihungen
        
        # Statusfilterung durchführen
        filtered_results = []
        for ausleihung in all_ausleihungen:
            # Clientseitige Statusverifizierung
            current_status = get_current_status(ausleihung)
            
            # Status-Matching
            if isinstance(status, list):
                if current_status in status:
                    # Status aktualisieren und zur Ergebnismenge hinzufügen
                    ausleihung['VerifiedStatus'] = current_status
                    filtered_results.append(ausleihung)
            else:
                if current_status == status:
                    # Status aktualisieren und zur Ergebnismenge hinzufügen
                    ausleihung['VerifiedStatus'] = current_status
                    filtered_results.append(ausleihung)
        
        return filtered_results
    except Exception as e:
        # print(f"Error retrieving ausleihungen for user {user_id}: {e}") # Log the error
        return []


def get_ausleihung_by_item(item_id, status=None, include_history=False):
    """
    Get ausleihung record(s) for a specific item.
    
    Args:
        item_id (str): ID of the item
        status (str, optional): Filter by status
        include_history (bool): If True, return the most recent record regardless of status
        
    Returns:
        dict or None: Ausleihung record or None if not found
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Build query
        query = {'Item': item_id}
        if status and not include_history:
            query['Status'] = status
        
        # Get the most recent record by sorting by Start date descending
        ausleihung = ausleihungen.find(query).sort('Start', -1).limit(1)
        
        result = None
        for record in ausleihung:
            record['_id'] = str(record['_id'])
            result = record
            break
            
        client.close()
        return result
        
    except Exception as e:
        print(f"Error getting ausleihung by item: {e}")
        return None


def get_ausleihungen_by_date_range(start_date, end_date, status=None):
    """
    Ruft Ausleihungen ab, die in einem bestimmten Zeitraum aktiv waren.
    
    Args:
        start_date (datetime): Beginn des Zeitraums
        end_date (datetime): Ende des Zeitraums
        status (str/list, optional): Status(se) der Ausleihungen
        
    Returns:
        list: Liste von Ausleihungsdatensätzen im Zeitraum
    """
    return get_ausleihungen(status=status, start=start_date, end=end_date)


def check_ausleihung_conflict(item_id, start_date, end_date, period=None):
    """
    Prüft, ob es Konflikte mit bestehenden Ausleihungen oder aktiven Ausleihen gibt.
    
    Args:
        item_id (str): ID des zu prüfenden Gegenstands
        start_date (datetime): Vorgeschlagenes Startdatum
        end_date (datetime): Vorgeschlagenes Enddatum
        period (int, optional): Schulstunde für die Prüfung

    Returns:
        bool: True, wenn ein Konflikt besteht, sonst False
    """
    try:
        print(f"Checking booking conflict for item {item_id}, period {period}, start {start_date}, end {end_date}")
        
        if start_date and hasattr(start_date, 'tzinfo') and start_date.tzinfo:
            start_date = start_date.replace(tzinfo=None)
        if end_date and hasattr(end_date, 'tzinfo') and end_date.tzinfo:
            end_date = end_date.replace(tzinfo=None)
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Get the date component for filtering
        booking_date = start_date.date()
        
        # First, get all active and planned bookings for this item
        all_bookings = list(ausleihungen.find({
            'Item': item_id,
            'Status': {'$in': ['planned', 'active']}
        }))
        
        # Print all relevant bookings for debugging
        print(f"Found {len(all_bookings)} existing bookings for this item")
        for bk in all_bookings:
            bk_id = str(bk.get('_id'))
            bk_status = bk.get('Status')
            bk_period = bk.get('Period', 'None')
            bk_start = bk.get('Start')
            bk_user = bk.get('User')
            print(f"  - Booking {bk_id}: Status={bk_status}, Period={bk_period}, Start={bk_start}, User={bk_user}")

        # If we're booking by period, check for period conflicts
        if period is not None:
            period_int = int(period)
            
            # Check bookings on the same day with the same period
            for booking in all_bookings:
                booking_start = booking.get('Start')
                if not booking_start:
                    continue
                    
                # Compare just the date part
                try:
                    # Ensure we're comparing date objects, not datetime objects
                    existing_date = booking_start.date()
                    if existing_date == booking_date:
                        # If this booking has the same period, it's a conflict
                        booking_period = booking.get('Period')
                        # Convert to integer for proper comparison
                        if booking_period is not None and int(booking_period) == period_int:
                            print(f"CONFLICT: Same day, same period. Period: {period_int}, Date: {booking_date}")
                            client.close()
                            return True
                except Exception as e:
                    print(f"Error comparing dates: {e}")
                    # Continue checking other bookings if there's an error with one
        
        # Always check for time overlaps, regardless of whether period was specified
        for booking in all_bookings:
            booking_start = booking.get('Start')
            booking_end = booking.get('End')
            
            if not booking_start:
                continue
            
            # Set default end time if not specified
            if not booking_end:
                booking_end = booking_start + datetime.timedelta(hours=1)
            
            # Check for overlap
            # 1. New booking starts during existing booking
            # 2. New booking ends during existing booking
            # 3. New booking completely contains existing booking
            # 4. Existing booking completely contains new booking
            if ((start_date >= booking_start and start_date < booking_end) or
                (end_date > booking_start and end_date <= booking_end) or
                (start_date <= booking_start and end_date >= booking_end) or
                (start_date >= booking_start and end_date <= booking_end)):
                print(f"CONFLICT: Time overlap. New booking: {start_date}-{end_date}, Existing: {booking_start}-{booking_end}")
                client.close()
                return True
        
        print("No conflicts found!")
        client.close()
        return False
        
    except Exception as e:
        print(f"Error checking booking conflicts: {e}")
        import traceback
        traceback.print_exc()
        return True  # Bei Fehler Konflikt annehmen, um auf Nummer sicher zu gehen


def check_booking_period_range_conflict(item_id, start_date, end_date, period=None, period_end=None):
    """
    Checks for conflicts with existing bookings, supporting period ranges
    
    Args:
        item_id (str): ID of the item to check
        start_date (datetime): Start time for the booking
        end_date (datetime): End time for the booking
        period (int): Optional period number (for period-based booking)
        period_end (int): Optional end period number for period ranges
        
    Returns:
        bool: True if there's a conflict, False otherwise
    """
    try:
        if start_date and hasattr(start_date, 'tzinfo') and start_date.tzinfo:
            start_date = start_date.replace(tzinfo=None)
        if end_date and hasattr(end_date, 'tzinfo') and end_date.tzinfo:
            end_date = end_date.replace(tzinfo=None)
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Get the date component for filtering
        booking_date = start_date.date()
        
        # First, get all active and planned bookings for this item
        all_bookings = list(ausleihungen.find({
            'Item': item_id,
            'Status': {'$in': ['planned', 'active']}
        }))
        
        # Print all relevant bookings for debugging
        print(f"Found {len(all_bookings)} existing bookings for this item")
        
        # If we're booking by period, check for period conflicts
        if period is not None:
            period_start = int(period)
            periods_to_check = [period_start]
            
            # If period_end is specified, it's a range of periods
            if period_end is not None:
                period_end = int(period_end)
                periods_to_check = list(range(period_start, period_end + 1))
                
            # Check bookings on the same day with any overlapping period
            for booking in all_bookings:
                booking_start = booking.get('Start')
                if not booking_start:
                    continue
                    
                # Compare just the date part
                existing_date = booking_start.date()
                if existing_date == booking_date:
                    booking_period = booking.get('Period')
                    # Normalize to int if possible
                    try:
                        booking_period_int = int(booking_period) if booking_period is not None else None
                    except Exception:
                        booking_period_int = None
                    
                    # If this booking has any period in our range, it's a conflict
                    if booking_period_int is not None and booking_period_int in periods_to_check:
                        print(f"CONFLICT: Same day, overlapping period. Booking period: {booking_period_int}")
                        client.close()
                        return True
        # Always also check time overlaps against any existing bookings (incl. those without Period)
        for booking in all_bookings:
            booking_start = booking.get('Start')
            booking_end = booking.get('End')
            
            if not booking_start:
                continue
            
            # Set default end time if not specified
            if not booking_end:
                booking_end = booking_start + datetime.timedelta(hours=1)
            
            # Check for overlap of [start_date, end_date] with [booking_start, booking_end]
            if ((start_date >= booking_start and start_date < booking_end) or
                (end_date > booking_start and end_date <= booking_end) or
                (start_date <= booking_start and end_date >= booking_end) or
                (start_date >= booking_start and end_date <= booking_end)):
                print(f"CONFLICT: Time overlap. New: {start_date}-{end_date}, Existing: {booking_start}-{booking_end}")
                client.close()
                return True
        
        print("No conflicts found!")
        client.close()
        return False
        
    except Exception as e:
        print(f"Error checking booking conflicts: {e}")
        import traceback
        traceback.print_exc()
        return True  # Assume conflict on error for safety


# === AUTOMATISIERTE VERARBEITUNG ===

def get_ausleihungen_starting_now(current_time):
    """
    Ruft Ausleihungen ab, die jetzt beginnen sollen (innerhalb eines Zeitfensters).
    
    Args:
        current_time (datetime): Aktuelle Zeit für den Vergleich
    
    Returns:
        list: Liste von Ausleihungen, die jetzt beginnen sollen
    """
    try:
        # Define a wider time window (3 hours before to 1 hour after)
        # This helps catch bookings that might have been missed
        hours_before = datetime.timedelta(hours=3)
        hours_after = datetime.timedelta(hours=1)
        start_time = current_time - hours_before
        end_time = current_time + hours_after
        
        # Get today's date for date comparison
        today = current_time.date()
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Build a query to find planned bookings that:
        # 1. Are scheduled to start within our time window
        # 2. OR have a period set for today
        query = {
            'Status': 'planned',
            '$or': [
                # Time-based bookings within our window
                {'Start': {'$lte': end_time, '$gte': start_time}},
                
                # Period-based bookings for today
                {
                    'Period': {'$exists': True},
                    'Start': {
                        '$gte': datetime.datetime.combine(today, datetime.time.min),
                        '$lt': datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min)
                    }
                }
            ]
        }
        
        print(f"Query for bookings starting now: {query}")
        bookings = list(ausleihungen.find(query))
        
        print(f"Found {len(bookings)} bookings that might be starting now")
        for b in bookings:
            print(f"  - Booking {b.get('_id')}: Start={b.get('Start')}, Period={b.get('Period')}")
            
        client.close()
        return bookings
    except Exception as e:
        print(f"Error in get_ausleihungen_starting_now: {e}")
        import traceback
        traceback.print_exc()
        return []


def get_ausleihungen_ending_now(current_time):
    """
    Ruft Ausleihungen ab, die jetzt enden sollen (innerhalb eines Zeitfensters).
    
    Args:
        current_time (datetime): Aktuelle Zeit für den Vergleich
    
    Returns:
        list: Liste von Ausleihungen, die jetzt enden sollen
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Create a wider time window (15 minutes before to catch any missed endings)
        window_before = datetime.timedelta(minutes=15)
        window_after = datetime.timedelta(minutes=5)
        start_time = current_time - window_before
        end_time = current_time + window_after
        
        # Get today's date for period-based checks
        today = current_time.date()
        
        # Find active bookings that:
        # 1. Have an end time within our window, OR
        # 2. Are from today with a period (will check the period in process_bookings)
        query = {
            'Status': 'active',
            '$or': [
                {'End': {'$gte': start_time, '$lte': end_time}},
                {
                    'Period': {'$exists': True},
                    'Start': {
                        '$gte': datetime.datetime.combine(today, datetime.time.min),
                        '$lt': datetime.datetime.combine(today + datetime.timedelta(days=1), datetime.time.min)
                    }
                }
            ]
        }
        
        print(f"Looking for bookings ending now with query: {query}")
        bookings = list(ausleihungen.find(query))
        print(f"Found {len(bookings)} bookings that might be ending now")
        for b in bookings:
            print(f"  - Potential ending booking {b.get('_id')}: End={b.get('End')}, Period={b.get('Period')}")
            
        client.close()
        return bookings
    except Exception as e:
        print(f"Error in get_ausleihungen_ending_now: {e}")
        import traceback
        traceback.print_exc()
        return []


def activate_ausleihung(id):
    """
    Aktiviert eine geplante Ausleihe.
    
    Args:
        id (str): ID der zu aktivierenden Ausleihe
        
    Returns:
        bool: True bei Erfolg, sonst False
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Zuerst prüfen, ob die Ausleihe existiert und den Status 'planned' hat
        ausleihung = ausleihungen.find_one({'_id': ObjectId(id)})
        if not ausleihung or ausleihung.get('Status') != 'planned':
            client.close()
            return False
            
        # Ausleihe aktivieren
        result = ausleihungen.update_one(
            {'_id': ObjectId(id)},
            {'$set': {
                'Status': 'active',
                'LastUpdated': datetime.datetime.now()
            }}
        )
        
        client.close()
        return result.modified_count > 0
    except Exception as e:
        return False


# === KOMPATIBILITÄTSFUNKTIONEN ===

# Hilfsmethoden für alte Funktionsaufrufe, um Abwärtskompatibilität zu gewährleisten

def add_planned_booking(item_id, user, start_date, end_date, notes="", period=None):
    """Kompatibilitätsfunktion - erstellt eine geplante Ausleihe"""
    return add_ausleihung(item_id, user, start_date, end_date, notes, status='planned', period=period)

def check_booking_conflict(item_id, start_date, end_date, period=None):
    """Kompatibilitätsfunktion - prüft auf Ausleihungskonflikte mit Periodenunterstützung"""
    return check_ausleihung_conflict(item_id, start_date, end_date, period)

def cancel_booking(booking_id):
    """Kompatibilitätsfunktion - storniert eine Ausleihe"""
    return cancel_ausleihung(booking_id)

def get_booking(booking_id):
    """Kompatibilitätsfunktion - ruft eine einzelne Ausleihe ab"""
    return get_ausleihung(booking_id)

def get_active_bookings(start=None, end=None):
    """Kompatibilitätsfunktion - ruft aktive Ausleihungen ab"""
    return get_active_ausleihungen(start, end)

def get_planned_bookings(start=None, end=None):
    """Kompatibilitätsfunktion - ruft geplante Ausleihungen ab"""
    return get_planned_ausleihungen(start, end)

def get_completed_bookings(start=None, end=None):
    """Kompatibilitätsfunktion - ruft abgeschlossene Ausleihungen ab"""
    return get_completed_ausleihungen(start, end)

def mark_booking_active(booking_id, ausleihung_id=None):
    """Kompatibilitätsfunktion - markiert eine Ausleihe als aktiv und verknüpft optional eine Ausleihungs-ID"""
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        
        # Basisupdate-Daten mit Status-Änderung
        update_data = {
            'Status': 'active',
            'LastUpdated': datetime.datetime.now()
        }
        
        # Wenn eine Ausleihungs-ID angegeben wurde, diese auch verknüpfen
        if ausleihung_id:
            update_data['AusleihungId'] = ausleihung_id
            
        # Update durchführen
        result = ausleihungen.update_one(
            {'_id': ObjectId(booking_id)},
            {'$set': update_data}
        )
        
        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error activating booking: {e}")
        # Fallback zur alten Methode bei Fehlern
        return activate_ausleihung(booking_id)

def mark_booking_completed(booking_id):
    """Kompatibilitätsfunktion - markiert eine Ausleihe als abgeschlossen"""
    return complete_ausleihung(booking_id)

def get_bookings_starting_now(current_time):
    """Kompatibilitätsfunktion - ruft startende Ausleihungen ab"""

def get_bookings_starting_now(current_time):
    """Kompatibilitätsfunktion - ruft startende Ausleihungen ab"""
    return get_ausleihungen_starting_now(current_time)

def get_bookings_ending_now(current_time):
    """Kompatibilitätsfunktion - ruft endende Ausleihungen ab"""
    return get_ausleihungen_ending_now(current_time)




def reset_item_completely(item_id):
    """
    Setzt den Ausleihstatus eines Items vollständig zurück.
    
    Diese Funktion:
    - Markiert das Item als verfügbar
    - Löscht alle Ausleihungsinformationen
    - Setzt Exemplar-Status zurück
    - Beendet alle aktiven Ausleihungen
    
    Args:
        item_id (str): Die ID des Items das zurückgesetzt werden soll
        
    Returns:
        dict: Erfolg-/Fehlerstatus mit Details
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items_collection = db['items']
        ausleihungen_collection = db['ausleihungen']
        
        # Item abrufen
        item = items_collection.find_one({'_id': ObjectId(item_id)})
        if not item:
            return {'success': False, 'message': 'Item nicht gefunden'}
        
        item_name = item.get('Name', 'Unbekannt')
        
        # 1. Alle aktiven Ausleihungen für dieses Item beenden
        active_borrowings = ausleihungen_collection.find({
            'Item': item_id,
            'Status': {'$in': ['active', 'planned']}
        })
        
        completed_count = 0
        for borrowing in active_borrowings:
            ausleihungen_collection.update_one(
                {'_id': borrowing['_id']},
                {
                    '$set': {
                        'Status': 'completed',
                        'End': datetime.datetime.now(),
                        'LastUpdated': datetime.datetime.now(),
                        'CompletedBy': 'System Reset'
                    }
                }
            )
            completed_count += 1
        
        # 2. Item-Status zurücksetzen
        update_data = {
            'Verfuegbar': True,
            'LastUpdated': datetime.datetime.now()
        }
        
        # Entferne User-Zuordnung falls vorhanden
        if 'User' in item:
            update_data['$unset'] = {'User': ''}
        
        # Entferne BorrowerInfo falls vorhanden
        if 'BorrowerInfo' in item:
            if '$unset' not in update_data:
                update_data['$unset'] = {}
            update_data['$unset']['BorrowerInfo'] = ''
        
        # Setze ExemplareStatus zurück falls vorhanden
        if 'ExemplareStatus' in item:
            if '$unset' not in update_data:
                update_data['$unset'] = {}
            update_data['$unset']['ExemplareStatus'] = ''
        
        # Item aktualisieren
        result = items_collection.update_one(
            {'_id': ObjectId(item_id)},
            update_data
        )
        
        client.close()
        
        if result.modified_count > 0:
            return {
                'success': True,
                'message': f'Item "{item_name}" wurde erfolgreich zurückgesetzt',
                'details': {
                    'completed_borrowings': completed_count,
                    'item_reset': True
                }
            }
        else:
            return {
                'success': True,
                'message': f'Item "{item_name}" war bereits im korrekten Status',
                'details': {
                    'completed_borrowings': completed_count,
                    'item_reset': False
                }
            }
        
    except Exception as e:
        return {
            'success': False,
            'message': f'Fehler beim Zurücksetzen: {str(e)}'
        }