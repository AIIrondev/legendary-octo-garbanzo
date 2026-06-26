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
import Web.modules.inventarsystem.data_protection as dp
from Web.modules.database.settings import MongoClient
from bson.objectid import ObjectId
import datetime 
import ast


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

def _decrypt_appointment(item):
    """Helper function to safely decrypt appointment fields back to their original types."""
    if not item:
        return item
    
    try:
        if 'user' in item and item['user']:
            item['user'] = dp.decrypt_text(item['user'])
        
        if 'note' in item and item['note']:
            item['note'] = dp.decrypt_text(item['note'])
            
        if 'title' in item and item['title']:
            item['title'] = dp.decrypt_text(item['title'])
            
        if 'mail' in item and item['mail']:
            decrypted_mail = dp.decrypt_text(item['mail'])
            try:
                item['mail'] = ast.literal_eval(decrypted_mail)
            except Exception:
                item['mail'] = decrypted_mail

        if 'custom_fields' in item and item['custom_fields']:
            item['custom_fields'] = [dp.decrypt_text(field) for field in item['custom_fields']]

        if 'slots_booked' in item and item['slots_booked']:
            # If it's a string, it was encrypted during an update execution
            if isinstance(item['slots_booked'], str):
                decrypted_slots = dp.decrypt_text(item['slots_booked'])
                try:
                    item['slots_booked'] = ast.literal_eval(decrypted_slots)
                except Exception:
                    item['slots_booked'] = decrypted_slots
    except Exception as e:
        print(f"Error during decryption: {e}")
        
    return item


def add(date_start: str, date_end: str, time_span: list, slots: int, slot_lenght: int, user: str, mail: list=[], note:str="", calendar_enabled: bool=False, title: str="", custom_fields: list = (), clients_p_slot: int=1):
    client = None
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
            'user': dp.encrypt_text(user.strip()),
            'mail': dp.encrypt_text(str(mail)),
            'note': dp.encrypt_text(note),
            'title': dp.encrypt_text(title),
            'custom_fields': [dp.encrypt_text(str(field)) for field in custom_fields],
            'calendar_enabled': bool(calendar_enabled),
            'clients_per_slot': clients_p_slot,
            'slots_booked': [],  # -> [(start_time, (names),(custom1, custom2,...)), ...]the list gets there indexes as the slot 1-defined so is can be counted without an extra variable
            'Created': datetime.datetime.now(),
            'LastUpdated': datetime.datetime.now()
        }
        result = items.insert_one(item)
        return result.inserted_id
    except Exception as e:
        print(f"Exception occurred in add: {e}")
        return None
    finally:
        if client:
            client.close()

def get_item(id):
    """Retrieve a specific appointment by its ID and decrypt it."""
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']
        item = items.find_one(_active_record_query({'_id': ObjectId(id)}))
        
        return _decrypt_appointment(item)
    except Exception as e:
        print(f"Error retrieving item: {e}")
        return None
    finally:
        if client:
            client.close()

def update(id, slots_used: list):
    """Update an existing appointment's booked slots securely."""
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        update_data = {
            'slots_booked': dp.encrypt_text(str(slots_used)),
            'LastUpdated': datetime.datetime.now()
        }

        result = items.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )

        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating item: {e}")
        return False
    finally:
        if client:
            client.close()

def remove_slot(id, date_start_time, name):
    """
    Remove a booked slot from an appointment's encrypted `slots_booked` list.
    
    Because the array is stored as an encrypted string blob, we must decrypt, 
    modify it in Python, and re-encrypt it.
    """
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        item = items.find_one({'_id': ObjectId(id)})
        if not item or 'slots_booked' not in item or not item['slots_booked']:
            return False

        try:
            decrypted_slots = dp.decrypt_text(item['slots_booked'])
            slots_list = ast.literal_eval(decrypted_slots)
        except Exception as e:
            print(f"Failed to decrypt or parse slots: {e}")
            return False

        # Structure format note: [(start_time, (names), (custom1, custom2...)), ...]
        updated_slots = []
        removed_any = False
        
        for slot in slots_list:
            slot_start = slot[0]
            slot_names = slot[1]
            

            if slot_start == date_start_time and (slot_names == name or name in slot_names):
                removed_any = True
                continue 
            updated_slots.append(slot)

        if not removed_any:
            return False 

        result = items.update_one(
            {'_id': ObjectId(id)},
            {
                '$set': {
                    'slots_booked': dp.encrypt_text(str(updated_slots)),
                    'LastUpdated': datetime.datetime.now()
                }
            }
        )

        return result.modified_count > 0
    except Exception as e:
        print(f"Error removing slot: {e}")
        return False
    finally:
        if client:
            client.close()


def remove(id):
    """
    Hard-delete an appointment plan by its ID.
    (Note: If your docstring mentions a soft-delete 'Deleted' flag, 
    change items.delete_one to items.update_one with {'$set': {'Deleted': True}})
    """
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        result = items.delete_one({'_id': ObjectId(id)})

        return result.deleted_count > 0
    except Exception as e:
        print(f"Error removing appointment: {e}")
        return False
    finally:
        if client:
            client.close()


def remove_done():
    """Remove all expired appointments whose end date is prior to today in a single call."""
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        today = datetime.date.today().strftime('%Y-%m-%d')

        result = items.delete_many(
            _active_record_query(
                {
                    'date_end': {'$lt': today},
                }
            )
        )

        return result.deleted_count > 0
    except Exception as e:
        print(f"Error cleaning up finished appointments: {e}")
        return False
    finally:
        if client:
            client.close()


def get_upcoming_for_user(user: str, limit: int = 25):
    """Return upcoming appointment plans for a user, matching by encrypted username."""
    try:
        if hasattr(globals(), 'remove_done'):
            remove_done()
    except Exception:
        pass

    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        items = db['appointments']

        today = datetime.date.today().strftime('%Y-%m-%d')

        cursor = items.find(
            _active_record_query(
                {
                    'user': user,
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

        return results
    except Exception as e:
        print(f"Error retrieving upcoming appointments: {e}")
        return []
    finally:
        if client:
            client.close()