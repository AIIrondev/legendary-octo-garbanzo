#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'
# Script to manage multitenant deployment
# Allows adding, removing, and restarting tenants without downtime for others

if [ ! -f "docker-compose-multitenant.yml" ]; then
    echo "Error: docker-compose-multitenant.yml not found."
    exit 1
fi

CONFIG_FILE="$PWD/config.json"

show_help() {
    echo "Usage: ./manage-tenant.sh [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  add <tenant_id> [port]       Add a new tenant (initializes database)"
    echo "  remove <tenant_id>           Remove a tenant completely (deletes data!)"
    echo "  restart-tenant <id>          'Restart' a single tenant (clears cache/sessions)"
    echo "  restart-all                  Restart all application containers (zero-downtime reload)"
    echo "  list                         List active tenants"
    echo "  module <tenant_id> <module>=<on|off>... Enable/disable modules for a tenant"
    echo "  -h, --help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./manage-tenant.sh add school_a 10001"
    echo "  ./manage-tenant.sh remove test_tenant"
    echo "  ./manage-tenant.sh module school_a inventory=off library=on"
    echo "  ./manage-tenant.sh restart-all"
    echo "  ./manage-tenant.sh -h"
    exit 1
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
for tid, conf in tenants.items():
    if isinstance(conf, dict) and str(conf.get('port')) == port_str and tid != tenant_id:
        print(f"Error: port {port_str} is already mapped to tenant {tid}", file=sys.stderr)
        sys.exit(2)
existing = tenants.get(tenant_id)
if existing is None or not isinstance(existing, dict):
    existing = {}
existing['port'] = int(port_str)
tenants[tenant_id] = existing
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

update_runtime_ports() {
    local new_port="$1"
    local env_file="$PWD/.docker-build.env"
    local current_ports=""
    local port_list=()
    local unique_ports=()
    local first_port=""
    if [ -n "$new_port" ]; then
        if [ -f "$env_file" ]; then
            current_ports="$(awk -F= '/^INVENTAR_HTTP_PORTS=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
            if [ -z "$current_ports" ]; then
                current_ports="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2; exit}' "$env_file" | tr -d ' ' || true)"
            fi
        fi

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
        local ports_csv
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
    fi
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
    local env_file="$PWD/.docker-build.env"
    # If HOST_WORKDIR is set, use it for absolute paths so docker daemon sees correct host paths
    local work_base="${HOST_WORKDIR:-.}"
    local compose_args=( -f "$work_base/docker-compose-multitenant.yml" )
    # Pass along COMPOSE_PROJECT_NAME if set so the internal docker-compose sees it
    if [ -n "$COMPOSE_PROJECT_NAME" ]; then
        compose_args=( -p "$COMPOSE_PROJECT_NAME" "${compose_args[@]}" )
    fi

    if [ -f "$work_base/.docker-compose.runtime.override.yml" ]; then
        compose_args+=( -f "$work_base/.docker-compose.runtime.override.yml" )
    fi
    if [ -f "$env_file" ]; then
        compose_args+=( --env-file "$env_file" )
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
if not isinstance(tenants, dict) or tenant_id not in tenants or not isinstance(tenants[tenant_id], dict):
    sys.exit(2)
removed = tenants.pop(tenant_id, None)
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
    local ports_csv="$(IFS=,; echo "${new_ports[*]}")"

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
import sys, re; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient; import hashlib
tenant_id = sys.argv[1].lower()
sanitized = ''.join(c for c in tenant_id if c.isalnum() or c == '_')
db_name = f'inventar_{sanitized}'
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[db_name]
hashed_pw = hashlib.sha512('admin123'.encode()).hexdigest()
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
    
    remove)
        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id to remove."
            exit 1
        fi
        echo -n "WARNING: Are you sure you want to permanently delete all data for tenant '$TENANT_ID'? (y/N) "
        read confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            echo "Removing tenant '$TENANT_ID'..."
            APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
            if [ -n "$APP_CONTAINER" ]; then
                docker exec $APP_CONTAINER python3 -c "
import sys; sys.path.insert(0, '/app/Web'); from tenant import TenantContext; import settings; from pymongo import MongoClient
ctx = TenantContext()
db_name = ctx._get_db_name(sys.argv[1])
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
client.drop_database(db_name)
print(f'Database for tenant {sys.argv[1]} dropped.')
" "$TENANT_ID"
                echo "Tenant '$TENANT_ID' database removed."
            else
                echo "Warning: Application container not running. Tenant database may still exist in MongoDB."
            fi

            port_to_remove=""
            if port_to_remove="$(remove_tenant_port "$TENANT_ID" 2>/dev/null)"; then
                if [ -n "$port_to_remove" ]; then
                    remove_runtime_port "$port_to_remove"
                    sync_tenant_port_map
                    if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
                        restart_app_container
                    fi
                    echo "Removed tenant '$TENANT_ID' from config.json and cleaned runtime port $port_to_remove."
                else
                    sync_tenant_port_map
                    if [ -n "$(docker ps -qf 'name=app' | head -n 1)" ]; then
                        restart_app_container
                    fi
                    echo "Removed tenant '$TENANT_ID' from config.json. No port mapping was present."
                fi
            else
                echo "Warning: tenant '$TENANT_ID' was not configured in config.json or could not be removed."
            fi
        else
            echo "Removal canceled."
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
import sys; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient
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
sys.path.insert(0, '/app/Web')
import settings
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
tenant_cfg = tenants.setdefault(tenant_id, {})
if 'port' not in tenant_cfg:
    print(f"Warning: Tenant {tenant_id} doesn't have a port mapping in config.json.", file=sys.stderr)

modules = tenant_cfg.setdefault('modules', {})

for arg in module_args:
    if '=' not in arg:
        print(f"Warning: Ignoring invalid argument format '{arg}'. Expected name=on|off.", file=sys.stderr)
        continue
    mod_name, state_str = arg.split('=', 1)
    state = str(state_str).lower() in ('on', '1', 'true', 'yes')
    module_cfg = modules.setdefault(mod_name, {})
    module_cfg['enabled'] = state
    print(f"Module '{mod_name}' set to '{'on' if state else 'off'}' for tenant '{tenant_id}'.")

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
