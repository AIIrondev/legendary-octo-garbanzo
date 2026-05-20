'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
"""
Funktion zum Protokollieren von Statusänderungen bei Ausleihungen
"""
import os
import datetime
from bson.objectid import ObjectId

def log_status_change(ausleihung_id, old_status, new_status, user=None):
    """
    Protokolliert eine Statusänderung einer Ausleihung in einer Log-Datei.
    
    Args:
        ausleihung_id: Die ID der Ausleihung
        old_status: Der alte Status
        new_status: Der neue Status
        user: Der Benutzer, der die Änderung vorgenommen hat (optional)
    """
    try:
        # Erstelle Log-Verzeichnis, falls es nicht existiert
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs')
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Log-Datei für Statusänderungen
        log_file = os.path.join(log_dir, 'ausleihungen_status_changes.log')
        
        # Protokolliere die Änderung
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        user_info = f" by {user}" if user else ""
        
        with open(log_file, 'a', encoding='utf-8') as f:
            f.write(f"{timestamp}: Ausleihung {ausleihung_id} - Status changed from '{old_status}' to '{new_status}'{user_info}\n")
            
        return True
    except Exception as e:
        print(f"Fehler beim Protokollieren der Statusänderung: {e}")
        return False
