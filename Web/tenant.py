"""
Multi-Tenant Context Manager

Handles tenant resolution, isolation, and database routing for multi-tenant deployments.
Supports subdomain-based tenant identification and per-tenant database namespacing.

Each tenant can support up to 20+ users with isolated data and resource pools.
"""

from flask import request, g, has_request_context
from functools import wraps
import logging
import os
import re
import settings as cfg
from settings import MongoClient

logger = logging.getLogger(__name__)

# Tenant registry: maps subdomain/tenant_id to database name
TENANT_REGISTRY = {}
if isinstance(getattr(cfg, 'TENANT_CONFIGS', None), dict):
    TENANT_REGISTRY.update(cfg.TENANT_CONFIGS)


def _get_nested_value(source, path, default=None):
    current = source
    for key in path:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default
    return current


def _parse_tenant_db_map():
    mapping = {}
    raw_map = os.getenv('INVENTAR_TENANT_DB_MAP', '').strip()
    if not raw_map:
        return mapping

    for mapping_pair in re.split(r'[;,\s]+', raw_map):
        if '=' not in mapping_pair:
            continue
        key, value = mapping_pair.split('=', 1)
        mapping[key.strip()] = value.strip()

    return mapping


def _parse_port_from_host(host):
    """Parse host header and return (hostname, port) when a numeric port is present."""
    if host.startswith('['):
        # IPv6 with port: [::1]:10000
        if ']:' in host:
            host_part, _, port_part = host.rpartition(']:')
            return host_part + ']', port_part
        return host, None

    if host.count(':') == 1:
        hostname, port = host.split(':', 1)
        if port.isdigit():
            return hostname, port

    return host, None


def _tenant_id_for_port(port):
    """Map a host port to a registered tenant ID via tenant configs or env overrides."""
    for tenant_id, config in TENANT_REGISTRY.items():
        if isinstance(config, dict) and config.get('port') is not None:
            try:
                configured_port = str(int(config.get('port')))
            except (TypeError, ValueError):
                continue
            if configured_port == str(port):
                return tenant_id

    port_map = os.getenv('INVENTAR_TENANT_PORT_MAP', '').strip()
    if port_map:
        for mapping in re.split(r'[;,\s]+', port_map):
            if '=' not in mapping:
                continue
            key, value = mapping.split('=', 1)
            if key.strip() == str(port):
                return value.strip()

    return None


def get_tenant_config(tenant_id=None):
    """Return the registered config for a tenant, falling back to default."""
    if tenant_id is None:
        ctx = get_tenant_context()
        tenant_id = ctx.tenant_id if ctx and ctx.tenant_id else 'default'

    if tenant_id in TENANT_REGISTRY:
        return TENANT_REGISTRY[tenant_id] or {}

    return TENANT_REGISTRY.get('default', {}) or {}


def _normalize_db_name(db_name):
    if not db_name:
        return None
    db_name = str(db_name).strip()
    if db_name and not db_name.startswith('inventar_'):
        db_name = f'inventar_{db_name}'
    return db_name


def _tenant_db_aliases(tenant_id):
    aliases = []
    env_map = _parse_tenant_db_map()
    if tenant_id in env_map:
        aliases.append(env_map[tenant_id])

    if tenant_id.lower().startswith('schule'):
        aliases.append(tenant_id.lower().replace('schule', 'school', 1))
    elif tenant_id.lower().startswith('school'):
        aliases.append(tenant_id.lower().replace('school', 'schule', 1))

    return [alias for alias in aliases if alias]


def _resolve_db_alias(tenant_id, db_name):
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        available_databases = client.list_database_names()
        if db_name in available_databases:
            return db_name

        for alias in _tenant_db_aliases(tenant_id):
            candidate = _normalize_db_name(alias)
            if candidate in available_databases:
                logger.warning(
                    "Tenant DB fallback applied for tenant %r: %r -> %r",
                    tenant_id,
                    db_name,
                    candidate,
                )
                return candidate
    except Exception as exc:
        logger.exception("Tenant DB alias resolution failed for %r: %s", tenant_id, exc)

    return db_name


def is_tenant_module_enabled(module_name, tenant_id=None, default=False):
    """Resolve whether a feature module is enabled for the current tenant."""
    config = get_tenant_config(tenant_id)
    enabled = _get_nested_value(config, ['modules', module_name, 'enabled'], default)
    return bool(enabled)


class TenantContext:
    """
    Manages current tenant context for request lifecycle.
    Automatically resolves tenant from port, header, or subdomain.
    """

    def __init__(self):
        self.tenant_id = None
        self.db_name = None
        self.subdomain = None
        self.port = None
        self.config = {}

    def resolve_tenant(self):
        """
        Resolve tenant from request context.
        Priority: Header > Port mapping > Subdomain > Default
        """
        if not has_request_context():
            return None

        # Priority 1: X-Tenant-ID header (for testing/internal APIs)
        tenant_from_header = request.headers.get('X-Tenant-ID', '').strip()
        if tenant_from_header:
            self.tenant_id = tenant_from_header
            self.config = get_tenant_config(tenant_from_header)
            return self._get_db_name(tenant_from_header)

        # Priority 2: Port-based tenant mapping
        host = request.host.lower()
        _, port = _parse_port_from_host(host)
        self.port = port
        logger.info(f"Tenant resolution start: request.host={host} request.headers={dict(request.headers)}")
        if port:
            tenant_from_port = _tenant_id_for_port(port)
            if tenant_from_port:
                self.tenant_id = tenant_from_port
                self.config = get_tenant_config(tenant_from_port)
                logger.info(
                    f"Tenant resolution by port: host={host} port={port} tenant={tenant_from_port} config={self.config}"
                )
                return self._get_db_name(tenant_from_port)
            logger.info(f"Tenant port not mapped: host={host} port={port}")

        # Priority 3: Subdomain extraction
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
                self.config = get_tenant_config(potential_subdomain)
                logger.info(
                    f"Tenant resolution by subdomain: host={host} tenant={potential_subdomain} config={self.config}"
                )
                return self._get_db_name(potential_subdomain)
            logger.info(f"Tenant subdomain ignored: {potential_subdomain}")

        # Fallback to default tenant if no tenant identifier found.
        # If no explicit 'default' tenant config exists, use configured MongoDB DB.
        if 'default' in TENANT_REGISTRY:
            self.tenant_id = 'default'
            self.config = get_tenant_config('default')
            return self._get_db_name('default')

        self.tenant_id = None
        self.config = {}
        self.db_name = cfg.MONGODB_DB
        return self.db_name

    def _get_db_name(self, tenant_id):
        """
        Get MongoDB database name for tenant.
        Format: inventar_<tenant_id> unless tenant config overrides it.
        """
        explicit_db = None
        if isinstance(self.config, dict):
            explicit_db = self.config.get('db') or self.config.get('db_name')

        if explicit_db:
            db_name = _normalize_db_name(explicit_db)
        else:
            sanitized = ''.join(c if c.isalnum() or c == '_' else '' for c in tenant_id.lower())
            db_name = f"inventar_{sanitized}"

        db_name = _resolve_db_alias(tenant_id, db_name)
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
    # Fallback to configured default database
    return mongo_client[cfg.MONGODB_DB]


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
