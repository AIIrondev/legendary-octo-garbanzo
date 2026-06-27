"""
Push Notification Management System
Handles Web Push notifications for users via Service Workers
"""

import os
import json
import datetime
from bson import ObjectId
import requests
import hashlib
import logging

import Web.modules.database.settings as cfg
from Web.modules.database.settings import MongoClient
from Web.modules.inventarsystem.data_protection import encrypt_text, decrypt_text

logger = logging.getLogger(__name__)

# VAPID keys for push notifications
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', f'mailto:admin@{os.getenv("SERVER_NAME", "localhost")}')

VAPID_PRIVATE_PEM = os.path.join(os.path.dirname(__file__), 'vapid_private.pem')
VAPID_PUBLIC_PEM = os.path.join(os.path.dirname(__file__), 'vapid_public.pem')

# Auto-generate VAPID keys if none are provided
if not VAPID_PUBLIC_KEY or not VAPID_PRIVATE_KEY:
    try:
        from py_vapid import Vapid, b64urlencode
        from cryptography.hazmat.primitives import serialization
        
        vapid = Vapid()
        if not os.path.exists(VAPID_PRIVATE_PEM):
            vapid.generate_keys()
            vapid.save_key(VAPID_PRIVATE_PEM)
            vapid.save_public_key(VAPID_PUBLIC_PEM)
            logger.info("Auto-generated new VAPID keys")
        else:
            vapid = Vapid.from_file(VAPID_PRIVATE_PEM)
            
        raw_pub = vapid.public_key.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint
        )
        
        VAPID_PUBLIC_KEY = b64urlencode(raw_pub).decode('utf-8')
        VAPID_PRIVATE_KEY = VAPID_PRIVATE_PEM
    except Exception as e:
        logger.error(f'Could not load or generate VAPID keys: {e}')

# Push service endpoint (typically Firebase or Web Push Service)
FCM_API_KEY = os.getenv('FCM_API_KEY', '')  # Firebase API key


def _get_username_hash(username):
    """Generates a deterministic hash for database lookups."""
    if not username:
        return None
    return hashlib.sha256(username.encode('utf-8')).hexdigest()


def get_push_subscriptions_collection(db=None):
    """Get MongoDB push subscriptions collection"""
    if db is None:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
    return db['push_subscriptions']


def get_user_subscriptions(username):
    """
    Get all active push subscriptions for a user, decrypting data on the fly.
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        # Query using the deterministic hash, NOT the encrypted text directly
        user_hash = _get_username_hash(username)
        
        encrypted_subscriptions = list(subs_col.find({
            'UsernameHash': user_hash,
            'IsActive': True
        }))
        
        client.close()
        
        # Decrypt endpoints and keys before returning
        decrypted_subs = []
        for sub in encrypted_subscriptions:
            try:
                sub['Endpoint'] = decrypt_text(sub.get('Endpoint'))
                
                # Keys are stored as encrypted JSON strings
                decrypted_keys_str = decrypt_text(sub.get('Keys'))
                sub['Keys'] = json.loads(decrypted_keys_str) if decrypted_keys_str else {}
                
                decrypted_subs.append(sub)
            except Exception as e:
                logger.error(f"Failed to decrypt subscription payload for hash {user_hash}: {e}")
                
        return decrypted_subs
    except Exception as e:
        logger.error(f'Error getting push subscriptions for user: {e}')
        return []


def save_push_subscription(username, subscription_obj):
    """
    Save a new push subscription for a user with field-level encryption.
    """
    try:
        endpoint = subscription_obj.get('endpoint')
        if not endpoint:
            logger.warning('Invalid subscription object: missing endpoint')
            return False
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        # Create unique hash of subscription using plaintext data to avoid duplicates
        sub_hash = hashlib.shake_256(
            f"{username}:{endpoint}".encode('utf-8')
        ).hexdigest()
        
        # Check if subscription already exists by Hash
        existing = subs_col.find_one({
            'SubscriptionHash': sub_hash
        })
        
        if existing:
            subs_col.update_one(
                {'_id': existing['_id']},
                {'$set': {
                    'LastUsed': datetime.datetime.now(),
                    'IsActive': True
                }}
            )
            logger.info('Updated existing push subscription')
            client.close()
            return True
        
        # Format keys as JSON string for your encrypt_text module
        keys_str = json.dumps(subscription_obj.get('keys', {}))
        
        # Save new subscription, encrypting sensitive fields
        subscription_doc = {
            'UsernameHash': _get_username_hash(username),
            'Username': encrypt_text(username),
            'Endpoint': encrypt_text(endpoint),
            'Keys': encrypt_text(keys_str),
            'SubscriptionHash': sub_hash,
            'IsActive': True,
            'CreatedAt': datetime.datetime.now(),
            'LastUsed': datetime.datetime.now(),
            'UserAgent': subscription_obj.get('userAgent', ''),
        }
        
        subs_col.insert_one(subscription_doc)
        logger.info('Saved new encrypted push subscription')
        client.close()
        return True
        
    except Exception as e:
        logger.error(f'Error saving push subscription: {e}')
        return False


def remove_push_subscription(username, endpoint):
    """
    Remove a push subscription by making it inactive.
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        # Recreate the deterministic hash to find the specific subscription
        sub_hash = hashlib.shake_256(
            f"{username}:{endpoint}".encode('utf-8')
        ).hexdigest()
        
        result = subs_col.update_one(
            {'SubscriptionHash': sub_hash},
            {'$set': {'IsActive': False}}
        )
        
        client.close()
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f'Error removing push subscription: {e}')
        return False


def send_push_notification(username, title, body, icon=None, url='/', reference=None, tag='notification'):
    """
    Send a push notification to all user's subscriptions.
    """
    try:
        subscriptions = get_user_subscriptions(username)
        
        if not subscriptions:
            logger.debug('No active push subscriptions for user')
            return 0
        
        sent_count = 0
        
        for subscription in subscriptions:
            success = _send_to_subscription(
                subscription,
                title,
                body,
                icon,
                url,
                reference,
                tag
            )
            if success:
                sent_count += 1
            else:
                _mark_subscription_inactive(subscription['_id'])
        
        logger.info(f'Sent push notification: {sent_count}/{len(subscriptions)} subscriptions')
        return sent_count
        
    except Exception as e:
        logger.error(f'Error sending push notification: {e}')
        return 0


def _send_to_subscription(subscription, title, body, icon, url, reference, tag):
    """Send push notification to a specific decrypted subscription"""
    try:
        payload = {
            'title': title,
            'body': body,
            'icon': icon or '/static/img/logo-192x192.png',
            'badge': '/static/img/badge-72x72.png',
            'tag': tag,
            'url': url,
            'reference': reference or {},
        }
        
        if FCM_API_KEY and subscription.get('Endpoint', '').startswith('https://fcm.'):
            return _send_fcm_notification(subscription, payload)
        
        return _send_web_push_notification(subscription, payload)
        
    except Exception as e:
        logger.error(f'Error sending to subscription: {e}')
        return False


def _send_fcm_notification(subscription, payload):
    try:
        if not FCM_API_KEY:
            logger.warning('FCM_API_KEY not configured')
            return False
        
        fcm_payload = {
            'to': subscription['Endpoint'],
            'notification': {
                'title': payload['title'],
                'body': payload['body'],
                'icon': payload['icon'],
                'badge': payload['badge'],
                'tag': payload['tag'],
                'click_action': payload['url'],
            },
            'data': {
                'url': payload['url'],
                'type': payload.get('type', 'info'),
            }
        }
        
        headers = {
            'Authorization': f'key={FCM_API_KEY}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://fcm.googleapis.com/fcm/send',
            json=fcm_payload,
            headers=headers,
            timeout=10
        )
        
        return response.status_code == 200
        
    except Exception as e:
        logger.error(f'FCM notification error: {e}')
        return False


def _send_web_push_notification(subscription, payload):
    try:
        from pywebpush import webpush
        
        webpush(
            subscription_info={
                'endpoint': subscription['Endpoint'],
                'keys': subscription.get('Keys', {})
            },
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_SUBJECT},
            timeout=10,
            ttl=3600 
        )
        
        return True
        
    except ImportError:
        logger.warning('pywebpush not installed. pip install pywebpush')
        return False
    except Exception as e:
        logger.error(f'Web push error: {e}')
        return False


def _mark_subscription_inactive(subscription_id):
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        subs_col.update_one(
            {'_id': ObjectId(subscription_id)},
            {'$set': {'IsActive': False}}
        )
        client.close()
    except Exception as e:
        logger.error(f'Error marking subscription inactive: {e}')


def send_push_to_all_admins(title, body, icon=None, url='/', reference=None):
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users_col = db['users']
        
        admin_users = list(users_col.find(
            {'Admin': True},
            {'Username': 1}
        ))
        client.close()
        
        total_sent = 0
        for admin_doc in admin_users:
            sent = send_push_notification(
                admin_doc['Username'],
                title,
                body,
                icon,
                url,
                reference,
                tag='admin-notification'
            )
            total_sent += sent
        
        logger.info(f'Sent push to all admins: {total_sent} notifications')
        return total_sent
        
    except Exception as e:
        logger.error(f'Error sending push to admins: {e}')
        return 0


def cleanup_inactive_subscriptions():
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=30)
        
        result = subs_col.delete_many({
            'IsActive': False,
            'LastUsed': {'$lt': cutoff_date}
        })
        
        client.close()
        logger.info(f'Cleaned up {result.deleted_count} inactive subscriptions')
        return result.deleted_count
        
    except Exception as e:
        logger.error(f'Error cleaning up subscriptions: {e}')
        return 0


def ensure_push_subscriptions_collection():
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        subs_col.create_index('UsernameHash')
        subs_col.create_index([('UsernameHash', 1), ('IsActive', 1)])
        subs_col.create_index([('CreatedAt', 1)]) 
        subs_col.create_index('SubscriptionHash', unique=True)
        
        logger.info('Push subscriptions collection indexes created')
        client.close()
        
    except Exception as e:
        logger.error(f'Error ensuring push subscriptions collection: {e}')