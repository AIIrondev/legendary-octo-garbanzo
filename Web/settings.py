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

# Expose settings
APP_VERSION = _get(_conf, ['ver'], DEFAULTS['version'])
DEBUG = _get(_conf, ['dbg'], DEFAULTS['debug'])
SECRET_KEY = str(_get(_conf, ['key'], DEFAULTS['secret_key']))
HOST = _get(_conf, ['host'], DEFAULTS['host'])
PORT = _get(_conf, ['port'], DEFAULTS['port'])

# Database
MONGODB_HOST = _get(_conf, ['mongodb', 'host'], DEFAULTS['mongodb']['host'])
MONGODB_PORT = _get(_conf, ['mongodb', 'port'], DEFAULTS['mongodb']['port'])
MONGODB_DB = _get(_conf, ['mongodb', 'db'], DEFAULTS['mongodb']['db'])

# Optional environment overrides for containerized/runtime deployments.
MONGODB_HOST = os.getenv('INVENTAR_MONGODB_HOST', MONGODB_HOST)
MONGODB_PORT = int(os.getenv('INVENTAR_MONGODB_PORT', str(MONGODB_PORT)))
MONGODB_DB = os.getenv('INVENTAR_MONGODB_DB', MONGODB_DB)

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

# Optional feature modules
LIBRARY_MODULE_ENABLED = bool(_get(_conf, ['modules', 'library', 'enabled'], DEFAULTS['modules']['library']['enabled']))
STUDENT_CARDS_MODULE_ENABLED = bool(_get(_conf, ['modules', 'student_cards', 'enabled'], DEFAULTS['modules']['student_cards']['enabled']))
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

# Optional environment overrides for writable storage mounts.
BACKUP_FOLDER = os.getenv('INVENTAR_BACKUP_FOLDER', BACKUP_FOLDER)
LOGS_FOLDER = os.getenv('INVENTAR_LOGS_FOLDER', LOGS_FOLDER)

# Normalize backup and logs paths to absolute paths (similar to upload folders) to avoid
# permission issues caused by relative paths resolving to unintended working dirs.
PROJECT_ROOT = os.path.dirname(os.path.dirname(BASE_DIR))
if not os.path.isabs(BACKUP_FOLDER):
    BACKUP_FOLDER = os.path.join(PROJECT_ROOT, BACKUP_FOLDER)
if not os.path.isabs(LOGS_FOLDER):
    LOGS_FOLDER = os.path.join(PROJECT_ROOT, LOGS_FOLDER)
