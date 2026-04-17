"""
Multi-Tenant Context Manager

Handles tenant resolution, isolation, and database routing for multi-tenant deployments.
Supports subdomain-based tenant identification and per-tenant database namespacing.

Each tenant can support up to 20+ users with isolated data and resource pools.
"""

from flask import request, g, has_request_context
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Tenant registry: maps subdomain/tenant_id to database name
TENANT_REGISTRY = {}


class TenantContext:
    """
    Manages current tenant context for request lifecycle.
    Automatically resolves tenant from subdomain or request header.
    """

    def __init__(self):
        self.tenant_id = None
        self.db_name = None
        self.subdomain = None

    def resolve_tenant(self):
        """
        Resolve tenant from request context.
        Priority: Header > Subdomain > Default
        """
        if not has_request_context():
            return None

        # Priority 1: X-Tenant-ID header (for testing/internal APIs)
        tenant_from_header = request.headers.get('X-Tenant-ID', '').strip()
        if tenant_from_header:
            self.tenant_id = tenant_from_header
            return self._get_db_name(tenant_from_header)

        # Priority 2: Subdomain extraction
        host = request.host.lower()
        parts = host.split('.')

        # Extract subdomain from host
        # Examples: schule1.example.com → schule1
        #          app.example.com → app (skip wildcard/app)
        if len(parts) >= 3:
            potential_subdomain = parts[0]

            # Filter out common non-tenant subdomains
            if potential_subdomain not in ('www', 'api', 'admin', 'app', 'mail'):
                self.subdomain = potential_subdomain
                self.tenant_id = potential_subdomain
                return self._get_db_name(potential_subdomain)

        # Fallback to default tenant if no subdomain detected
        self.tenant_id = 'default'
        return self._get_db_name('default')

    def _get_db_name(self, tenant_id):
        """
        Get MongoDB database name for tenant.
        Format: inventar_<tenant_id>
        """
        # Sanitize tenant_id for MongoDB database name
        sanitized = ''.join(c if c.isalnum() or c == '_' else '' for c in tenant_id.lower())
        db_name = f"inventar_{sanitized}"
        self.db_name = db_name
        return db_name

    def get_database(self, mongo_client):
        """
        Get MongoDB database instance for current tenant.
        """
        if not self.db_name:
            self.resolve_tenant()
        return mongo_client[self.db_name]


def get_tenant_context():
    """
    Get or create tenant context for current request.
    Safe to call outside request context; returns None.
    """
    if not has_request_context():
        return None

    if 'tenant_context' not in g:
        g.tenant_context = TenantContext()
        g.tenant_context.resolve_tenant()

    return g.tenant_context


def require_tenant(f):
    """
    Decorator to enforce tenant context resolution before route handler.
    Automatically injects tenant context into g.tenant_context.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        ctx = get_tenant_context()
        if not ctx or not ctx.tenant_id:
            logger.warning(f"Request to {request.path} missing tenant context")
            # Fallback to 'default' tenant
            ctx = TenantContext()
            ctx.resolve_tenant()
            g.tenant_context = ctx

        return f(*args, **kwargs)

    return decorated_function


def get_tenant_db(mongo_client):
    """
    Convenience helper to get tenant-specific database.
    Usage: db = get_tenant_db(mongo_client)
    """
    ctx = get_tenant_context()
    if ctx:
        return ctx.get_database(mongo_client)
    # Fallback to default database
    return mongo_client['inventar_default']


def register_tenant(tenant_id, config=None):
    """
    Register a new tenant in the system.
    Typically called during tenant provisioning.

    Args:
        tenant_id: Unique tenant identifier (e.g., 'schule1')
        config: Optional tenant-specific configuration
    """
    TENANT_REGISTRY[tenant_id] = config or {}
    logger.info(f"Tenant registered: {tenant_id}")


def list_registered_tenants():
    """Return list of all registered tenants."""
    return list(TENANT_REGISTRY.keys())
