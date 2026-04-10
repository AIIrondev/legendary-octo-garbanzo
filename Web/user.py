"""
Module for managing user accounts and authentication.
Provides methods for creating, validating, and retrieving user information.
"""
'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
from pymongo import MongoClient
import hashlib
from bson.objectid import ObjectId
import settings as cfg


def normalize_student_card_id(card_id):
    """Normalize student card IDs for reliable lookup."""
    if card_id is None:
        return ''
    return str(card_id).strip().upper()


# === FAVORITES MANAGEMENT ===
def get_favorites(username):
    """Return a list of favorite item ObjectId strings for the user."""
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    user = users.find_one({'Username': username}) or users.find_one({'username': username})
    client.close()
    if not user:
        return []
    favs = user.get('favorites', [])
    # Normalize to strings
    return [str(f) for f in favs if f]

def add_favorite(username, item_id):
    """Add an item to user's favorites (idempotent)."""
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        users.update_one(
            {'$or': [{'Username': username}, {'username': username}]},
            {'$addToSet': {'favorites': ObjectId(item_id)}}
        )
        client.close()
        return True
    except Exception:
        return False

def remove_favorite(username, item_id):
    """Remove an item from user's favorites."""
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        users.update_one(
            {'$or': [{'Username': username}, {'username': username}]},
            {'$pull': {'favorites': ObjectId(item_id)}}
        )
        client.close()
        return True
    except Exception:
        return False



def check_password_strength(password):
    """
    Check if a password meets minimum security requirements.
    
    Args:
        password (str): Password to check
        
    Returns:
        bool: True if password is strong enough, False otherwise
    """
    if len(password) < 6:
        return False
    return True


def hashing(password):
    """
    Hash a password using SHA-512.
    
    Args:
        password (str): Password to hash
        
    Returns:
        str: Hexadecimal digest of the hashed password
    """
    return hashlib.sha512(password.encode()).hexdigest()


def check_nm_pwd(username, password):
    """
    Verify username and password combination.
    
    Args:
        username (str): Username to check
        password (str): Password to verify
        
    Returns:
        dict: User document if credentials are valid, None otherwise
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    hashed_password = hashlib.sha512(password.encode()).hexdigest()
    user = users.find_one({'Username': username, 'Password': hashed_password})
    client.close()
    return user


def add_user(username, password, name, last_name, is_student=False, student_card_id=None, max_borrow_days=None):
    """
    Add a new user to the database.
    
    Args:
        username (str): Username for the new user
        password (str): Password for the new user
        
    Returns:
        bool: True if user was added successfully, False if password was too weak
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    if not check_password_strength(password):
        return False
    user_doc = {
        'Username': username,
        'Password': hashing(password),
        'Admin': False,
        'active_ausleihung': None,
        'name': name,
        'last_name': last_name,
        'IsStudent': bool(is_student)
    }

    normalized_card = normalize_student_card_id(student_card_id)
    if bool(is_student):
        if normalized_card:
            user_doc['StudentCardId'] = normalized_card
        if max_borrow_days is not None:
            try:
                user_doc['MaxBorrowDays'] = int(max_borrow_days)
            except (TypeError, ValueError):
                pass

    users.insert_one(user_doc)
    client.close()
    return True


def student_card_exists(student_card_id):
    """Return True if a student card id is already assigned to a user."""
    normalized = normalize_student_card_id(student_card_id)
    if not normalized:
        return False
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    exists = users.find_one({'StudentCardId': normalized}) is not None
    client.close()
    return exists


def get_user_by_student_card(student_card_id):
    """Return user by student card id or None."""
    normalized = normalize_student_card_id(student_card_id)
    if not normalized:
        return None
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    found_user = users.find_one({'StudentCardId': normalized})
    client.close()
    return found_user


def make_admin(username):
    """
    Grant administrator privileges to a user.
    
    Args:
        username (str): Username of the user to promote
        
    Returns:
        bool: True if user was promoted successfully
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    users.update_one({'Username': username}, {'$set': {'Admin': True}})
    client.close()
    return True

def remove_admin(username):
    """
    Remove administrator privileges from a user.
    
    Args:
        username (str): Username of the user to demote
        
    Returns:
        bool: True if user was demoted successfully
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    users.update_one({'Username': username}, {'$set': {'Admin': False}})
    client.close()
    return True

def get_user(username):
    """
    Retrieve a specific user by username.
    
    Args:
        username (str): Username to search for
        
    Returns:
        dict: User document or None if not found
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    users_return = users.find_one({'Username': username})
    client.close()
    return users_return


def check_admin(username):
    """
    Check if a user has administrator privileges.
    
    Args:
        username (str): Username to check
        
    Returns:
        bool: True if user is an administrator, False otherwise
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    user = users.find_one({'Username': username})
    client.close()
    return user and user.get('Admin', False)


def update_active_ausleihung(username, id_item, ausleihung):
    """
    Update a user's active borrowing record.
    
    Args:
        username (str): Username of the user
        id_item (str): ID of the borrowed item
        ausleihung (str): ID of the borrowing record
        
    Returns:
        bool: True if successful
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    users.update_one({'Username': username}, {'$set': {'active_ausleihung': {'Item': id_item, 'Ausleihung': ausleihung}}})
    client.close()
    return True


def get_active_ausleihung(username):
    """
    Get a user's active borrowing record.
    
    Args:
        username (str): Username of the user
        
    Returns:
        dict: Active borrowing information or None
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    user = users.find_one({'Username': username})
    return user['active_ausleihung']


def has_active_borrowing(username):
    """
    Check if a user currently has an active borrowing.
    
    Args:
        username (str): Username to check
        
    Returns:
        bool: True if user has an active borrowing, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        
        user = users.find_one({'username': username})
        if not user:
            user = users.find_one({'Username': username})
            
        if not user:
            client.close()
            return False
            
        has_active = user.get('active_borrowing', False)
        
        client.close()
        return has_active
    except Exception as e:
        return False


def delete_user(username):
    """
    Delete a user from the database.
    Administrative function for removing user accounts.
    
    Args:
        username (str): Username of the account to delete
        
    Returns:
        bool: True if user was deleted successfully, False otherwise
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    result = users.delete_one({'username': username})
    client.close()
    if result.deleted_count == 0:
        # Try with different field name
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        result = users.delete_one({'Username': username})
        client.close()
    
    return result.deleted_count > 0


def update_active_borrowing(username, item_id, status):
    """
    Update a user's active borrowing status.
    
    Args:
        username (str): Username of the user
        item_id (str): ID of the borrowed item or None if returning
        status (bool): True if borrowing, False if returning
        
    Returns:
        bool: True if successful, False on error
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        result = users.update_one(
            {'username': username}, 
            {'$set': {
                'active_borrowing': status,
                'borrowed_item': item_id if status else None
            }}
        )
        
        if result.matched_count == 0:
            result = users.update_one(
                {'Username': username}, 
                {'$set': {
                    'active_borrowing': status,
                    'borrowed_item': item_id if status else None
                }}
            )
            
        client.close()
        return result.modified_count > 0
    except Exception as e:
        return False


def get_name(username):
    """
    Retrieve the name that is assosiated with the username.

    Returns:
        str: String of name
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    user = users.find_one({'Username': username})
    name = user.get("name")
    return name


def get_last_name(username):
    """
    Retrieve the last_name that is assosiated with the username.

    Returns:
        str: String of last_name
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = client[cfg.MONGODB_DB]
    users = db['users']
    user = users.find_one({'Username': username})
    name = user.get("last_name")
    return name


def get_all_users():
    """
    Retrieve all users from the database.
    Administrative function for user management.
    
    Returns:
        list: List of all user documents
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        all_users = list(users.find())
        client.close()
        return all_users
    except Exception as e:
        return []

def update_password(username, new_password):
    """
    Update a user's password with a new one.
    
    Args:
        username (str): Username of the user
        new_password (str): New password to set
        
    Returns:
        bool: True if password was updated successfully, False otherwise
    """
    try:
        if not check_password_strength(new_password):
            return False
            
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        
        # Hash the new password
        hashed_password = hashing(new_password)
        
        # Update the user's password
        result = users.update_one(
            {'Username': username}, 
            {'$set': {'Password': hashed_password}}
        )
        
        client.close()
        return result.modified_count > 0
    except Exception as e:
        print(f"Error updating password: {e}")
        return False
 
def update_user_name(username, name, last_name):
    """
    Update a user's name and last name.

    Args:
        username (str): Username of the user
        name (str): New first name
        last_name (str): New last name

    Returns:
        bool: True if updated successfully, False otherwise
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users = db['users']
        
        result = users.update_one(
            {'Username': username}, 
            {'$set': {'name': name, 'last_name': last_name}}
        )
        
        client.close()
        return True
    except Exception as e:
        print(f"Error updating user name: {e}")
        return False
