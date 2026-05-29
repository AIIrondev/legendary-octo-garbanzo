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

def _active_record_query(extra_query=None):
    """Build a query that excludes logically deleted records."""
    base_query = {'Deleted': {'$ne': True}}
    if extra_query:
        base_query.update(extra_query)
    return base_query


def add(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str=""):
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
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
            'slots_booked': [], # -> [(start_time, name), ...]the list gets there indexes as the slot 1-defined so is can be counted without an extra variable
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
        db = client[cfg.MONGODB_DB]
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
        db = client[cfg.MONGODB_DB]
        items = db['appointments']

        update_data = {
            'slots_booked': [slots_used],
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

