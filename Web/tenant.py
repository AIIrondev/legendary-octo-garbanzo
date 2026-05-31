"""
Multi-Tenant Context Manager

Handles tenant resolution, isolation, and database routing for multi-tenant deployments.
Supports subdomain-based tenant identification and per-tenant database namespacing.

Each tenant can support up to 20+ users with isolated data and resource pools.
"""

from flask import request, g, session, has_request_context
from functools import wraps
import datetime
import json
import logging
import os
import re
import ipaddress
import Web.modules.database.settings as cfg
from Web.modules.database.settings import MongoClient

logger = logging.getLogger(__name__)

_TENANT_REGISTRY_MTIME = None


def _load_tenant_registry_from_config():
    registry = {}
    config_path = getattr(cfg, 'CONFIG_PATH', None)
    if config_path and os.path.isfile(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as handle:
                config = json.load(handle)
            tenants = config.get('tenants', {})
            if isinstance(tenants, dict):
                registry.update(tenants)
        except Exception as exc:
            logger.warning("Failed to load tenant registry from config: %s", exc)
    elif isinstance(getattr(cfg, 'TENANT_CONFIGS', None), dict):
        registry.update(cfg.TENANT_CONFIGS)
    return registry


def _refresh_tenant_registry():
    global TENANT_REGISTRY, _TENANT_REGISTRY_MTIME
    config_path = getattr(cfg, 'CONFIG_PATH', None)

    current_mtime = None
    if config_path and os.path.isfile(config_path):
        try:
            current_mtime = os.path.getmtime(config_path)
        except OSError:
            current_mtime = None

    if current_mtime == _TENANT_REGISTRY_MTIME:
        return TENANT_REGISTRY

    TENANT_REGISTRY.clear()
    TENANT_REGISTRY.update(_load_tenant_registry_from_config())
    _TENANT_REGISTRY_MTIME = current_mtime
    return TENANT_REGISTRY


# Tenant registry: maps subdomain/tenant_id to database name
TENANT_REGISTRY = _load_tenant_registry_from_config()


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


def _first_host_token(value):
    raw = str(value or '').strip()
    if not raw:
        return ''
    return raw.split(',', 1)[0].strip().lower()


def _request_host_candidates():
    candidates = []
    for header_name in ('X-Forwarded-Host', 'X-Original-Host', 'Host'):
        token = _first_host_token(request.headers.get(header_name, ''))
        if token and token not in candidates:
            candidates.append(token)

    direct_host = _first_host_token(getattr(request, 'host', ''))
    if direct_host and direct_host not in candidates:
        candidates.append(direct_host)

    return candidates


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


def _find_registered_tenant_id(candidate):
    candidate = str(candidate or '').strip()
    if not candidate:
        return None

    if candidate in TENANT_REGISTRY:
        return candidate

    lowered = candidate.lower()
    for tenant_id in TENANT_REGISTRY:
        if str(tenant_id).lower() == lowered:
            return tenant_id

    return None


def _is_ip_host(hostname):
    hostname = str(hostname or '').strip()
    if not hostname:
        return False
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def get_tenant_config(tenant_id=None):
    """Return the registered config for a tenant, falling back to default."""
    _refresh_tenant_registry()

    if tenant_id is None:
        ctx = get_tenant_context()
        tenant_id = ctx.tenant_id if ctx and ctx.tenant_id else 'default'

    if tenant_id in TENANT_REGISTRY:
        return TENANT_REGISTRY[tenant_id] or {}
        
    for alias in _tenant_db_aliases(tenant_id):
        if alias in TENANT_REGISTRY:
            return TENANT_REGISTRY[alias] or {}

    return TENANT_REGISTRY.get('default', {}) or {}


def _normalize_db_name(db_name):
    if not db_name:
        return None
    db_name = str(db_name).strip()
    if db_name and not db_name.startswith('inventar_'):
        db_name = f'inventar_{db_name}'
    return db_name


def _module_name_candidates(module_name):
    normalized = str(module_name or '').strip().lower().replace('-', '_')
    if not normalized:
        return []

    candidates = [normalized]
    alias_groups = {
        'inventory': {'inventory', 'inventar'},
        'terminplan': {'terminplan', 'terminplaner', 'termin', 'appointments'},
        'library': {'library', 'bib', 'bibliothek'},
        'student_cards': {'student_cards', 'studentcards', 'schuelerausweise', 'schueler_ausweise'},
    }

    for canonical_name, aliases in alias_groups.items():
        if normalized in aliases:
            for alias in (canonical_name, *sorted(aliases)):
                if alias not in candidates:
                    candidates.append(alias)
            break

    return candidates


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
    for candidate_name in _module_name_candidates(module_name):
        enabled = _get_nested_value(config, ['modules', candidate_name, 'enabled'], None)
        if enabled is not None:
            return bool(enabled)

    return bool(default)


def _parse_datetime_value(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime.datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        try:
            parsed = datetime.datetime.fromisoformat(text.replace('Z', '+00:00'))
        except ValueError:
            return None

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return parsed


def get_tenant_trial_config(tenant_id=None):
    """Return the optional trial/demo lifecycle settings for a tenant."""
    config = get_tenant_config(tenant_id)
    trial_config = _get_nested_value(config, ['trial'], {})
    if not isinstance(trial_config, dict):
        trial_config = {}

    demo_config = _get_nested_value(config, ['demo'], {})
    if isinstance(demo_config, dict):
        merged = dict(demo_config)
        merged.update(trial_config)
        trial_config = merged

    return trial_config


def get_tenant_trial_status(tenant_id=None, now=None):
    """Compute the current trial status for a tenant.

    The config may define either an absolute "expires_at" timestamp or a
    relative lifetime via "started_at"/"created_at" plus one of
    "expires_after_days", "ttl_days", or "days".
    """
    trial_config = get_tenant_trial_config(tenant_id)
    now = now or datetime.datetime.now()

    enabled = bool(trial_config.get('enabled') or trial_config.get('active'))
    if not enabled:
        return {
            'enabled': False,
            'expired': False,
            'auto_delete': bool(trial_config.get('auto_delete', False)),
            'started_at': None,
            'expires_at': None,
            'days_left': None,
        }

    started_at = _parse_datetime_value(
        trial_config.get('started_at')
        or trial_config.get('created_at')
        or trial_config.get('activated_at')
    )
    expires_at = _parse_datetime_value(trial_config.get('expires_at'))

    if expires_at is None:
        duration_days = trial_config.get('expires_after_days')
        if duration_days is None:
            duration_days = trial_config.get('ttl_days')
        if duration_days is None:
            duration_days = trial_config.get('days')
        try:
            duration_days = int(duration_days) if duration_days is not None else None
        except (TypeError, ValueError):
            duration_days = None

        if duration_days is not None:
            base_time = started_at or now
            expires_at = base_time + datetime.timedelta(days=max(0, duration_days))

    expired = bool(expires_at and now >= expires_at)
    days_left = None
    if expires_at:
        remaining = expires_at - now
        days_left = max(0, int(remaining.total_seconds() // 86400))

    return {
        'enabled': True,
        'expired': expired,
        'auto_delete': bool(trial_config.get('auto_delete', False)),
        'started_at': started_at,
        'expires_at': expires_at,
        'days_left': days_left,
    }


def _get_tenant_db_name_from_config(tenant_id):
    config = get_tenant_config(tenant_id)
    explicit_db = None
    if isinstance(config, dict):
        explicit_db = config.get('db') or config.get('db_name')

    if explicit_db:
        return _normalize_db_name(explicit_db)

    sanitized = ''.join(c if c.isalnum() or c == '_' else '' for c in str(tenant_id).lower())
    return f'inventar_{sanitized}' if sanitized else cfg.MONGODB_DB


def delete_tenant(tenant_id, *, drop_database=True, remove_from_config=True):
    """Delete a tenant's runtime data and optionally remove its config entry."""
    tenant_id = str(tenant_id or '').strip()
    if not tenant_id:
        return False

    db_name = _get_tenant_db_name_from_config(tenant_id)

    if drop_database:
        try:
            client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
            try:
                client.drop_database(db_name)
            finally:
                client.close()
        except Exception as exc:
            logger.warning("Failed to drop tenant database %s for %s: %s", db_name, tenant_id, exc)

    if remove_from_config:
        try:
            config_path = getattr(cfg, 'CONFIG_PATH', None)
            if config_path and os.path.isfile(config_path):
                with open(config_path, 'r', encoding='utf-8') as handle:
                    config = json.load(handle)

                tenants = config.get('tenants', {})
                if not isinstance(tenants, dict):
                    tenants = {}

                aliases = set(_tenant_db_aliases(tenant_id))
                aliases.add(tenant_id)
                lowered = tenant_id.lower()
                if lowered.startswith('schule'):
                    aliases.add('school' + lowered[len('schule'):])
                elif lowered.startswith('school'):
                    aliases.add('schule' + lowered[len('school'):])

                removed_any = False
                for alias in aliases:
                    if alias in tenants:
                        tenants.pop(alias, None)
                        removed_any = True

                if removed_any:
                    config['tenants'] = tenants
                    with open(config_path, 'w', encoding='utf-8') as handle:
                        json.dump(config, handle, indent=4, ensure_ascii=False)

            for alias in [tenant_id, *_tenant_db_aliases(tenant_id)]:
                TENANT_REGISTRY.pop(alias, None)
        except Exception as exc:
            logger.warning("Failed to remove tenant config for %s: %s", tenant_id, exc)

    return True


def purge_expired_trial_tenants(now=None):
    """Delete expired trial tenants that opted into auto-delete."""
    now = now or datetime.datetime.now()
    purged_tenants = []

    for tenant_id in list(TENANT_REGISTRY.keys()):
        status = get_tenant_trial_status(tenant_id, now=now)
        if status.get('enabled') and status.get('expired') and status.get('auto_delete'):
            if delete_tenant(tenant_id):
                purged_tenants.append(tenant_id)

    return purged_tenants


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

        # Query parameters are useful for public links that must open a specific tenant
        # even when the host/subdomain cannot be mapped reliably.
        tenant_from_query = (
            request.args.get('tenant', '').strip()
            or request.args.get('tenant_id', '').strip()
            or request.args.get('tenantId', '').strip()
        )
        if tenant_from_query:
            matched_tenant = _find_registered_tenant_id(tenant_from_query) or tenant_from_query
            self.tenant_id = matched_tenant
            self.config = get_tenant_config(matched_tenant)
            session['tenant_id'] = matched_tenant
            return self._get_db_name(matched_tenant)

        # Priority 1: X-Tenant-ID header (for testing/internal APIs)
        tenant_from_header = request.headers.get('X-Tenant-ID', '').strip()
        if tenant_from_header:
            matched_tenant = _find_registered_tenant_id(tenant_from_header) or tenant_from_header
            self.tenant_id = matched_tenant
            self.config = get_tenant_config(matched_tenant)
            session['tenant_id'] = matched_tenant
            return self._get_db_name(matched_tenant)

        # Priority 2: Port/host based tenant mapping
        host_candidates = _request_host_candidates()
        primary_host = host_candidates[0] if host_candidates else _first_host_token(getattr(request, 'host', ''))
        logger.info(
            "Tenant resolution start: request.host=%s host_candidates=%s request.headers=%s",
            getattr(request, 'host', ''),
            host_candidates,
            dict(request.headers),
        )

        for host in host_candidates:
            hostname, port = _parse_port_from_host(host)
            if port:
                self.port = port
                tenant_from_port = _tenant_id_for_port(port)
                if tenant_from_port:
                    self.tenant_id = tenant_from_port
                    self.config = get_tenant_config(tenant_from_port)
                    session['tenant_id'] = tenant_from_port
                    logger.info(
                        f"Tenant resolution by port: host={host} port={port} tenant={tenant_from_port} config={self.config}"
                    )
                    return self._get_db_name(tenant_from_port)
                logger.info(f"Tenant port not mapped: host={host} port={port}")

        # Priority 3: Subdomain extraction
        for host in host_candidates:
            host_without_port, _ = _parse_port_from_host(host)
            host_without_port = (host_without_port or '').strip().lower()
            if not host_without_port:
                continue

            direct_host_match = _find_registered_tenant_id(host_without_port)
            if direct_host_match:
                self.subdomain = host_without_port
                self.tenant_id = direct_host_match
                self.config = get_tenant_config(direct_host_match)
                session['tenant_id'] = direct_host_match
                logger.info(
                    f"Tenant resolution by direct host match: host={host} tenant={direct_host_match} config={self.config}"
                )
                return self._get_db_name(direct_host_match)

            if host_without_port and not _is_ip_host(host_without_port):
                parts = host_without_port.split('.')
                if len(parts) >= 2:
                    potential_subdomain = parts[0]
                    if potential_subdomain not in ('www', 'api', 'admin', 'app', 'mail'):
                        matched_tenant = _find_registered_tenant_id(potential_subdomain)
                        if not matched_tenant and potential_subdomain.startswith('school'):
                            matched_tenant = _find_registered_tenant_id('schule' + potential_subdomain[len('school'):])
                        elif not matched_tenant and potential_subdomain.startswith('schule'):
                            matched_tenant = _find_registered_tenant_id('school' + potential_subdomain[len('schule'):])
                        if matched_tenant:
                            self.subdomain = potential_subdomain
                            self.tenant_id = matched_tenant
                            self.config = get_tenant_config(matched_tenant)
                            session['tenant_id'] = matched_tenant
                            logger.info(
                                f"Tenant resolution by subdomain: host={host} tenant={matched_tenant} config={self.config}"
                            )
                            return self._get_db_name(matched_tenant)
                        logger.info(f"Tenant subdomain not registered: {potential_subdomain}")
                    else:
                        logger.info(f"Tenant subdomain ignored: {potential_subdomain}")

        # Priority 4: sticky tenant from the authenticated session
        session_tenant = session.get('tenant_id', '').strip() if session.get('tenant_id') else ''
        if session_tenant:
            self.tenant_id = session_tenant
            self.config = get_tenant_config(session_tenant)
            logger.info(
                f"Tenant resolution by session: host={primary_host} tenant={session_tenant} config={self.config}"
            )
            return self._get_db_name(session_tenant)

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
