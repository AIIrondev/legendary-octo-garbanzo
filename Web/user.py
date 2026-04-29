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
import hashlib
import copy
import logging
import re
import secrets
import string
from bson.objectid import ObjectId
import settings as cfg
from settings import MongoClient

logger = logging.getLogger('app')
logger.setLevel(logging.INFO)


def normalize_student_card_id(card_id):
    """Normalize student card IDs for reliable lookup."""
    if card_id is None:
        return ''
    return str(card_id).strip().upper()


def _clean_name_fragment(value):
    cleaned = re.sub(r'[^A-Za-zÄÖÜäöüß]', '', str(value or '').strip())
    if not cleaned:
        return ''
    replacements = {
        'ä': 'ae',
        'ö': 'oe',
        'ü': 'ue',
        'ß': 'ss',
        'Ä': 'Ae',
        'Ö': 'Oe',
        'Ü': 'Ue',
    }
    for old_char, new_char in replacements.items():
        cleaned = cleaned.replace(old_char, new_char)
    return cleaned


def _get_tenant_db(client):
    """Return the current tenant database for the request, or fall back to default."""
    try:
        from tenant import get_tenant_db
        return get_tenant_db(client)
    except Exception:
        return client[cfg.MONGODB_DB]


def build_name_synonym(first_name, last_name=''):
    """Build a deterministic, non-personalized short alias from 2 letters each."""
    first = _clean_name_fragment(first_name)
    last = _clean_name_fragment(last_name)

    if first and last:
        return (first[:2] + last[:2]).title()

    combined = (first + last)
    if not combined:
        return 'User'
    return combined[:4].title()


def build_username_from_name(first_name, last_name=''):
    """
    Build a deterministic username abbreviation from first and last name.
    Uses 2 letters from each name and stores it lowercase.
    
    Args:
        first_name (str): First name
        last_name (str): Last name (optional)
        
    Returns:
        str: Generated username
    """
    alias = build_name_synonym(first_name, last_name)
    return alias.lower()


def build_unique_username_from_name(first_name, last_name=''):
    """
    Build a unique username from the first 2 letters of the first name and
    the first 2 letters of the last name.
    """
    first = _clean_name_fragment(first_name)
    last = _clean_name_fragment(last_name)
    base_username = (first[:2] + last[:2]).lower()

    if not base_username:
        base_username = 'user'

    if not get_user(base_username):
        return base_username

    suffix = 2
    while get_user(f"{base_username}{suffix}"):
        suffix += 1
    return f"{base_username}{suffix}"


ACTION_PERMISSION_KEYS = (
    'can_borrow',
    'can_insert',
    'can_edit',
    'can_delete',
    'can_manage_users',
    'can_manage_settings',
    'can_view_logs',
)

DEFAULT_ACTION_PERMISSIONS = {
    'can_borrow': True,
    'can_insert': False,
    'can_edit': False,
    'can_delete': False,
    'can_manage_users': False,
    'can_manage_settings': False,
    'can_view_logs': False,
}

DEFAULT_PAGE_PERMISSIONS = {
    'home': True,
    'tutorial_page': True,
    'my_borrowed_items': True,
    'notifications_view': True,
    'impressum': True,
    'license': True,
    'library_view': True,
    'terminplan': True,
    'home_admin': False,
    'upload_admin': False,
    'library_admin': False,
    'admin_borrowings': False,
    'library_loans_admin': False,
    'admin_damaged_items': False,
    'admin_audit_dashboard': False,
    'logs': False,
    'user_del': False,
    'register': False,
    'manage_filters': False,
    'manage_locations': False,
}

PERMISSION_PRESETS = {
    'standard_user': {
        'label': 'Standard (Ausleihe)',
        'actions': {
            'can_borrow': True,
        },
        'pages': {
            'home': True,
            'tutorial_page': True,
            'my_borrowed_items': True,
            'notifications_view': True,
            'impressum': True,
            'license': True,
            'library_view': True,
            'terminplan': True,
        },
    },
    'editor': {
        'label': 'Editor (Einfügen/Bearbeiten)',
        'actions': {
            'can_borrow': True,
            'can_insert': True,
            'can_edit': True,
        },
        'pages': {
            'home': True,
            'tutorial_page': True,
            'my_borrowed_items': True,
            'notifications_view': True,
            'impressum': True,
            'license': True,
            'library_view': True,
            'terminplan': True,
            'upload_admin': True,
            'library_admin': True,
        },
    },
    'manager': {
        'label': 'Manager (inkl. Löschen)',
        'actions': {
            'can_borrow': True,
            'can_insert': True,
            'can_edit': True,
            'can_delete': True,
            'can_manage_settings': True,
            'can_view_logs': True,
        },
        'pages': {
            'home': True,
            'tutorial_page': True,
            'my_borrowed_items': True,
            'notifications_view': True,
            'impressum': True,
            'license': True,
            'library_view': True,
            'terminplan': True,
            'home_admin': True,
            'upload_admin': True,
            'library_admin': True,
            'admin_borrowings': True,
            'library_loans_admin': True,
            'admin_damaged_items': True,
            'admin_audit_dashboard': True,
            'logs': True,
            'manage_filters': True,
            'manage_locations': True,
        },
    },
    'full_access': {
        'label': 'Vollzugriff',
        'actions': {
            'can_borrow': True,
            'can_insert': True,
            'can_edit': True,
            'can_delete': True,
            'can_manage_users': True,
            'can_manage_settings': True,
            'can_view_logs': True,
        },
        'pages': {
            'home': True,
            'tutorial_page': True,
            'my_borrowed_items': True,
            'notifications_view': True,
            'impressum': True,
            'license': True,
            'library_view': True,
            'terminplan': True,
            'home_admin': True,
            'upload_admin': True,
            'library_admin': True,
            'admin_borrowings': True,
            'library_loans_admin': True,
            'admin_damaged_items': True,
            'admin_audit_dashboard': True,
            'logs': True,
            'user_del': True,
            'register': True,
            'manage_filters': True,
            'manage_locations': True,
        },
    },
}


def _normalize_bool_map(source, defaults):
    result = dict(defaults)
    if isinstance(source, dict):
        for key, value in source.items():
            result[str(key)] = bool(value)
    return result


def get_permission_preset_definitions():
    return copy.deepcopy(PERMISSION_PRESETS)


def build_default_permission_payload(preset_key='standard_user'):
    selected_key = preset_key if preset_key in PERMISSION_PRESETS else 'standard_user'
    preset = PERMISSION_PRESETS.get(selected_key, {})
    action_defaults = _normalize_bool_map(preset.get('actions', {}), DEFAULT_ACTION_PERMISSIONS)
    page_defaults = _normalize_bool_map(preset.get('pages', {}), DEFAULT_PAGE_PERMISSIONS)
    return {
        'preset': selected_key,
        'actions': action_defaults,
        'pages': page_defaults,
    }


def get_effective_permissions(username):
    user = get_user(username)
    if not user:
        return build_default_permission_payload('standard_user')

    # Admin users always have full access, independent of custom presets.
    if bool(user.get('Admin', False)):
        return build_default_permission_payload('full_access')

    preset_key = user.get('PermissionPreset') or 'standard_user'
    payload = build_default_permission_payload(preset_key)
    payload['actions'] = _normalize_bool_map(user.get('ActionPermissions', {}), payload['actions'])
    payload['pages'] = _normalize_bool_map(user.get('PagePermissions', {}), payload['pages'])
    return payload


def update_user_permissions(username, preset_key, action_permissions=None, page_permissions=None):
    selected_key = preset_key if preset_key in PERMISSION_PRESETS else 'standard_user'
    payload = build_default_permission_payload(selected_key)

    if isinstance(action_permissions, dict):
        for key, value in action_permissions.items():
            payload['actions'][str(key)] = bool(value)

    if isinstance(page_permissions, dict):
        for key, value in page_permissions.items():
            payload['pages'][str(key)] = bool(value)

    update_data = {
        'PermissionPreset': payload['preset'],
        'ActionPermissions': payload['actions'],
        'PagePermissions': payload['pages'],
    }

    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = _get_tenant_db(client)
    users = db['users']
    result = users.update_one({'Username': username}, {'$set': update_data})

    if result.matched_count == 0:
        result = users.update_one({'username': username}, {'$set': update_data})

    client.close()
    return result.matched_count > 0


# === FAVORITES MANAGEMENT ===
def get_favorites(username):
    """Return a list of favorite item ObjectId strings for the user."""
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
    if password is None:
        return False

    if len(password) < 12:
        return False

    has_lower = any(char.islower() for char in password)
    has_upper = any(char.isupper() for char in password)
    has_digit = any(char.isdigit() for char in password)
    has_symbol = any(not char.isalnum() for char in password)

    if not (has_lower and has_upper and has_digit and has_symbol):
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
    db_name = cfg.MONGODB_DB
    tenant_db = None
    ctx = None
    try:
        from tenant import get_tenant_context
        ctx = get_tenant_context()
        if ctx and ctx.tenant_id:
            tenant_db = ctx.db_name or ctx.resolve_tenant()
            db_name = tenant_db
    except Exception as exc:
        logger.exception(f"Failed to resolve tenant context in check_nm_pwd: {exc}")

    logger.info(
        "check_nm_pwd start: username=%r tenant=%r db=%r host=%r port=%r uri=%r",
        username,
        ctx.tenant_id if ctx else None,
        db_name,
        cfg.MONGODB_HOST,
        cfg.MONGODB_PORT,
        getattr(cfg, 'MONGODB_URI', None),
    )

    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    try:
        hashed_password = hashing(password)
        logger.info("check_nm_pwd password hash for username=%r: %s", username, hashed_password)

        db = client[db_name]
        users = db['users']
        user_record = users.find_one({'$or': [{'Username': username}, {'username': username}]})

        if user_record is None:
            try:
                available_dbs = client.list_database_names()
                logger.warning(
                    "No user document in tenant database %r for username=%r. Available databases=%s",
                    db_name,
                    username,
                    available_dbs,
                )
            except Exception as exc:
                logger.exception("Could not list databases during failed login check: %s", exc)
            return None

        logger.info("Found user document for username=%r in db=%r: %s", username, db_name, user_record)
        stored_password = user_record.get('Password') or user_record.get('password')
        if stored_password is None:
            logger.warning("User document for username=%r in db=%r has no password field", username, db_name)
            return None

        if stored_password != hashed_password:
            logger.warning(
                "Password mismatch for username=%r in db=%r: provided_hash=%s stored_hash=%s",
                username,
                db_name,
                hashed_password,
                stored_password,
            )
            return None

        return user_record
    finally:
        client.close()

    return None


def add_user(
    username,
    password,
    name='',
    last_name='',
    is_student=False,
    student_card_id=None,
    max_borrow_days=None,
    permission_preset='standard_user',
    action_permissions=None,
    page_permissions=None,
):
    """
    Add a new user to the database.
    
    Args:
        username (str): Username for the new user
        password (str): Password for the new user
        
    Returns:
        bool: True if user was added successfully, False if password was too weak
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = _get_tenant_db(client)
    users = db['users']
    if not check_password_strength(password):
        return False
    permission_defaults = build_default_permission_payload(permission_preset)
    if isinstance(action_permissions, dict):
        for key, value in action_permissions.items():
            permission_defaults['actions'][str(key)] = bool(value)
    if isinstance(page_permissions, dict):
        for key, value in page_permissions.items():
            permission_defaults['pages'][str(key)] = bool(value)

    alias_first = name if str(name or '').strip() else username
    alias_last = last_name if str(last_name or '').strip() else ''
    name_alias = build_name_synonym(alias_first, alias_last)

    user_doc = {
        'Username': username,
        'Password': hashing(password),
        'Admin': False,
        'active_ausleihung': None,
        'name': name_alias,
        'last_name': last_name.strip() if last_name else '',
        'IsStudent': bool(is_student),
        'PermissionPreset': permission_defaults['preset'],
        'ActionPermissions': permission_defaults['actions'],
        'PagePermissions': permission_defaults['pages'],
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
    db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
    users = db['users']
    result = users.update_one({'Username': username}, {'$set': {'Admin': True}})
    if result.matched_count == 0:
        result = users.update_one({'username': username}, {'$set': {'Admin': True}})
    client.close()
    return result.matched_count > 0

def remove_admin(username):
    """
    Remove administrator privileges from a user.
    
    Args:
        username (str): Username of the user to demote
        
    Returns:
        bool: True if user was demoted successfully
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    db = _get_tenant_db(client)
    users = db['users']
    result = users.update_one({'Username': username}, {'$set': {'Admin': False}})
    if result.matched_count == 0:
        result = users.update_one({'username': username}, {'$set': {'Admin': False}})
    client.close()
    return result.matched_count > 0

def get_user(username):
    """
    Retrieve a specific user by username.
    
    Args:
        username (str): Username to search for
        
    Returns:
        dict: User document or None if not found
    """
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    try:
        def find_in_db(database_name):
            db = client[database_name]
            users = db['users']
            return users.find_one({'Username': username}) or users.find_one({'username': username})

        # Try current tenant first when available
        try:
            from tenant import get_tenant_context
            ctx = get_tenant_context()
            if ctx and ctx.db_name:
                user = find_in_db(ctx.db_name)
                if user:
                    return user
        except Exception:
            pass

        # Fallback to default configured database
        user = find_in_db(cfg.MONGODB_DB)
        if user:
            return user

        return None
    finally:
        client.close()


def check_admin(username):
    """
    Check if a user has administrator privileges.
    
    Args:
        username (str): Username to check
        
    Returns:
        bool: True if user is an administrator, False otherwise
    """
    user = get_user(username)
    return bool(user and user.get('Admin', False))


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
    db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
    users = db['users']
    result = users.delete_one({'username': username})
    client.close()
    if result.deleted_count == 0:
        # Try with different field name
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
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
    db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
        db = _get_tenant_db(client)
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
        name_alias = build_name_synonym(name, last_name)
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = _get_tenant_db(client)
        users = db['users']
        
        result = users.update_one(
            {'Username': username}, 
            {'$set': {'name': name_alias, 'last_name': ''}}
        )
        
        client.close()
        return True
    except Exception as e:
        print(f"Error updating user name: {e}")
        return False
