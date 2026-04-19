"""
Push Notification Management System
Handles Web Push notifications for users via Service Workers
"""

import os
import json
import datetime
from pymongo import MongoClient
from bson import ObjectId
import requests
import hashlib
import logging

import settings as cfg

logger = logging.getLogger(__name__)

# VAPID keys for push notifications (should be in environment variables)
VAPID_PUBLIC_KEY = os.getenv('VAPID_PUBLIC_KEY', '')
VAPID_PRIVATE_KEY = os.getenv('VAPID_PRIVATE_KEY', '')
VAPID_SUBJECT = os.getenv('VAPID_SUBJECT', f'mailto:admin@{os.getenv("SERVER_NAME", "localhost")}')

# Push service endpoint (typically Firebase or Web Push Service)
PUSH_SERVICE_URL = 'https://fcm.googleapis.com/fcm/send'  # Firebase Cloud Messaging
FCM_API_KEY = os.getenv('FCM_API_KEY', '')  # Firebase API key


def get_push_subscriptions_collection(db=None):
    """Get MongoDB push subscriptions collection"""
    if db is None:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
    return db['push_subscriptions']


def get_user_subscriptions(username):
    """
    Get all active push subscriptions for a user
    
    Args:
        username (str): Username
        
    Returns:
        list: List of subscription documents
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        subscriptions = list(subs_col.find({
            'Username': username,
            'IsActive': True
        }))
        
        client.close()
        return subscriptions
    except Exception as e:
        logger.error(f'Error getting push subscriptions for {username}: {e}')
        return []


def save_push_subscription(username, subscription_obj):
    """
    Save a new push subscription for a user
    
    Args:
        username (str): Username
        subscription_obj (dict): Subscription object from Service Worker
        {
            'endpoint': 'https://...',
            'keys': {
                'p256dh': '...',
                'auth': '...'
            }
        }
        
    Returns:
        bool: Success status
    """
    try:
        if not subscription_obj.get('endpoint'):
            logger.warning(f'Invalid subscription object for {username}')
            return False
        
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        # Create unique hash of subscription to avoid duplicates
        sub_hash = hashlib.md5(
            f"{username}:{subscription_obj['endpoint']}".encode()
        ).hexdigest()
        
        # Check if subscription already exists
        existing = subs_col.find_one({
            'Username': username,
            'SubscriptionHash': sub_hash
        })
        
        if existing:
            # Update last used time
            subs_col.update_one(
                {'_id': existing['_id']},
                {'$set': {
                    'LastUsed': datetime.datetime.now(),
                    'IsActive': True
                }}
            )
            logger.info(f'Updated existing subscription for {username}')
            client.close()
            return True
        
        # Save new subscription
        subscription_doc = {
            'Username': username,
            'Endpoint': subscription_obj['endpoint'],
            'Keys': subscription_obj.get('keys', {}),
            'SubscriptionHash': sub_hash,
            'IsActive': True,
            'CreatedAt': datetime.datetime.now(),
            'LastUsed': datetime.datetime.now(),
            'UserAgent': subscription_obj.get('userAgent', ''),
        }
        
        subs_col.insert_one(subscription_doc)
        logger.info(f'Saved new push subscription for {username}')
        client.close()
        return True
        
    except Exception as e:
        logger.error(f'Error saving push subscription for {username}: {e}')
        return False


def remove_push_subscription(username, endpoint):
    """
    Remove a push subscription
    
    Args:
        username (str): Username
        endpoint (str): Subscription endpoint URL
        
    Returns:
        bool: Success status
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        result = subs_col.update_one(
            {
                'Username': username,
                'Endpoint': endpoint
            },
            {'$set': {'IsActive': False}}
        )
        
        client.close()
        return result.modified_count > 0
        
    except Exception as e:
        logger.error(f'Error removing push subscription for {username}: {e}')
        return False


def send_push_notification(username, title, body, icon=None, url='/', reference=None, tag='notification'):
    """
    Send a push notification to all user's subscriptions
    
    Args:
        username (str): Target username
        title (str): Notification title
        body (str): Notification body
        icon (str, optional): Icon URL
        url (str, optional): URL to open on click
        reference (dict, optional): Reference data (item_id, etc)
        tag (str, optional): Notification tag for grouping
        
    Returns:
        int: Number of successfully sent notifications
    """
    try:
        subscriptions = get_user_subscriptions(username)
        
        if not subscriptions:
            logger.debug(f'No active push subscriptions for {username}')
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
                # Mark subscription as inactive if send fails
                _mark_subscription_inactive(subscription['_id'])
        
        logger.info(f'Sent push notification to {username}: {sent_count}/{len(subscriptions)} subscriptions')
        return sent_count
        
    except Exception as e:
        logger.error(f'Error sending push notification to {username}: {e}')
        return 0


def _send_to_subscription(subscription, title, body, icon, url, reference, tag):
    """Send push notification to a specific subscription"""
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
        
        # If using Firebase Cloud Messaging
        if FCM_API_KEY and subscription.get('Endpoint', '').startswith('https://fcm.'):
            return _send_fcm_notification(subscription, payload)
        
        # Otherwise use standard Web Push Protocol
        return _send_web_push_notification(subscription, payload)
        
    except Exception as e:
        logger.error(f'Error sending to subscription {subscription.get("_id")}: {e}')
        return False


def _send_fcm_notification(subscription, payload):
    """Send notification via Firebase Cloud Messaging"""
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
    """Send notification using standard Web Push Protocol"""
    try:
        # This requires pywebpush library
        from pywebpush import webpush
        
        webpush(
            subscription_info={
                'endpoint': subscription['Endpoint'],
                'keys': subscription.get('Keys', {})
            },
            data=json.dumps(payload),
            vapid_private_key=VAPID_PRIVATE_KEY,
            vapid_claims={'sub': VAPID_SUBJECT},
            timeout=10
        )
        
        return True
        
    except ImportError:
        logger.warning('pywebpush not installed, install with: pip install pywebpush')
        return False
    except Exception as e:
        logger.error(f'Web push error: {e}')
        return False


def _mark_subscription_inactive(subscription_id):
    """Mark a subscription as inactive (e.g., after failed send)"""
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
    """
    Send a push notification to all admin users
    
    Args:
        title (str): Notification title
        body (str): Notification body
        icon (str, optional): Icon URL
        url (str, optional): URL to open on click
        reference (dict, optional): Reference data
        
    Returns:
        int: Total notifications sent
    """
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        users_col = db['users']
        
        # Get all admin users
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
    """
    Remove inactive subscriptions older than 30 days
    Run this periodically as a maintenance task
    """
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


# Database collection schema
def ensure_push_subscriptions_collection():
    """Ensure the push_subscriptions collection exists with proper indexes"""
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        subs_col = get_push_subscriptions_collection(db)
        
        # Create indexes
        subs_col.create_index('Username')
        subs_col.create_index([('Username', 1), ('IsActive', 1)])
        subs_col.create_index([('CreatedAt', 1)])  # TTL-like usage
        subs_col.create_index('SubscriptionHash', unique=True)
        
        logger.info('Push subscriptions collection indexes created')
        client.close()
        
    except Exception as e:
        logger.error(f'Error ensuring push subscriptions collection: {e}')
