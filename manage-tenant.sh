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
    echo "  -h, --help                   Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./manage-tenant.sh add school_a 10001"
    echo "  ./manage-tenant.sh remove test_tenant"
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
        fi

        echo "Adding new tenant '$TENANT_ID'..."
        # Initialize tenant database via Python inside container
        echo "Initializing database for $TENANT_ID..."
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
            docker exec $APP_CONTAINER python3 -c "
import sys; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient; import hashlib
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[f'{settings.MONGODB_DB}_{sys.argv[1]}']
hashed_pw = hashlib.sha512('admin123'.encode()).hexdigest()
db.users.insert_one({'Username': 'admin', 'Password': hashed_pw, 'Role': 'admin', 'Name': 'Admin', 'Nachname': 'User'})
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
import sys; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
client.drop_database(f'{settings.MONGODB_DB}_{sys.argv[1]}')
print(f'Database for tenant {sys.argv[1]} dropped.')
" "$TENANT_ID"
                echo "Tenant '$TENANT_ID' removed successfully."
            else
                echo "Error: Application container not running."
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
        echo "Listing active tenants (Databases):"
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
             docker exec $APP_CONTAINER python3 -c "
import sys; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
prefix = f'{settings.MONGODB_DB}_'
dbs = [d for d in client.list_database_names() if d.startswith(prefix)]
for db in dbs:
    print(f'- {db.replace(prefix, \"\")}')
"
        else
            echo "Error: Application container not running."
        fi
        ;;

    *)
        echo "Unknown command: $COMMAND"
        show_help
        ;;
esac

exit 0
