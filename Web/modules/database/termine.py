"""
Apointment Managment
=========================

This module manages appointments in the database. It provides comprehensive 
functionality for creating, updating, retrieving appointments items.

Key Features:
- Creating and updating appointments
- Retrieving items by ID
- Managing time slots
- client retrival

Collection Structure:
- appointments:
  - Required fields: user, start_date, end_date, daytime, slots, slot_time
  - Optional fields: Images, Filter, Filter2, Filter3, Anschaffungsjahr, Anschaffungskosten, Code_4
  - Status fields: slots_used_by
"""
import Web.modules.database.settings as cfg
from Web.modules.database.settings import MongoClient
from bson.objectid import ObjectId
import datetime 


def _get_tenant_db(client):
    try:
        from tenant import get_tenant_db
        return get_tenant_db(client)
    except Exception:
        return client[cfg.MONGODB_DB]

def _active_record_query(extra_query=None):
    """Build a query that excludes logically deleted records."""
    base_query = {'Deleted': {'$ne': True}}
    if extra_query:
        base_query.update(extra_query)
    return base_query


def add(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str="", calendar_enabled: bool=False, title: str="", custom_fields: list = (), clients_p_slot: int=1):
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        item = {
            'date_start': date_start,
            'date_end': date_end,
            'time_span': time_span,
            'slots': slots,
            'slot_lenght': slot_lenght,
            'user': user,
            'mail': mail,
            'note': note,
            'title': title,
            'custom_fields': custom_fields, 
            'calendar_enabled': bool(calendar_enabled),
            'clients_per_slot': clients_p_slot,
            'slots_booked': [], # -> [(start_time, (names),(custom1, custom2,...)), ...]the list gets there indexes as the slot 1-defined so is can be counted without an extra variable
            'Created': datetime.datetime.now(),
            'LastUpdated': datetime.datetime.now()
        }
        result = items.insert_one(item)
        return result.inserted_id
    except Exception as e:
        print(f"Exception accured: {e}")


def get_item(id):
    """
    Retrieve a specific appointment by its ID.
    
    Args:
        id (str): ID of the appointsment to retrieve
        
    Returns:
        dict: The appointment document or None if not found
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']
        item = items.find_one(_active_record_query({'_id': ObjectId(id)}))
        client.close()
        return item
    except Exception as e:
        print(f"Error retrieving item: {e}")
        return None

def update(id,slots_used: list):
    """
    Update an existing appointment.
    
    Args:
        id (str): ID of the item to update
        
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        update_data = {
            'slots_booked': slots_used,
            'LastUpdated': datetime.datetime.now()
        }

        result = items.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating item: {e}")
        return False


def remove_slot(id, date_start_time, name):
    """
    Remove a booked slot from an appointment's `slots_booked`.

    Args:
        id (str): Appointment ID
        date_start_time: The start time value used when booking
        name (str): Name associated with the booking

    Returns:
        bool: True if a slot was removed, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        # Attempt to pull the exact element (stored as an array/tuple)
        result = items.update_one(
            {'_id': ObjectId(id)},
            {'$pull': {'slots_booked': [date_start_time, name]}}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error removing slot: {e}")
        return False


def remove(id):
    """
    Soft-delete an appointment by setting its `Deleted` flag.

    Args:
        id (str): Appointment ID

    Returns:
        bool: True if the appointment was marked deleted, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        result = items.delete_one({'_id': ObjectId(id)})

        client.close()
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error removing appointment: {e}")
        return False

def remove_done():
    """removose already finisched appointments"""
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        today = datetime.date.today().strftime('%Y-%m-%d')
        removed_count = 0

        cursor = items.find(
            _active_record_query(
                {
                    'date_end': {'$lt': today},
                }
            )
        ).sort('date_start', 1)

        for item in cursor:
            item['_id'] = str(item.get('_id'))
            result = items.delete_one({'_id': ObjectId(item['_id'])})
            removed_count += result.deleted_count
        
        client.close()
        return removed_count > 0
    except Exception as e:
        print(f"Error removing appointment: {e}")
        return False

def get_upcoming_for_user(user: str, limit: int = 25):
    """Return upcoming appointment plans for a user ordered by start date."""
    remove_done()
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        today = datetime.date.today().strftime('%Y-%m-%d')
        cursor = items.find(
            _active_record_query(
                {
                    'user': str(user or '').strip(),
                    'date_end': {'$gte': today},
                }
            )
        ).sort('date_start', 1)

        results = []
        for item in cursor:
            item['_id'] = str(item.get('_id'))
            results.append(item)
            if len(results) >= max(1, int(limit)):
                break

        client.close()
        return results
    except Exception as e:
        print(f"Error retrieving upcoming appointments: {e}")
        return []

 