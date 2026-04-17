"""
Optimized Session Management using Redis

Replaces Flask's default filesystem session storage with Redis for:
- Significantly reduced I/O (no disk writes per request)
- Multi-instance session sharing (sticky sessions not needed)
- Automatic cleanup of expired sessions
- Distributed cache support

Reduces memory footprint and improves responsiveness across multi-tenant instances.
"""

import redis
import os
import json
import secrets
from datetime import datetime, timedelta
from flask.sessions import SessionInterface
from werkzeug.datastructures import CallbackDict
import logging

logger = logging.getLogger(__name__)


class RedisSessionInterface(SessionInterface):
    """
    Flask session storage backend using Redis.
    
    Each session is stored as JSON in Redis with automatic expiration.
    Supports distributed deployments with multiple app instances.
    """

    def __init__(self, redis_client=None, redis_host='redis', redis_port=6379, 
                 redis_db=0, key_prefix='inventar:session:'):
        """
        Initialize Redis session interface.
        
        Args:
            redis_client: Existing redis.Redis instance (optional)
            redis_host: Redis server hostname
            redis_port: Redis server port
            redis_db: Redis database number
            key_prefix: Prefix for all session keys
        """
        self.redis = redis_client
        if not self.redis:
            try:
                self.redis = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=True,
                    socket_keepalive=True,
                    socket_keepalive_options={
                        1: 1,  # TCP_KEEPIDLE
                        2: 1,  # TCP_KEEPINTVL
                        3: 3,  # TCP_KEEPCNT
                    } if hasattr(redis, 'TCP_KEEPIDLE') else {}
                )
                # Test connection
                self.redis.ping()
                logger.info(f"Redis session backend initialized: {redis_host}:{redis_port}")
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self.redis = None

        self.key_prefix = key_prefix
        self.permanent_session_lifetime = timedelta(days=7)

    def open_session(self, app, request):
        """
        Open session: retrieve from Redis or create new.
        Called at the start of each request.
        """
        if not self.redis:
            # Fallback: return empty session if Redis unavailable
            logger.warning("Redis unavailable, creating in-memory session")
            return {}

        sid = request.cookies.get(app.config.get('SESSION_COOKIE_NAME', 'session'))

        if not sid:
            # New session
            sid = secrets.token_urlsafe(32)
            session = {}
        else:
            # Retrieve from Redis
            try:
                session_key = f"{self.key_prefix}{sid}"
                session_data = self.redis.get(session_key)

                if session_data:
                    session = json.loads(session_data)
                else:
                    # Session expired or not found
                    session = {}
                    sid = secrets.token_urlsafe(32)
            except Exception as e:
                logger.error(f"Failed to load session {sid}: {e}")
                session = {}
                sid = secrets.token_urlsafe(32)

        # Wrap in CallbackDict to track modifications
        def save_session(*args):
            self.save_session(app, session, None)

        return CallbackDict(session, save_session)

    def save_session(self, app, session, response):
        """
        Save session to Redis with auto-expiration.
        Called at the end of each request.
        """
        if not self.redis or not session:
            return

        sid = response.headers.get('Set-Cookie', '').split('session=')[-1].split(';')[0] if response else None

        if not sid:
            # Generate new session ID
            sid = secrets.token_urlsafe(32)

        try:
            session_key = f"{self.key_prefix}{sid}"

            # Set TTL based on session permanent flag
            ttl = int(self.permanent_session_lifetime.total_seconds())

            # Store session as JSON with expiration
            session_data = json.dumps(session)
            self.redis.setex(session_key, ttl, session_data)

            # Set session cookie if response provided
            if response:
                cookie_secure = app.config.get('SESSION_COOKIE_SECURE', False)
                cookie_httponly = app.config.get('SESSION_COOKIE_HTTPONLY', True)
                cookie_samesite = app.config.get('SESSION_COOKIE_SAMESITE', 'Lax')
                cookie_path = '/'

                response.set_cookie(
                    app.config.get('SESSION_COOKIE_NAME', 'session'),
                    sid,
                    max_age=ttl,
                    secure=cookie_secure,
                    httponly=cookie_httponly,
                    samesite=cookie_samesite,
                    path=cookie_path
                )

        except Exception as e:
            logger.error(f"Failed to save session {sid}: {e}")

    def delete_session(self, app, session_id):
        """
        Manually delete a session from Redis.
        Useful for logout or admin cleanup.
        """
        if not self.redis:
            return

        try:
            session_key = f"{self.key_prefix}{session_id}"
            self.redis.delete(session_key)
            logger.debug(f"Session deleted: {session_id}")
        except Exception as e:
            logger.error(f"Failed to delete session {session_id}: {e}")


def create_redis_session_interface(app):
    """
    Factory function to create and configure Redis session interface for Flask app.
    
    Usage in app.py:
        app.session_interface = create_redis_session_interface(app)
    """
    redis_host = os.getenv('INVENTAR_REDIS_HOST', 'redis')
    redis_port = int(os.getenv('INVENTAR_REDIS_PORT', 6379))
    redis_db = int(os.getenv('INVENTAR_REDIS_DB', 0))

    interface = RedisSessionInterface(
        redis_host=redis_host,
        redis_port=redis_port,
        redis_db=redis_db,
        key_prefix='inventar:session:'
    )

    if not interface.redis:
        logger.warning("Redis session backend failed to initialize, using fallback")

    return interface
