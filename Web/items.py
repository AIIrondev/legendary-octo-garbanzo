"""
Inventory Items Management
=========================

This module manages inventory items in the database. It provides comprehensive 
functionality for creating, updating, retrieving and filtering inventory items.

Key Features:
- Creating and updating inventory items
- Retrieving items by ID, name, or filters
- Managing item availability status
- Supporting images and categorization
- Retrieving filter/category values for UI components

Collection Structure:
- items: Stores all inventory item records with their metadata
  - Required fields: Name, Ort, Beschreibung
  - Optional fields: Images, Filter, Filter2, Filter3, Anschaffungsjahr, Anschaffungskosten, Code_4
  - Status fields: Verfuegbar, User (if currently borrowed)
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
import settings as cfg


LIBRARY_ITEM_TYPES = ('book', 'cd', 'dvd', 'media')


def _non_library_query(extra_query=None):
    """Build a query that excludes library media items from normal inventory."""
    base_query = {'ItemType': {'$nin': list(LIBRARY_ITEM_TYPES)}}
    if extra_query:
        base_query.update(extra_query)
    return base_query


# === ITEM MANAGEMENT ===

def add_item(name, ort, beschreibung, images=None, filter=None, filter2=None, filter3=None,
             ansch_jahr=None, ansch_kost=None, code_4=None, reservierbar=True,
             series_group_id=None, series_count=1, series_position=1,
             is_grouped_sub_item=False, parent_item_id=None,
             isbn=None, item_type='general'):
    """
    Add a new item to the inventory.
    
    Args:
        name (str): Name of the item
        ort (str): Location of the item
        beschreibung (str): Description of the item
        images (list, optional): List of image filenames for the item
        filter (str, optional): Primary filter/category for the item
        filter2 (str, optional): Secondary filter/category for the item
        filter3 (str, optional): Tertiary filter/category for the item
        ansch_jahr (int, optional): Year of acquisition
        ansch_kost (float, optional): Cost of acquisition
        code_4 (str, optional): 4-digit identification code
        reservierbar (bool, optional): Whether the item can be reserved in advance
        series_group_id (str, optional): Shared group id for same-type batch items
        series_count (int, optional): Total items in the created batch
        series_position (int, optional): Position inside the batch (1-based)
        is_grouped_sub_item (bool, optional): Whether this item is hidden as sub-item
        parent_item_id (str, optional): Parent item id if this is a sub-item
        
    Returns:
        ObjectId: ID of the new item or None if failed
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']

        # Set default values for optional parameters
        if images is None:
            images = []

        item = {
            'Name': name,
            'Ort': ort,
            'Beschreibung': beschreibung,
            'Images': images,
            'Verfuegbar': True,
            'Reservierbar': reservierbar,
            'Filter': filter,
            'Filter2': filter2,
            'Filter3': filter3,
            'Anschaffungsjahr': ansch_jahr,
            'Anschaffungskosten': ansch_kost,
            'Code_4': code_4,
            'ISBN': isbn,
            'ItemType': item_type,
            'SeriesGroupId': series_group_id,
            'SeriesCount': series_count,
            'SeriesPosition': series_position,
            'IsGroupedSubItem': is_grouped_sub_item,
            'ParentItemId': parent_item_id,
            'Created': datetime.datetime.now(),
            'LastUpdated': datetime.datetime.now()
        }
        result = items.insert_one(item)
        item_id = result.inserted_id

        client.close()
        return item_id
    except Exception as e:
        print(f"Error adding item: {e}")
        return None


def remove_item(id):
    """
    Remove an item from the inventory.
    
    Args:
        id (str): ID of the item to remove
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        result = items.delete_one({'_id': ObjectId(id)})
        client.close()
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error removing item: {e}")
        return False


def get_group_item_ids(id):
    """
    Resolve all item ids that belong to the same grouped series as the given item.

    For non-grouped items, this returns only the provided id.

    Args:
        id (str): ID of any item in the group

    Returns:
        list[str]: All related item IDs (including the parent item)
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']

        base_item = items.find_one({'_id': ObjectId(id)})
        if not base_item:
            client.close()
            return []

        resolved_ids = set()

        # Prefer SeriesGroupId because it represents the full logical group.
        series_group_id = base_item.get('SeriesGroupId')
        if series_group_id:
            for group_item in items.find({'SeriesGroupId': series_group_id}, {'_id': 1}):
                resolved_ids.add(str(group_item['_id']))
        else:
            resolved_ids.add(str(base_item['_id']))

            parent_item_id = base_item.get('ParentItemId')
            if parent_item_id:
                resolved_ids.add(str(parent_item_id))
                for sibling in items.find({'ParentItemId': str(parent_item_id), 'IsGroupedSubItem': True}, {'_id': 1}):
                    resolved_ids.add(str(sibling['_id']))
            else:
                for child in items.find({'ParentItemId': str(base_item['_id']), 'IsGroupedSubItem': True}, {'_id': 1}):
                    resolved_ids.add(str(child['_id']))

        client.close()
        return list(resolved_ids)
    except Exception as e:
        print(f"Error resolving group item IDs: {e}")
        return []


def update_item(id, name, ort, beschreibung, images=None, verfuegbar=True, 
                filter=None, filter2=None, filter3=None, ansch_jahr=None, ansch_kost=None, code_4=None, reservierbar=True,
                isbn=None, item_type='general'):
    """
    Update an existing inventory item.
    
    Args:
        id (str): ID of the item to update
        name (str): Name of the item
        ort (str): Location of the item
        beschreibung (str): Description of the item
        images (list, optional): List of image filenames for the item
        verfuegbar (bool, optional): Availability status of the item
        filter (str, optional): Primary filter/category for the item
        filter2 (str, optional): Secondary filter/category for the item
        filter3 (str, optional): Tertiary filter/category for the item
        ansch_jahr (int, optional): Year of acquisition
        ansch_kost (float, optional): Cost of acquisition
        code_4 (str, optional): 4-digit identification code
        reservierbar (bool, optional): Whether the item can be reserved in advance
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']

        # Set default values for optional parameters
        if images is None:
            images = []

        update_data = {
            'Name': name,
            'Ort': ort,
            'Beschreibung': beschreibung,
            'Images': images,
            'Verfuegbar': verfuegbar,
            'Reservierbar': reservierbar,
            'Filter': filter,
            'Filter2': filter2,
            'Filter3': filter3,
            'Anschaffungsjahr': ansch_jahr,
            'Anschaffungskosten': ansch_kost,
            'Code_4': code_4,
            'ISBN': isbn,
            'ItemType': item_type,
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


def update_item_status(id, verfuegbar, user=None):
    """
    Update the availability status of an inventory item.
    
    Args:
        id (str): ID of the item to update
        verfuegbar (bool): New availability status
        user (str, optional): Username of person who borrowed the item
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']

        update_data = {
            'Verfuegbar': verfuegbar,
            'LastUpdated': datetime.datetime.now()
        }

        if user is not None:
            update_data['User'] = user
        elif verfuegbar:
            # If item is being marked as available, clear the user field
            update_data['$unset'] = {'User': ""}

        result = items.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating item status: {e}")
        return False


def update_item_exemplare_status(id, exemplare_status):
    """
    Update the exemplar status of an inventory item.
    
    Args:
        id (str): ID of the item to update
        exemplare_status (list): List of status objects for each exemplar
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']

        update_data = {
            'ExemplareStatus': exemplare_status,
            'LastUpdated': datetime.datetime.now()
        }

        result = items.update_one(
            {'_id': ObjectId(id)},
            {'$set': update_data}
        )

        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating exemplar status: {e}")
        return False


def is_code_unique(code_4, exclude_id=None):
    """
    Check if a given code is unique (not used by any other item).
    
    Args:
        code_4 (str): The code to check
        exclude_id (str, optional): ID of item to exclude from the check (for edit operations)
        
    Returns:
        bool: True if code is unique, False if already in use
    """
    if not code_4 or code_4.strip() == "":
        # Empty codes are not considered unique
        return False
        
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    items = db['items']
    
    # Build query to find items with this code
    query = {'Code_4': code_4}
    
    # If we're editing an item, exclude it from the uniqueness check
    if exclude_id:
        query['_id'] = {'$ne': ObjectId(exclude_id)}
    
    # Check if any items with this code exist
    count = items.count_documents(query)
    
    client.close()
    return count == 0


# === ITEM RETRIEVAL ===

def get_items():
    """
    Retrieve all inventory items.
    
    Returns:
        list: List of all inventory item documents with string IDs
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        items_return = items.find(_non_library_query())
        items_list = []
        for item in items_return:
            item['_id'] = str(item['_id'])
            items_list.append(item)
        client.close()
        return items_list
    except Exception as e:
        print(f"Error retrieving items: {e}")
        return []


def get_available_items():
    """
    Retrieve all available inventory items.
    
    Returns:
        list: List of available inventory item documents with string IDs
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        items_return = items.find(_non_library_query({'Verfuegbar': True}))
        items_list = []
        for item in items_return:
            item['_id'] = str(item['_id'])
            items_list.append(item)
        client.close()
        return items_list
    except Exception as e:
        print(f"Error retrieving available items: {e}")
        return []


def get_borrowed_items():
    """
    Retrieve all currently borrowed inventory items.
    
    Returns:
        list: List of borrowed inventory item documents with string IDs
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        items_return = items.find(_non_library_query({'Verfuegbar': False}))
        items_list = []
        for item in items_return:
            item['_id'] = str(item['_id'])
            items_list.append(item)
        client.close()
        return items_list
    except Exception as e:
        print(f"Error retrieving borrowed items: {e}")
        return []


def get_item(id):
    """
    Retrieve a specific inventory item by its ID.
    
    Args:
        id (str): ID of the item to retrieve
        
    Returns:
        dict: The inventory item document or None if not found
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        item = items.find_one({'_id': ObjectId(id)})
        client.close()
        return item
    except Exception as e:
        print(f"Error retrieving item: {e}")
        return None


def get_item_by_name(name):
    """
    Retrieve a specific inventory item by its name.
    
    Args:
        name (str): Name of the item to retrieve
        
    Returns:
        dict: The inventory item document or None if not found
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        item = items.find_one({'Name': name})
        client.close()
        return item
    except Exception as e:
        print(f"Error retrieving item by name: {e}")
        return None


def get_items_by_filter(filter_value):
    """
    Retrieve inventory items matching a specific filter/category.
    
    Args:
        filter_value (str): Filter value to search for
        
    Returns:
        list: List of items matching the filter in primary, secondary, or tertiary category
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        
        # Use $or to find matches in any filter field
        query = _non_library_query({
            '$or': [
                {'Filter': filter_value},
                {'Filter2': filter_value},
                {'Filter3': filter_value}
            ]
        })
        
        results = list(items.find(query))
        client.close()
        
        # Convert ObjectId to string
        for item in results:
            item['_id'] = str(item['_id'])
            
        return results
    except Exception as e:
        print(f"Error retrieving items by filter: {e}")
        return []


def get_filters():
    """
    Retrieve all unique filter/category values from the inventory.
    
    Returns:
        list: Combined list of all primary, secondary and tertiary filter values
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        non_library = _non_library_query()
        filters = items.distinct('Filter', non_library)
        filters2 = items.distinct('Filter2', non_library)
        filters3 = items.distinct('Filter3', non_library)
        
        # Combine filters and remove None/empty values
        all_filters = [f for f in filters + filters2 + filters3 if f]
        
        # Remove duplicates while preserving order
        unique_filters = []
        for f in all_filters:
            if f not in unique_filters:
                unique_filters.append(f)
                
        client.close()
        return unique_filters
    except Exception as e:
        print(f"Error retrieving filters: {e}")
        return []


def get_primary_filters():
    """
    Retrieve all unique primary filter values.
    
    Returns:
        list: List of all primary filter values
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        filters = [f for f in items.distinct('Filter', _non_library_query()) if f]
        client.close()
        return filters
    except Exception as e:
        print(f"Error retrieving primary filters: {e}")
        return []


def get_secondary_filters():
    """
    Retrieve all unique secondary filter values.
    
    Returns:
        list: List of all secondary filter values
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        filters = [f for f in items.distinct('Filter2', _non_library_query()) if f]
        client.close()
        return filters
    except Exception as e:
        print(f"Error retrieving secondary filters: {e}")
        return []


def get_tertiary_filters():
    """
    Retrieve all unique tertiary filter values.
    
    Returns:
        list: List of all tertiary filter values
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        filters = [f for f in items.distinct('Filter3', _non_library_query()) if f]
        client.close()
        return filters
    except Exception as e:
        print(f"Error retrieving tertiary filters: {e}")
        return []


def get_item_by_code_4(code_4):
    """
    Retrieve inventory items matching a specific 4-digit code.
    
    Args:
        code_4 (str): 4-digit code to search for
        
    Returns:
        list: List of items matching the code
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        results = list(items.find(_non_library_query({"Code_4": code_4})))
        
        # Convert ObjectId to string
        for item in results:
            item['_id'] = str(item['_id'])
            
        client.close()
        return results
    except Exception as e:
        print(f"Error retrieving item by code: {e}")
        return []


# === MAINTENANCE FUNCTIONS ===

def unstuck_item(id):
    """
    Remove all borrowing records for a specific item to reset its status.
    Used to fix problematic or stuck items.
    
    Args:
        id (str): ID of the item to unstick
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        ausleihungen = db['ausleihungen']
        result = ausleihungen.delete_many({'Item': id})
        
        # Also reset the item status
        items = db['items']
        items.update_one(
            {'_id': ObjectId(id)},
            {
                '$set': {
                    'Verfuegbar': True,
                    'LastUpdated': datetime.datetime.now()
                },
                '$unset': {'User': ""}
            }
        )
        
        client.close()
        return True
    except Exception as e:
        print(f"Error unsticking item: {e}")
        return False


def get_predefined_filter_values(filter_num):
    """
    Get predefined values for a specific filter.
    
    Args:
        filter_num (int): Filter number (1 for Unterrichtsfach, 2 for Jahrgangsstufe)
        
    Returns:
        list: List of predefined filter values
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    
    # Use a dedicated collection for filter presets
    filter_presets = db['filter_presets']
    
    # Find the document for the specified filter
    filter_doc = filter_presets.find_one({'filter_num': filter_num})
    
    client.close()
    
    if filter_doc and 'values' in filter_doc:
        # Sort values alphabetically
        return sorted(filter_doc['values'])
    else:
        # Create empty document if it doesn't exist
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        filter_presets = db['filter_presets']
        filter_presets.update_one(
            {'filter_num': filter_num},
            {'$set': {'values': []}},
            upsert=True
        )
        client.close()
        return []

def add_predefined_filter_value(filter_num, value):
    """
    Add a new predefined value to a filter.
    
    Args:
        filter_num (int): Filter number (1 for Unterrichtsfach, 2 for Jahrgangsstufe)
        value (str): Value to add
        
    Returns:
        bool: True if value was added, False if it already existed
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    filter_presets = db['filter_presets']
    
    # Check if value already exists
    filter_doc = filter_presets.find_one({
        'filter_num': filter_num,
        'values': value
    })
    
    if filter_doc:
        # Value already exists
        client.close()
        return False
    
    # Add the value to the filter
    result = filter_presets.update_one(
        {'filter_num': filter_num},
        {'$push': {'values': value}},
        upsert=True
    )
    
    client.close()
    return result.modified_count > 0 or result.upserted_id is not None

def remove_predefined_filter_value(filter_num, value):
    """
    Remove a predefined value from a filter.
    
    Args:
        filter_num (int): Filter number (1 for Unterrichtsfach, 2 for Jahrgangsstufe)
        value (str): Value to remove
        
    Returns:
        bool: True if value was removed, False otherwise
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    filter_presets = db['filter_presets']
    
    # Remove the value from the filter
    result = filter_presets.update_one(
        {'filter_num': filter_num},
        {'$pull': {'values': value}}
    )
    
    client.close()
    return result.modified_count > 0


# === LOCATION MANAGEMENT ===

def get_predefined_locations():
    """
    Get list of all predefined locations/placement options.
    
    Returns:
        list: List of predefined location strings
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        
        # Check if settings collection exists, create if not
        if 'settings' not in db.list_collection_names():
            db.create_collection('settings')
        
        # Get settings document or create if it doesn't exist
        settings_collection = db['settings']
        location_settings = settings_collection.find_one({'setting_type': 'predefined_locations'})
        
        if not location_settings:
            # Create default settings document if it doesn't exist
            settings_collection.insert_one({
                'setting_type': 'predefined_locations',
                'locations': []
            })
            return []
        
        # Return the predefined locations
        locations = location_settings.get('locations', [])
        client.close()
        return sorted(locations)
        
    except Exception as e:
        print(f"Error getting predefined locations: {str(e)}")
        return []


def add_predefined_location(location):
    """
    Add a new predefined location.
    
    Args:
        location (str): Location to add
        
    Returns:
        bool: True if added successfully, False if already exists
    """
    if not location or not isinstance(location, str):
        return False
    
    location = location.strip()
    if not location:
        return False
        
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        settings_collection = db['settings']
        
        # Check if settings document exists, create if not
        location_settings = settings_collection.find_one({'setting_type': 'predefined_locations'})
        
        if not location_settings:
            # Create with the new location
            settings_collection.insert_one({
                'setting_type': 'predefined_locations',
                'locations': [location]
            })
            client.close()
            return True
        
        # Check if location already exists (case-insensitive)
        current_locations = location_settings.get('locations', [])
        if any(loc.lower() == location.lower() for loc in current_locations):
            client.close()
            return False
        
        # Add the new location
        settings_collection.update_one(
            {'setting_type': 'predefined_locations'},
            {'$push': {'locations': location}}
        )
        
        client.close()
        return True
        
    except Exception as e:
        print(f"Error adding predefined location: {str(e)}")
        return False


def remove_predefined_location(location):
    """
    Remove a predefined location.
    
    Args:
        location (str): Location to remove
        
    Returns:
        bool: True if removed successfully
    """
    if not location:
        return False
        
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        settings_collection = db['settings']
        
        result = settings_collection.update_one(
            {'setting_type': 'predefined_locations'},
            {'$pull': {'locations': location}}
        )
        
        client.close()
        return result.modified_count > 0
        
    except Exception as e:
        print(f"Error removing predefined location: {str(e)}")
        return False


def update_item_next_appointment(item_id, appointment_data):
    """
    Update an item with information about its next scheduled appointment.
    
    Args:
        item_id (str): ID of the item to update
        appointment_data (dict): Appointment information containing:
            - date: Date of the appointment
            - start_period: Start period number
            - end_period: End period number
            - user: Username who scheduled the appointment
            - notes: Optional notes
            - appointment_id: ID of the appointment booking
            
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        
        # Format the appointment data for storage
        # Ensure date is a datetime object for MongoDB storage
        appointment_date = appointment_data['date']
        if isinstance(appointment_date, datetime.date) and not isinstance(appointment_date, datetime.datetime):
            # Convert date to datetime for MongoDB compatibility
            appointment_date = datetime.datetime.combine(appointment_date, datetime.time())
        
        next_appointment = {
            'date': appointment_date,
            'end_date': appointment_data.get('end_date', appointment_date),
            'start_period': appointment_data['start_period'],
            'end_period': appointment_data['end_period'],
            'user': appointment_data['user'],
            'notes': appointment_data.get('notes', ''),
            'appointment_id': appointment_data['appointment_id'],
            'scheduled_at': datetime.datetime.now()
        }
        
        update_data = {
            'NextAppointment': next_appointment,
            'LastUpdated': datetime.datetime.now()
        }
        
        result = items.update_one(
            {'_id': ObjectId(item_id)},
            {'$set': update_data}
        )
        
        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating item next appointment: {e}")
        return False


def clear_item_next_appointment(item_id):
    """
    Clear the next appointment information from an item.
    
    Args:
        item_id (str): ID of the item to update
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        
        result = items.update_one(
            {'_id': ObjectId(item_id)},
            {'$unset': {'NextAppointment': ""}, '$set': {'LastUpdated': datetime.datetime.now()}}
        )
        
        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error clearing item next appointment: {e}")
        return False


def get_items_with_appointments():
    """
    Retrieve all items that have scheduled appointments.
    
    Returns:
        list: List of items with NextAppointment field
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        
        items_return = items.find({'NextAppointment': {'$exists': True}})
        items_list = []
        for item in items_return:
            item['_id'] = str(item['_id'])
            items_list.append(item)
        client.close()
        return items_list
    except Exception as e:
        print(f"Error retrieving items with appointments: {e}")
        return []

def get_current_status(item_id):
    """
    Retrieve the current status of an item, including availability and user.
    
    Args:
        item_id (str): ID of the item to check
        
    Returns:
        dict: Current status of the item or None if not found
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        items = db['items']
        
        item = items.find_one({'_id': ObjectId(item_id)}, {'Verfuegbar': 1, 'User': 1})
        
        if item:
            # Convert ObjectId to string for consistency
            item['_id'] = str(item['_id'])
            client.close()
            return item
        else:
            client.close()
            return None
    except Exception as e:
        print(f"Error retrieving current status: {e}")
        return None