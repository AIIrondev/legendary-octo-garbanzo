'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
"""
Centralized settings module to load configuration from config.json and provide
defaults for the web application and helper modules.
"""
import os
import json
import atexit
from threading import Lock
from flask import has_request_context
from pymongo import MongoClient as _PyMongoClient

# Base directory of this Web package
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Default values
DEFAULTS = {
    'version': '2.6.5',
    'debug': False,
    'secret_key': 'Hsse783942h2342f342342i34hwebf8',
    'host': '0.0.0.0',
    'port': 443,
    'mongodb': {
        'host': 'localhost',
        'port': 27017,
        'db': 'Inventarsystem',
    },
    'scheduler': {
        'interval_minutes': 1,
        'backup_interval_hours': 24,
        'enabled': True,
    },
    'ssl': {
        'enabled': False,
        'cert': 'ssl_certs/cert.pem',
        'key': 'ssl_certs/key.pem',
    },
    'images': {
        'thumbnail_size': [150, 150],
        'preview_size': [400, 400],
    },
    'upload': {
        'folder': os.path.join(BASE_DIR, 'uploads'),
        'thumbnail_folder': os.path.join(BASE_DIR, 'thumbnails'),
        'preview_folder': os.path.join(BASE_DIR, 'previews'),
        'qrcode_folder': os.path.join(BASE_DIR, 'QRCodes'),
        'max_size_mb': 10,
        'image_max_size_mb': 15,
        'video_max_size_mb': 100,
        'allowed_extensions': ['png', 'jpg', 'jpeg', 'gif']
    },
    'paths': {
        'backups': os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), 'backups'),
        'logs': os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), 'logs'),
        'deleted_archives': os.path.join(os.path.dirname(os.path.dirname(BASE_DIR)), 'deleted_archives'),
    },
    'school': {
        'name': 'Schulname',
        'address': 'Schulstraße 1',
        'postal_code': '00000',
        'city': 'Ort',
        'school_number': '000000',
        'it_admin': 'IT-Beauftragte oder IT-Beauftragter',
        'logo_path': '',
        'logo_thumb': '',
        'logo_thumb': '',
    },
    'schoolPeriods': {
        "1": {"start": "08:00", "end": "08:45", "label": "1. Stunde (08:00 - 08:45)"},
        "2": {"start": "08:45", "end": "09:30", "label": "2. Stunde (08:45 - 09:30)"},
        "3": {"start": "09:45", "end": "10:30", "label": "3. Stunde (09:45 - 10:30)"},
        "4": {"start": "10:30", "end": "11:15", "label": "4. Stunde (10:30 - 11:15)"},
        "5": {"start": "11:30", "end": "12:15", "label": "5. Stunde (11:30 - 12:15)"},
        "6": {"start": "12:15", "end": "13:00", "label": "6. Stunde (12:15 - 13:00)"},
        "7": {"start": "13:30", "end": "14:15", "label": "7. Stunde (13:30 - 14:15)"},
        "8": {"start": "14:15", "end": "15:00", "label": "8. Stunde (14:15 - 15:00)"},
        "9": {"start": "15:15", "end": "16:00", "label": "9. Stunde (15:15 - 16:00)"},
        "10": {"start": "16:00", "end": "16:45", "label": "10. Stunde (16:00 - 16:45)"}
    },
    'modules': {
        'inventory': {
            'enabled': True
        },
        'library': {
            'enabled': False
        },
        'student_cards': {
            'enabled': False,
            'default_borrow_days': 14,
            'max_borrow_days': 365
        }
    }
}

# Load configuration file
CONFIG_PATH = os.path.join(BASE_DIR, '..', 'config.json')
try:
    with open(CONFIG_PATH, 'r') as f:
        _conf = json.load(f)
except Exception:
    _conf = {}

# Helper to get nested values with defaults
def _get(conf, path, default):
    cur = conf
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def _get_bool_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _get_int_env(name, default):
    value = os.getenv(name)
    if value is None or not value.strip():
        return int(default)
    try:
        return int(value)
    except ValueError:
        return int(default)

# Expose settings
APP_VERSION = _get(_conf, ['ver'], DEFAULTS['version'])
DEBUG = _get_bool_env('INVENTAR_DEBUG', _get(_conf, ['dbg'], DEFAULTS['debug']))
SECRET_KEY = str(os.getenv('INVENTAR_SECRET_KEY', _get(_conf, ['key'], DEFAULTS['secret_key'])))
HOST = _get(_conf, ['host'], DEFAULTS['host'])
PORT = _get(_conf, ['port'], DEFAULTS['port'])

# Database
MONGODB_HOST = _get(_conf, ['mongodb', 'host'], DEFAULTS['mongodb']['host'])
MONGODB_PORT = _get(_conf, ['mongodb', 'port'], DEFAULTS['mongodb']['port'])
MONGODB_DB = _get(_conf, ['mongodb', 'db'], DEFAULTS['mongodb']['db'])
MONGODB_URI = _get(_conf, ['mongodb', 'uri'], '')

# Optional environment overrides for containerized/runtime deployments.
MONGODB_HOST = os.getenv('INVENTAR_MONGODB_HOST', MONGODB_HOST)
MONGODB_PORT = int(os.getenv('INVENTAR_MONGODB_PORT', str(MONGODB_PORT)))
MONGODB_DB = os.getenv('INVENTAR_MONGODB_DB', MONGODB_DB)
MONGODB_URI = os.getenv('INVENTAR_MONGODB_URI', os.getenv('MONGO_URI', MONGODB_URI))
if isinstance(MONGODB_URI, str):
    MONGODB_URI = MONGODB_URI.strip() or None
MONGODB_MAX_POOL_SIZE = _get_int_env('INVENTAR_MONGODB_MAX_POOL_SIZE', 20)
MONGODB_MIN_POOL_SIZE = _get_int_env('INVENTAR_MONGODB_MIN_POOL_SIZE', 0)
MONGODB_MAX_IDLE_TIME_MS = _get_int_env('INVENTAR_MONGODB_MAX_IDLE_TIME_MS', 300000)
MONGODB_CONNECT_TIMEOUT_MS = _get_int_env('INVENTAR_MONGODB_CONNECT_TIMEOUT_MS', 5000)
MONGODB_SERVER_SELECTION_TIMEOUT_MS = _get_int_env('INVENTAR_MONGODB_SERVER_SELECTION_TIMEOUT_MS', 5000)
MONGODB_SOCKET_TIMEOUT_MS = _get_int_env('INVENTAR_MONGODB_SOCKET_TIMEOUT_MS', 30000)
MONGODB_MAX_CONNECTING = _get_int_env('INVENTAR_MONGODB_MAX_CONNECTING', 2)

# Scheduler
SCHEDULER_INTERVAL_MIN = _get(_conf, ['scheduler', 'interval_minutes'], DEFAULTS['scheduler']['interval_minutes'])
BACKUP_INTERVAL_HOURS = _get(_conf, ['scheduler', 'backup_interval_hours'], DEFAULTS['scheduler']['backup_interval_hours'])
SCHEDULER_ENABLED = _get(_conf, ['scheduler', 'enabled'], DEFAULTS['scheduler']['enabled'])

# SSL
SSL_ENABLED = _get(_conf, ['ssl', 'enabled'], DEFAULTS['ssl']['enabled'])
SSL_CERT = _get(_conf, ['ssl', 'cert'], DEFAULTS['ssl']['cert'])
SSL_KEY = _get(_conf, ['ssl', 'key'], DEFAULTS['ssl']['key'])

# School periods
SCHOOL_PERIODS = _get(_conf, ['schoolPeriods'], DEFAULTS['schoolPeriods'])
SCHOOL_INFO_DEFAULT = _get(_conf, ['school'], DEFAULTS['school'])

# Optional feature modules
TENANT_CONFIGS = _get(_conf, ['tenants'], {})


class _TenantAwareBool:
    def __init__(self, module_name, default):
        self.module_name = module_name
        self.default = bool(default)

    def resolve(self):
        try:
            from tenant import is_tenant_module_enabled
            return bool(is_tenant_module_enabled(self.module_name, default=self.default))
        except Exception:
            return self.default

    def __bool__(self):
        return self.resolve()

    def __int__(self):
        return int(self.resolve())

    def __str__(self):
        return 'True' if self.resolve() else 'False'

    def __repr__(self):
        return f"_TenantAwareBool(module_name={self.module_name!r}, value={self.resolve()!r})"


from module_registry import registry as MODULES

INVENTORY_MODULE_ENABLED = _TenantAwareBool('inventory', _get(_conf, ['modules', 'inventory', 'enabled'], DEFAULTS['modules']['inventory']['enabled']))
LIBRARY_MODULE_ENABLED = _TenantAwareBool('library', _get(_conf, ['modules', 'library', 'enabled'], DEFAULTS['modules']['library']['enabled']))
STUDENT_CARDS_MODULE_ENABLED = _TenantAwareBool('student_cards', _get(_conf, ['modules', 'student_cards', 'enabled'], DEFAULTS['modules']['student_cards']['enabled']))

def _match_inventory(path):
    if not path: return False
    if path == '/' or path.startswith('/home'): return True
    return path.startswith(('/scanner', '/inventory', '/upload_admin', '/manage_filters', '/manage_locations', '/admin_borrowings', '/admin_damaged_items', '/admin/borrowings', '/admin/damaged_items', '/terminplan'))

def _match_library(path):
    if not path: return False
    return path.startswith(('/library', '/library_', '/student_cards'))

def _match_student_cards(path):
    if not path: return False
    return path.startswith(('/student_cards'))

# Register core modules into the pipeline
MODULES.register('inventory', INVENTORY_MODULE_ENABLED, _match_inventory)
MODULES.register('library', LIBRARY_MODULE_ENABLED, _match_library)
MODULES.register('student_cards', STUDENT_CARDS_MODULE_ENABLED, _match_student_cards)

STUDENT_DEFAULT_BORROW_DAYS = int(_get(_conf, ['modules', 'student_cards', 'default_borrow_days'], DEFAULTS['modules']['student_cards']['default_borrow_days']))
STUDENT_MAX_BORROW_DAYS = int(_get(_conf, ['modules', 'student_cards', 'max_borrow_days'], DEFAULTS['modules']['student_cards']['max_borrow_days']))

# Upload/paths
ALLOWED_EXTENSIONS = set(_get(_conf, ['allowed_extensions'], DEFAULTS['upload']['allowed_extensions']))
UPLOAD_FOLDER = _get(_conf, ['upload', 'folder'], DEFAULTS['upload']['folder'])
THUMBNAIL_FOLDER = _get(_conf, ['upload', 'thumbnail_folder'], DEFAULTS['upload']['thumbnail_folder'])
PREVIEW_FOLDER = _get(_conf, ['upload', 'preview_folder'], DEFAULTS['upload']['preview_folder'])
QR_CODE_FOLDER = _get(_conf, ['upload', 'qrcode_folder'], DEFAULTS['upload']['qrcode_folder'])

# Normalize to absolute paths to avoid cwd issues
if not os.path.isabs(UPLOAD_FOLDER):
    UPLOAD_FOLDER = os.path.join(BASE_DIR, os.path.relpath(UPLOAD_FOLDER, BASE_DIR))
if not os.path.isabs(THUMBNAIL_FOLDER):
    THUMBNAIL_FOLDER = os.path.join(BASE_DIR, os.path.relpath(THUMBNAIL_FOLDER, BASE_DIR))
if not os.path.isabs(PREVIEW_FOLDER):
    PREVIEW_FOLDER = os.path.join(BASE_DIR, os.path.relpath(PREVIEW_FOLDER, BASE_DIR))
if not os.path.isabs(QR_CODE_FOLDER):
    QR_CODE_FOLDER = os.path.join(BASE_DIR, os.path.relpath(QR_CODE_FOLDER, BASE_DIR))
MAX_UPLOAD_MB = _get(_conf, ['upload', 'max_size_mb'], DEFAULTS['upload']['max_size_mb'])
IMAGE_MAX_UPLOAD_MB = _get(_conf, ['upload', 'image_max_size_mb'], DEFAULTS['upload']['image_max_size_mb'])
VIDEO_MAX_UPLOAD_MB = _get(_conf, ['upload', 'video_max_size_mb'], DEFAULTS['upload']['video_max_size_mb'])

THUMBNAIL_SIZE_LIST = _get(_conf, ['images', 'thumbnail_size'], DEFAULTS['images']['thumbnail_size'])
PREVIEW_SIZE_LIST = _get(_conf, ['images', 'preview_size'], DEFAULTS['images']['preview_size'])
THUMBNAIL_SIZE = (int(THUMBNAIL_SIZE_LIST[0]), int(THUMBNAIL_SIZE_LIST[1])) if isinstance(THUMBNAIL_SIZE_LIST, (list, tuple)) else (150, 150)
PREVIEW_SIZE = (int(PREVIEW_SIZE_LIST[0]), int(PREVIEW_SIZE_LIST[1])) if isinstance(PREVIEW_SIZE_LIST, (list, tuple)) else (400, 400)

BACKUP_FOLDER = _get(_conf, ['paths', 'backups'], DEFAULTS['paths']['backups'])
LOGS_FOLDER = _get(_conf, ['paths', 'logs'], DEFAULTS['paths']['logs'])
DELETED_ARCHIVE_FOLDER = _get(_conf, ['paths', 'deleted_archives'], DEFAULTS['paths']['deleted_archives'])

# Optional environment overrides for writable storage mounts.
BACKUP_FOLDER = os.getenv('INVENTAR_BACKUP_FOLDER', BACKUP_FOLDER)
LOGS_FOLDER = os.getenv('INVENTAR_LOGS_FOLDER', LOGS_FOLDER)
DELETED_ARCHIVE_FOLDER = os.getenv('INVENTAR_DELETED_ARCHIVE_FOLDER', DELETED_ARCHIVE_FOLDER)

# Normalize backup and logs paths to absolute paths (similar to upload folders) to avoid
# permission issues caused by relative paths resolving to unintended working dirs.
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
if not os.path.isabs(BACKUP_FOLDER):
    BACKUP_FOLDER = os.path.join(PROJECT_ROOT, BACKUP_FOLDER)
if not os.path.isabs(LOGS_FOLDER):
    LOGS_FOLDER = os.path.join(PROJECT_ROOT, LOGS_FOLDER)
if not os.path.isabs(DELETED_ARCHIVE_FOLDER):
    DELETED_ARCHIVE_FOLDER = os.path.join(PROJECT_ROOT, DELETED_ARCHIVE_FOLDER)

# Optional key for field/file encryption at application level.
DATA_ENCRYPTION_KEY = os.getenv('INVENTAR_DATA_ENCRYPTION_KEY', '').strip()


_MONGO_CLIENT_CACHE = {}
_MONGO_CLIENT_LOCK = Lock()


class _MongoClientProxy:
    def __init__(self, client):
        self._client = client

    def __getattr__(self, name):
        return getattr(self._client, name)

    def __getitem__(self, name):
        if has_request_context():
            try:
                from tenant import get_tenant_context
                ctx = get_tenant_context()
                if ctx and ctx.db_name:
                    if name == MONGODB_DB or name == MONGODB_DB.lower() or name == 'inventar_default':
                        return self._client[ctx.db_name]
            except Exception:
                pass
        return self._client[name]

    def get_database(self, name=None, *args, **kwargs):
        if has_request_context():
            try:
                from tenant import get_tenant_context
                ctx = get_tenant_context()
                if ctx and ctx.db_name:
                    if name is None or name == MONGODB_DB or name == MONGODB_DB.lower() or name == 'inventar_default':
                        return self._client.get_database(ctx.db_name, *args, **kwargs)
            except Exception:
                pass
        return self._client.get_database(name, *args, **kwargs)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def close(self):
        return None


def _close_cached_mongo_clients():
    with _MONGO_CLIENT_LOCK:
        clients = list(_MONGO_CLIENT_CACHE.values())
        _MONGO_CLIENT_CACHE.clear()

    for proxy in clients:
        try:
            proxy._client.close()
        except Exception:
            pass


atexit.register(_close_cached_mongo_clients)


def MongoClient(*args, **kwargs):
    """Return a process-local MongoDB client configured from this settings module."""
    explicit_host = 'host' in kwargs
    explicit_port = 'port' in kwargs
    host = args[0] if len(args) >= 1 else kwargs.pop('host', MONGODB_HOST)
    port = args[1] if len(args) >= 2 else kwargs.pop('port', MONGODB_PORT)
    client_kwargs = {
        'maxPoolSize': MONGODB_MAX_POOL_SIZE,
        'minPoolSize': MONGODB_MIN_POOL_SIZE,
        'maxIdleTimeMS': MONGODB_MAX_IDLE_TIME_MS,
        'connectTimeoutMS': MONGODB_CONNECT_TIMEOUT_MS,
        'serverSelectionTimeoutMS': MONGODB_SERVER_SELECTION_TIMEOUT_MS,
        'socketTimeoutMS': MONGODB_SOCKET_TIMEOUT_MS,
        'maxConnecting': MONGODB_MAX_CONNECTING,
        'retryWrites': True,
        'retryReads': True,
    }
    client_kwargs.update(kwargs)

    if MONGODB_URI and len(args) == 0 and not explicit_host and not explicit_port:
        mongo_args = (MONGODB_URI,)
    elif len(args) >= 2 and not explicit_host and not explicit_port:
        mongo_args = args
    else:
        mongo_args = (host, port)

    cache_key = (
        mongo_args,
        tuple(sorted((key, repr(value)) for key, value in client_kwargs.items())),
    )

    with _MONGO_CLIENT_LOCK:
        cached_client = _MONGO_CLIENT_CACHE.get(cache_key)
        if cached_client is not None:
            return cached_client

        client = _PyMongoClient(*mongo_args, **client_kwargs)

        cached_client = _MongoClientProxy(client)
        _MONGO_CLIENT_CACHE[cache_key] = cached_client
        return cached_client


def get_school_info():
    """Return the tenant-scoped school metadata used for PDFs and admin views."""
    school_info = dict(SCHOOL_INFO_DEFAULT)
    client = None
    try:
        client = MongoClient(MONGODB_HOST, MONGODB_PORT)
        db = client[MONGODB_DB]
        if 'settings' not in db.list_collection_names():
            return school_info

        settings_collection = db['settings']
        settings_document = settings_collection.find_one({'setting_type': 'school_info'})
        if not settings_document:
            return school_info

        configured_school = settings_document.get('school', {})
        if isinstance(configured_school, dict):
            for key, value in configured_school.items():
                if value is not None:
                    school_info[key] = value
        return school_info
    except Exception:
        return school_info
    finally:
        if client:
            client.close()


def update_school_info(school_info):
    """Persist tenant-scoped school metadata into MongoDB and refresh the in-memory cache."""
    if not isinstance(school_info, dict):
        raise TypeError('school_info must be a dict')

    updated_school = dict(SCHOOL_INFO_DEFAULT)
    for key in updated_school.keys():
        value = school_info.get(key, updated_school[key])
        if value is None:
            value = ''
        updated_school[key] = str(value).strip()

    client = None
    try:
        client = MongoClient(MONGODB_HOST, MONGODB_PORT)
        db = client[MONGODB_DB]
        settings_collection = db['settings']
        settings_collection.update_one(
            {'setting_type': 'school_info'},
            {
                '$set': {
                    'setting_type': 'school_info',
                    'school': updated_school,
                }
            },
            upsert=True,
        )
    finally:
        if client:
            client.close()

    return dict(updated_school)
