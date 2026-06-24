#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
# Script to manage multitenant deployment
# Allows adding, removing, and restarting tenants without downtime for others

if [ ! -f "docker-compose-multitenant.yml" ]; then
    echo "Error: docker-compose-multitenant.yml not found."
    exit 1
fi

# Resolve script directory so config paths are deterministic even when called via sudo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/config.json"

ensure_runtime_config_json() {
    local config_path backup_path
    config_path="$CONFIG_FILE"

    if [ -d "$config_path" ]; then
        backup_path="${config_path}.dir.$(date +%Y%m%d-%H%M%S).bak"
        mv "$config_path" "$backup_path"
        echo "Warning: moved unexpected directory $config_path to $backup_path"
    fi

        FORCE_REMOVE=false
        if [ "${2:-}" = "--yes" ] || [ "${2:-}" = "-y" ]; then
            FORCE_REMOVE=true
            TENANT_ID="${3:-}"
        fi

        if [ -z "$TENANT_ID" ]; then
        cat > "$config_path" <<'EOF'
{
    "ver": "2.6.5",

        if [ "$FORCE_REMOVE" != true ]; then
            echo -n "WARNING: Are you sure you want to permanently delete all data for tenant '$TENANT_ID'? (y/N) "
            read confirm
            if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
                echo "Removal canceled."
                exit 0
            fi
        fi

        echo "Removing tenant '$TENANT_ID'..."
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        port_to_remove=""
        if [ -n "$APP_CONTAINER" ]; then
            port_to_remove="$({ docker exec "$APP_CONTAINER" python3 - "$TENANT_ID" <<'PY'
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/Web')
from tenant import delete_tenant, get_tenant_config

tenant_id = sys.argv[1]
tenant_cfg = get_tenant_config(tenant_id)
port = tenant_cfg.get('port')

if not delete_tenant(tenant_id):
    print(f'Error: failed to delete tenant {tenant_id}', file=sys.stderr)
    sys.exit(1)

if port is not None:
    print(port)
PY
            } 2>/dev/null)"
            echo "Tenant '$TENANT_ID' database and config removed."
        else
            echo "Warning: Application container not running. Tenant database may still exist in MongoDB."
            if port_to_remove="$(remove_tenant_port "$TENANT_ID" 2>/dev/null)"; then
                :
            else
                echo "Warning: tenant '$TENANT_ID' was not configured in config.json or could not be removed."
            fi
        fi

        if [ -n "$port_to_remove" ]; then
            remove_runtime_port "$port_to_remove"
        fi
        sync_tenant_port_map
        if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
            restart_app_container
        fi
        if [ -n "$port_to_remove" ]; then
            echo "Removed tenant '$TENANT_ID' and cleaned runtime port $port_to_remove."
        else
            echo "Removed tenant '$TENANT_ID'. No port mapping was present."
        fi
    local normalized alias
    normalized="$(printf '%s' "$tenant_id" | tr '[:upper:]' '[:lower:]')"
    printf '%s\n' "$tenant_id"
    if [[ "$normalized" == schule* ]]; then
        alias="school${normalized#schule}"
        if [[ "$alias" != "$tenant_id" ]]; then
            printf '%s\n' "$alias"
        fi
    elif [[ "$normalized" == school* ]]; then
        alias="schule${normalized#school}"
        if [[ "$alias" != "$tenant_id" ]]; then
            printf '%s\n' "$alias"
        fi
    fi
}

write_trial_tenant_config() {
    local tenant_id="$1"
    local port="$2"
    local trial_days="$3"

    if python3 - <<'PY' "$CONFIG_FILE" "$tenant_id" "$port" "$trial_days"
import json, sys, os, datetime

path, tenant_id, port_str, trial_days_str = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
if not os.path.isfile(path):
    print(f"Error: config file not found: {path}", file=sys.stderr)
    sys.exit(1)

with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

tenants = cfg.get('tenants')
if tenants is None or not isinstance(tenants, dict):
    tenants = {}

aliases = {tenant_id}
normalized = tenant_id.lower()
if normalized.startswith('schule'):
    aliases.add('school' + normalized[len('schule'):])
elif normalized.startswith('school'):
    aliases.add('schule' + normalized[len('school'):])

for tid, conf in tenants.items():
    if port_str and isinstance(conf, dict) and str(conf.get('port')) == port_str and tid not in aliases:
        print(f"Error: port {port_str} is already mapped to tenant {tid}", file=sys.stderr)
        sys.exit(2)

try:
    trial_days = max(1, int(trial_days_str))
except ValueError:
    print(f"Error: trial days must be numeric, got {trial_days_str!r}", file=sys.stderr)
    sys.exit(3)

now = datetime.datetime.now(datetime.timezone.utc).isoformat()
trial_config = {
    'enabled': True,
    'auto_delete': True,
    'days': trial_days,
    'ttl_days': trial_days,
    'expires_after_days': trial_days,
    'started_at': now,
    'created_at': now,
}

existing = {}
for alias in aliases:
    alias_cfg = tenants.get(alias)
    if isinstance(alias_cfg, dict):
        existing = alias_cfg
        break

if port_str:
    existing['port'] = int(port_str)
existing['modules'] = {
    'inventory': {'enabled': True},
    'library': {'enabled': True},
    'student_cards': {'enabled': True, 'default_borrow_days': 14, 'max_borrow_days': 365},
        'terminplan': {'enabled': True},
    'mail': {'enabled': True},
}
existing['trial'] = trial_config

for alias in aliases:
    tenants[alias] = dict(existing)

cfg['tenants'] = tenants
with open(path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)

print(f"Configured trial tenant {tenant_id} with {trial_days} day(s) and auto-delete enabled")
PY
    then
        echo "Trial tenant $tenant_id configured in config.json"
    else
        echo "Failed to configure trial tenant $tenant_id"
        exit 1
    fi
}

initialize_tenant_database() {
    local tenant_id="$1"
    local mode="$2"

    APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
    if [ -z "$APP_CONTAINER" ]; then
        echo "Warning: Application container is not running. Please start the multi-tenant system first."
        echo "Data will be initialized upon first access by the tenant."
        return 0
    fi

    docker exec "$APP_CONTAINER" python3 -c '
import sys, re, datetime, hashlib
sys.path.insert(0, "/app")
sys.path.insert(0, "/app/Web")
from Web.modules.database import settings
from pymongo import MongoClient

tenant_id = sys.argv[1].lower()
mode = sys.argv[2]
sanitized = "".join(c for c in tenant_id if c.isalnum() or c == "_")
db_name = f"inventar_{sanitized}"
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[db_name]
hashed_pw = hashlib.scrypt('admin123', salt=b'some_salt', n=16384, r=8, p=1).hex()

action_permissions = {
    "can_borrow": True,
    "can_insert": True,
    "can_edit": True,
    "can_delete": True,
    "can_manage_users": True,
    "can_manage_settings": True,
    "can_view_logs": True,
}

page_permissions = {
    "home": True,
    "tutorial_page": True,
    "my_borrowed_items": True,
    "notifications_view": True,
    "impressum": True,
    "license": True,
    "library_view": True,
    "terminplan": True,
    "home_admin": True,
    "upload_admin": True,
    "library_admin": True,
    "admin_borrowings": True,
    "library_loans_admin": True,
    "admin_damaged_items": True,
    "admin_audit_dashboard": True,
    "logs": True,
    "manage_filters": True,
    "manage_locations": True,
}

if db.users.count_documents({"Username": "admin"}) == 0:
    db.users.insert_one({
        "Username": "admin",
        "Password": hashed_pw,
        "Admin": True,
        "active_ausleihung": None,
        "name": "Admin",
        "last_name": "User",
        "IsStudent": False,
        "PermissionPreset": "full_access",
        "ActionPermissions": action_permissions,
        "PagePermissions": page_permissions,
    })

if mode == "trial":
    db.settings.update_one(
        {"setting_type": "tenant_trial"},
        {"$set": {
            "setting_type": "tenant_trial",
            "enabled": True,
            "auto_delete": True,
            "days": 7,
            "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }},
        upsert=True,
    )

print(f"Tenant {sys.argv[1]} database initialized. Default admin: admin / admin123")
' "$tenant_id" "$mode"
}

update_runtime_ports() {
    local new_port="$1"
    local env_file="$PWD/.docker-build.env"
    local current_ports port_list unique_ports first_port ports_csv

    if [ -z "$new_port" ]; then
        return 0
    fi

    current_ports=""
    if [ -f "$env_file" ]; then
        current_ports="$(awk -F= '/^INVENTAR_HTTP_PORTS=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
        if [ -z "$current_ports" ]; then
            current_ports="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
        fi
    fi

    port_list=()
    unique_ports=()
    if [ -n "$current_ports" ]; then
        IFS=',' read -r -a port_list <<<"${current_ports// /,}"
    fi
    port_list+=("$new_port")

    for port in "${port_list[@]}"; do
        if [ -n "$port" ] && ! printf '%s\n' "${unique_ports[@]}" | grep -qx "$port"; then
            unique_ports+=("$port")
        fi
    done

    if [ ${#unique_ports[@]} -eq 0 ]; then
        unique_ports=("$new_port")
    fi

    first_port="${unique_ports[0]}"
    ports_csv="$(IFS=,; echo "${unique_ports[*]}")"

    if [ ! -f "$env_file" ]; then
        cat > "$env_file" <<EOF
NUITKA_BUILD=0
INVENTAR_HTTP_PORT=$first_port
INVENTAR_HTTP_PORTS=$ports_csv
EOF
    else
        if grep -q '^INVENTAR_HTTP_PORTS=' "$env_file" 2>/dev/null; then
            sed -i "s|^INVENTAR_HTTP_PORTS=.*|INVENTAR_HTTP_PORTS=$ports_csv|" "$env_file"
        else
            printf '\nINVENTAR_HTTP_PORTS=%s\n' "$ports_csv" >> "$env_file"
        fi
        if grep -q '^INVENTAR_HTTP_PORT=' "$env_file" 2>/dev/null; then
            sed -i "s|^INVENTAR_HTTP_PORT=.*|INVENTAR_HTTP_PORT=$first_port|" "$env_file"
        else
            printf '\nINVENTAR_HTTP_PORT=%s\n' "$first_port" >> "$env_file"
        fi
    fi

    echo "Updated runtime env ports: $ports_csv"
}

sync_tenant_port_map() {
    local config_path="$CONFIG_FILE"
    local env_file="$PWD/.docker-build.env"
    local tenant_port_map

    tenant_port_map="$(python3 - <<'PY' "$config_path"
import json, os, sys
path = sys.argv[1]
if not os.path.isfile(path):
    sys.exit(1)
with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)
tenants = cfg.get('tenants', {})
if not isinstance(tenants, dict):
    sys.exit(0)
entries = []
for tenant_id, conf in sorted(tenants.items()):
    if isinstance(conf, dict):
        port = conf.get('port')
        if isinstance(port, (int, float)) or (isinstance(port, str) and str(port).strip().isdigit()):
            entries.append(f"{int(port)}={tenant_id}")
print(','.join(entries))
PY
)"

    if [ -z "$tenant_port_map" ]; then
        if [ -f "$env_file" ]; then
            sed -i '/^INVENTAR_TENANT_PORT_MAP=/d' "$env_file"
        fi
        return 0
    fi

    if [ ! -f "$env_file" ]; then
        cat > "$env_file" <<EOF
NUITKA_BUILD=0
INVENTAR_TENANT_PORT_MAP=$tenant_port_map
EOF
        return 0
    fi

    if grep -q '^INVENTAR_TENANT_PORT_MAP=' "$env_file" 2>/dev/null; then
        sed -i "s|^INVENTAR_TENANT_PORT_MAP=.*|INVENTAR_TENANT_PORT_MAP=$tenant_port_map|" "$env_file"
    else
        printf '\nINVENTAR_TENANT_PORT_MAP=%s\n' "$tenant_port_map" >> "$env_file"
    fi
}

restart_app_container() {
    local workdir="$SCRIPT_DIR"
    local env_file="$SCRIPT_DIR/.docker-build.env"
    local compose_args=()

    ensure_runtime_config_json
    
    # If HOST_WORKDIR is set (called from container), use absolute paths so docker daemon resolves them correctly
    if [ -n "${HOST_WORKDIR:-}" ]; then
        workdir="$HOST_WORKDIR"
        compose_args+=( -f "$(readlink -f "$HOST_WORKDIR/docker-compose-multitenant.yml")" )
        if [ -f "$HOST_WORKDIR/.docker-compose.runtime.override.yml" ]; then
            compose_args+=( -f "$(readlink -f "$HOST_WORKDIR/.docker-compose.runtime.override.yml")" )
        fi
        if [ -f "$HOST_WORKDIR/.docker-build.env" ]; then
            compose_args+=( --env-file "$(readlink -f "$HOST_WORKDIR/.docker-build.env")" )
        fi
    else
        # Normal case: called directly from host
        compose_args+=( -f "$workdir/docker-compose-multitenant.yml" )
        if [ -f "$workdir/.docker-compose.runtime.override.yml" ]; then
            compose_args+=( -f "$workdir/.docker-compose.runtime.override.yml" )
        fi
        if [ -f "$env_file" ]; then
            compose_args+=( --env-file "$env_file" )
        fi
    fi
    
    # Pass along COMPOSE_PROJECT_NAME if set so the internal docker-compose sees it
    if [ -n "${COMPOSE_PROJECT_NAME:-}" ]; then
        compose_args=( -p "$COMPOSE_PROJECT_NAME" "${compose_args[@]}" )
    fi

    echo "Restarting app container to apply tenant configuration changes..."
    docker compose "${compose_args[@]}" up -d --no-build --force-recreate app
}

remove_tenant_port() {
    local tenant_id="$1"
    local config_path="$CONFIG_FILE"
    local port

    port="$(python3 - "$config_path" "$tenant_id" <<'PY'
import json, sys, os
path, tenant_id = sys.argv[1], sys.argv[2]
if not os.path.isfile(path):
    sys.exit(1)
with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)
tenants = cfg.get('tenants', {})
if not isinstance(tenants, dict):
    sys.exit(2)
aliases = {tenant_id}
normalized = tenant_id.lower()
if normalized.startswith('schule'):
    aliases.add('school' + normalized[len('schule'):])
elif normalized.startswith('school'):
    aliases.add('schule' + normalized[len('school'):])
removed = None
for alias in list(aliases):
    alias_cfg = tenants.get(alias)
    if isinstance(alias_cfg, dict):
        removed = alias_cfg if removed is None else removed
        tenants.pop(alias, None)
cfg['tenants'] = tenants
with open(path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)
if removed is not None:
    port = removed.get('port')
    if port is not None:
        print(port)
PY
)"

    local status=$?
    if [ $status -eq 1 ]; then
        echo "Error: config file not found: $config_path"
        return 1
    fi
    if [ $status -eq 2 ]; then
        return 2
    fi

    if [ -n "$port" ]; then
        echo "$port"
    fi
    return 0
}

remove_runtime_port() {
    local removed_port="$1"
    local env_file="$PWD/.docker-build.env"
    local current_ports=""
    local port_list=()
    local new_ports=()
    local first_port=""
    local ports_csv=""


    if [ ! -f "$env_file" ]; then
        return 0
    fi

    current_ports="$(awk -F= '/^INVENTAR_HTTP_PORTS=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
    if [ -z "$current_ports" ]; then
        current_ports="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
    fi

    if [ -z "$current_ports" ]; then
        return 0
    fi

    IFS=',' read -r -a port_list <<<"${current_ports// /,}"
    for port in "${port_list[@]}"; do
        if [ -n "$port" ] && [ "$port" != "$removed_port" ]; then
            new_ports+=("$port")
        fi
    done

    if [ ${#new_ports[@]} -eq 0 ]; then
        sed -i '/^INVENTAR_HTTP_PORTS=/d;/^INVENTAR_HTTP_PORT=/d' "$env_file"
        return 0
    fi

    first_port="${new_ports[0]}"
    # Das 'local' hier entfernen, da wir es oben deklariert haben:
    ports_csv="$(IFS=,; echo "${new_ports[*]}")"

    if grep -q '^INVENTAR_HTTP_PORTS=' "$env_file" 2>/dev/null; then
        sed -i "s|^INVENTAR_HTTP_PORTS=.*|INVENTAR_HTTP_PORTS=$ports_csv|" "$env_file"
    else
        printf '\nINVENTAR_HTTP_PORTS=%s\n' "$ports_csv" >> "$env_file"
    fi

    if grep -q '^INVENTAR_HTTP_PORT=' "$env_file" 2>/dev/null; then
        sed -i "s|^INVENTAR_HTTP_PORT=.*|INVENTAR_HTTP_PORT=$first_port|" "$env_file"
    else
        printf '\nINVENTAR_HTTP_PORT=%s\n' "$first_port" >> "$env_file"
    fi
}

register_tenant_port() {
    local tenant_id="$1"
    local port="$2"

    if python3 - <<'PY' "$CONFIG_FILE" "$tenant_id" "$port"
import json, sys, os
path, tenant_id, port_str = sys.argv[1], sys.argv[2], sys.argv[3]
if not os.path.isfile(path):
    print(f"Error: config file not found: {path}", file=sys.stderr)
    sys.exit(1)
with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)
tenants = cfg.get('tenants')
if tenants is None or not isinstance(tenants, dict):
    tenants = {}
aliases = {tenant_id}
normalized = tenant_id.lower()
if normalized.startswith('schule'):
    aliases.add('school' + normalized[len('schule'):])
elif normalized.startswith('school'):
    aliases.add('schule' + normalized[len('school'):])
for tid, conf in tenants.items():
    if isinstance(conf, dict) and str(conf.get('port')) == port_str and tid not in aliases:
        print(f"Error: port {port_str} is already mapped to tenant {tid}", file=sys.stderr)
        sys.exit(2)
existing = {}
for alias in aliases:
    alias_cfg = tenants.get(alias)
    if isinstance(alias_cfg, dict):
        existing = alias_cfg
        break
existing['port'] = int(port_str)
for alias in aliases:
    tenants[alias] = dict(existing)
cfg['tenants'] = tenants
with open(path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)
print(f"Registered tenant port {port_str} for {tenant_id}")
PY
    then
        echo "Tenant $tenant_id port $port registered in config.json"
    else
        echo "Failed to register tenant port $port for $tenant_id"
        exit 1
    fi
}

show_help() {
    local script_name
    script_name="$(basename "$0")"

    echo "=== MULTI-TENANT INVENTAR MANAGER ==="
    echo ""
    echo "NUTZUNG:"
    echo "  ./$script_name <befehl> [tenant_id] [optionen]"
    echo ""
    echo "VERFÜGBARE BEFEHLE:"
    echo "  add <tenant_id> [port]"
    echo "      Legt einen neuen Tenant an, registriert den Port und initialisiert"
    echo "      die MongoDB-Datenbank mit einem Standard-Admin (admin / admin123)."
    echo ""
    echo "  trial <tenant_id> [port] [tage]"
    echo "      Erstellt einen temporären Test-Tenant (Standardlaufzeit: 7 Tage)."
    echo "      Dieser läuft nach der festgelegten Zeit ab und wird automatisch gelöscht."
    echo ""
    echo "  remove [-y|--yes] <tenant_id>"
    echo "      Löscht einen Tenant komplett (Konfiguration, Ports und Datenbank)."
    echo "      Nutze -y oder --yes, um die Bestätigungsabfrage zu überspringen."
    echo ""
    echo "  restart-tenant <tenant_id>"
    echo "      Startet einen spezifischen Tenant neu, indem alle aktiven Sessions"
    echo "      und der Cache in der MongoDB geleert werden (Sitzungs-Reset)."
    echo ""
    echo "  restart-all"
    echo "      Führt einen Zero-Downtime Rolling-Restart für alle App-Container durch."
    echo ""
    echo "  list"
    echo "      Listet alle registrierten Tenants (aus der config.json) sowie alle"
    echo "      aktiven Tenant-Datenbanken (aus der MongoDB) übersichtlich auf."
    echo ""
    echo "  module <tenant_id> <modulname>=<on|off> [...]"
    echo "      Aktiviert oder deaktiviert bestimmte Features/Module für einen Tenant."
    echo "      Es können mehrere Module gleichzeitig konfiguriert werden."
    echo ""
    echo "GLOBALE OPTIONEN:"
    echo "  -h, --help"
    echo "      Zeigt dieses Hilfemenü an."
    echo ""
    echo "BEISPIELE:"
    echo "  ./$script_name add schule_muenchen 8081"
    echo "  ./$script_name trial test_user 8082 14"
    echo "  ./$script_name module schule_muenchen inventory=on mail=off"
    echo "  ./$script_name remove --yes test_user"
    echo ""
}

if [ -z "${1:-}" ]; then
    show_help
fi

COMMAND="$1"
TENANT_ID="${2:-}"

case "$COMMAND" in
    -h|--help)
        show_help
        ;;
    add)
        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id."
            exit 1
        fi

        PORT_ARG="$3"
        if [ -n "$PORT_ARG" ]; then
            if ! printf '%s\n' "$PORT_ARG" | grep -qE '^[0-9]+$'; then
                echo "Error: Port must be a numeric value."
                exit 1
            fi
            register_tenant_port "$TENANT_ID" "$PORT_ARG"
            update_runtime_ports "$PORT_ARG"
            sync_tenant_port_map
            if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
                restart_app_container
            fi
        fi

        echo "Adding new tenant '$TENANT_ID'..."
        # Initialize tenant database via Python inside container
        echo "Initializing database for $TENANT_ID..."
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
            docker exec $APP_CONTAINER python3 -c "
import sys, re; sys.path.insert(0, '/app'); sys.path.insert(0, '/app/Web'); from Web.modules.database import settings; from pymongo import MongoClient; import hashlib
tenant_id = sys.argv[1].lower()
sanitized = ''.join(c for c in tenant_id if c.isalnum() or c == '_')
db_name = f'inventar_{sanitized}'
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[db_name]
hashed_pw = hashlib.scrypt('admin123', salt=b'some_salt', n=16384, r=8, p=1).hex()
if db.users.count_documents({'Username': 'admin'}) == 0:
    db.users.insert_one({
        'Username': 'admin',
        'Password': hashed_pw,
        'Admin': True,
        'active_ausleihung': None,
        'name': 'Admin',
        'last_name': 'User',
        'IsStudent': False,
        'PermissionPreset': 'full_access',
        'ActionPermissions': {
            'can_borrow': True,
            'can_insert': True,
            'can_edit': True,
            'can_delete': True,
            'can_manage_users': True,
            'can_manage_settings': True,
            'can_view_logs': True,
        },
        'PagePermissions': {
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
    })
print(f'Tenant {sys.argv[1]} database initialized. Default admin: admin / admin123')
" "$TENANT_ID"
            echo "Tenant '$TENANT_ID' successfully added. Ready to use."
        else
            echo "Warning: Application container is not running. Please start the multi-tenant system first."
            echo "Data will be initialized upon first access by the tenant."
        fi
        ;;

    trial)
        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id."
            exit 1
        fi

        PORT_ARG="${3:-}"
        DAYS_ARG="${4:-7}"

        if [ -n "$PORT_ARG" ]; then
            if ! printf '%s\n' "$PORT_ARG" | grep -qE '^[0-9]+$'; then
                echo "Error: Port must be a numeric value."
                exit 1
            fi
            register_tenant_port "$TENANT_ID" "$PORT_ARG"
            update_runtime_ports "$PORT_ARG"
            sync_tenant_port_map
        fi

        write_trial_tenant_config "$TENANT_ID" "$PORT_ARG" "$DAYS_ARG"

        if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
            restart_app_container
        fi

        echo "Initializing trial database for $TENANT_ID..."
        initialize_tenant_database "$TENANT_ID" "trial"
        echo "Trial tenant '$TENANT_ID' successfully configured. It will expire after $DAYS_ARG day(s) and self-delete."
        ;;
    
    remove)
        FORCE_REMOVE=true
        if [ "${2:-}" = "--yes" ] || [ "${2:-}" = "-y" ]; then
            FORCE_REMOVE=true
            TENANT_ID="${3:-}"
        fi

        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id to remove."
            exit 1
        fi

        if [ "$FORCE_REMOVE" != true ]; then
            echo -n "WARNING: Are you sure you want to permanently delete all data for tenant '$TENANT_ID'? (y/N) "
            read confirm
            if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
                echo "Removal canceled."
                exit 0
            fi
        fi

        echo "Removing tenant '$TENANT_ID'..."
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        port_to_remove=""
        
        if port_to_remove="$(remove_tenant_port "$TENANT_ID" 2>/dev/null)"; then
            : 
        else
            echo "Warning: tenant '$TENANT_ID' was not found in config.json."
        fi

        # 2. Dann die Datenbank via Container hart über PyMongo löschen
        if [ -n "$APP_CONTAINER" ]; then
            docker exec "$APP_CONTAINER" python3 - "$TENANT_ID" <<'PY'
import sys, re
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/Web')
from Web.modules.database import settings
from pymongo import MongoClient

tenant_id = sys.argv[1].lower()
# Den genauen Datenbanknamen rekonstruieren (wie beim 'add' Befehl)
sanitized = "".join(c for c in tenant_id if c.isalnum() or c == "_")
db_name = f"inventar_{sanitized}"

try:
    # Direkte Verbindung zur Datenbank herstellen und komplett löschen
    client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
    client.drop_database(db_name)
    print(f"MongoDB database '{db_name}' dropped successfully.")
except Exception as e:
    print(f"Warning: Could not drop database '{db_name}': {e}", file=sys.stderr)

# Fallback: Die interne Funktion trotzdem aufrufen, falls sie noch Ordner/Dateien bereinigt
try:
    from tenant import delete_tenant
    delete_tenant(sys.argv[1])
except Exception:
    pass
PY
            echo "Tenant '$TENANT_ID' database and config removed."
        else
            echo "Warning: Application container not running. Tenant database may still exist in MongoDB."
        fi

        if [ -n "$port_to_remove" ]; then
            remove_runtime_port "$port_to_remove"
        fi
        sync_tenant_port_map
        if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
            restart_app_container
        fi
        
        if [ -n "$port_to_remove" ]; then
            echo "Removed tenant '$TENANT_ID' and cleaned runtime port $port_to_remove."
        else
            echo "Removed tenant '$TENANT_ID'. No port mapping was present."
        fi
        ;;

    restart-tenant)
        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id."
            exit 1
        fi
        echo "Restarting tenant '$TENANT_ID' (clearing session/cache)..."
        # To restart a single tenant without restarting the global python processes,
        # we can invalidate their cache or drop their sessions collection to sign everyone out
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
            docker exec $APP_CONTAINER python3 -c "
import sys; sys.path.insert(0, '/app'); sys.path.insert(0, '/app/Web'); from Web.modules.database import settings; from pymongo import MongoClient
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[f'{settings.MONGODB_DB}_{sys.argv[1]}']
db.sessions.drop() # Force sign-out / session clear
print(f'Tenant {sys.argv[1]} session cache cleared. Tenant restarted.')
" "$TENANT_ID"
            echo "Tenant '$TENANT_ID' has been refreshed without impacting others."
        else
             echo "Error: Application container not running."
        fi
        ;;

    restart-all)
        echo "Restarting all application instances with zero-downtime rolling restart..."
        docker restart $(docker ps -qf "name=app")
        echo "Global restart complete."
        ;;
        
    list)
        echo "Listing configured tenants (config.json):"
        if [ -f "$CONFIG_FILE" ]; then
            python3 - "$CONFIG_FILE" <<'PY'
import json, sys
path = sys.argv[1]
with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)
tenants = cfg.get('tenants', {})
if isinstance(tenants, dict) and tenants:
    for tid, conf in tenants.items():
        port = conf.get('port') if isinstance(conf, dict) else None
        if port is not None:
            print(f'- {tid} (port {port})')
        else:
            print(f'- {tid}')
else:
    print('  (no tenants configured)')
PY
        else
            echo "  (config.json not found)"
        fi

        echo ""
        echo "Listing active tenant databases (MongoDB):"
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
             docker exec -i "$APP_CONTAINER" python3 - <<'PY'
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/Web')
from Web.modules.database import settings
from pymongo import MongoClient
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
prefix = 'inventar_'
dbs = [d for d in client.list_database_names() if d.startswith(prefix)]
if dbs:
    for db in dbs:
        print(f'- {db.replace(prefix, "")}')
else:
    print('  (no tenant databases found)')
PY
        else
            echo "Error: Application container not running."
        fi
        ;;

    module)
        if [ -z "$TENANT_ID" ] || [ -z "${3:-}" ]; then
            echo "Error: Usage: manage-tenant.sh module <tenant_id> <module_name>=<on|off> [...]"
            exit 1
        fi
        
        # Pass all remaining arguments to python script
        shift 2
        
        if python3 - "$CONFIG_FILE" "$TENANT_ID" "$@" <<'PY'
import json, sys, os
path = sys.argv[1]
tenant_id = sys.argv[2]
module_args = sys.argv[3:]

if not os.path.isfile(path):
    print(f"Error: config file not found: {path}", file=sys.stderr)
    sys.exit(1)

with open(path, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

tenants = cfg.setdefault('tenants', {})
aliases = {tenant_id}
normalized = tenant_id.lower()
if normalized.startswith('schule'):
    aliases.add('school' + normalized[len('schule'):])
elif normalized.startswith('school'):
    aliases.add('schule' + normalized[len('school'):])

tenant_cfg = None
for alias in aliases:
    alias_cfg = tenants.get(alias)
    if isinstance(alias_cfg, dict):
        tenant_cfg = alias_cfg
        break
if tenant_cfg is None:
    tenant_cfg = {}

modules = tenant_cfg.setdefault('modules', {})
port = tenant_cfg.get('port')
if port is None:
    print(f"Warning: Tenant {tenant_id} doesn't have a port mapping in config.json.", file=sys.stderr)

for arg in module_args:
    if '=' not in arg:
        print(f"Warning: Ignoring invalid argument format '{arg}'. Expected name=on|off.", file=sys.stderr)
        continue
    mod_name, state_str = arg.split('=', 1)
    state = str(state_str).lower() in ('on', '1', 'true', 'yes')
    module_cfg = modules.setdefault(mod_name, {})
    module_cfg['enabled'] = state
    print(f"Module '{mod_name}' set to '{'on' if state else 'off'}' for tenant '{tenant_id}'.")

for alias in aliases:
    alias_cfg = tenants.get(alias)
    if not isinstance(alias_cfg, dict):
        alias_cfg = {}
    alias_cfg.update(tenant_cfg)
    alias_cfg['modules'] = modules
    tenants[alias] = alias_cfg

with open(path, 'w', encoding='utf-8') as f:
    json.dump(cfg, f, indent=4, ensure_ascii=False)
PY
        then
            echo "Module configurations updated successfully."
            if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
                restart_app_container
            fi
        else
            echo "Failed to update module configuration."
            exit 1
        fi
        ;;

    *)
        echo "Unknown command: $COMMAND"
        show_help
        ;;
esac

exit 0
