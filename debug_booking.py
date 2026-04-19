#!/usr/bin/env python3
"""
Debug script to check why planned bookings are not being activated
"""
import sys
import os
import datetime
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Web'))

from pymongo import MongoClient
import settings as cfg
import ausleihung as au

def check_bookings():
    """Check all planned bookings and their status"""
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    ausleihungen = db['ausleihungen']
    
    # Get all planned bookings
    planned = list(ausleihungen.find({'Status': 'planned'}))
    
    print(f"\n📊 Gefundene GEPLANTE Ausleihen: {len(planned)}\n")
    print("=" * 100)
    
    current_time = datetime.datetime.now()
    print(f"⏰ Aktuelle Zeit: {current_time}\n")
    
    for booking in planned:
        booking_id = str(booking['_id'])
        user = booking.get('User', 'N/A')
        item = booking.get('Item', 'N/A')
        start = booking.get('Start')
        end = booking.get('End')
        period = booking.get('Period')
        status = booking.get('Status')
        
        print(f"\n🔹 Ausleihe ID: {booking_id}")
        print(f"   Benutzer: {user}")
        print(f"   Item: {item}")
        print(f"   Status: {status}")
        print(f"   Schulstunde/Periode: {period}")
        print(f"   Start: {start} (Typ: {type(start).__name__})")
        print(f"   Ende: {end} (Typ: {type(end).__name__})")
        
        # Check current status
        current_status = au.get_current_status(booking, log_changes=False)
        print(f"   ✓ Berechneter Status: {current_status}")
        
        if current_status != status:
            print(f"   ⚠️  STATUS STIMMT NICHT ÜBEREIN! Sollte sein: {current_status}")
        
        # Check time comparison
        if start:
            time_diff = (current_time - start).total_seconds()
            if time_diff < 0:
                print(f"   ⏳ Startet in: {abs(time_diff) / 60:.1f} Minuten")
            elif time_diff < 3600:
                print(f"   ✓ Sollte JETZT AKTIV sein! ({time_diff / 60:.1f} Minuten vorbei)")
            else:
                print(f"   ✓ Sollte schon {time_diff / 3600:.1f} Stunden aktiv sein!")
    
    print("\n" + "=" * 100)
    
    # Check active bookings too
    active = list(ausleihungen.find({'Status': 'active'}))
    print(f"\n✓ AKTIVE Ausleihen: {len(active)}")
    for booking in active:
        print(f"  - {booking.get('User', 'N/A')}: {booking.get('Item', 'N/A')} (Periode: {booking.get('Period')})")
    
    client.close()

if __name__ == '__main__':
    check_bookings()
