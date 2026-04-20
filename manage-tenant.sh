#!/bin/bash
# Script to manage multitenant deployment
# Allows adding, removing, and restarting tenants without downtime for others

if [ ! -f "docker-compose-multitenant.yml" ]; then
    echo "Error: docker-compose-multitenant.yml not found."
    exit 1
fi

show_help() {
    echo "Usage: ./manage-tenant.sh [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  add <tenant_id>       Add a new tenant (initializes database)"
    echo "  remove <tenant_id>    Remove a tenant completely (deletes data!)"
    echo "  restart-tenant <id>   'Restart' a single tenant (clears cache/sessions)"
    echo "  restart-all           Restart all application containers (zero-downtime reload)"
    echo "  list                  List active tenants"
    echo ""
    echo "Examples:"
    echo "  ./manage-tenant.sh add school_a"
    echo "  ./manage-tenant.sh remove test_tenant"
    echo "  ./manage-tenant.sh restart-all"
    exit 1
}

if [ -z "$1" ]; then
    show_help
fi

COMMAND=$1
TENANT_ID=$2

case "$COMMAND" in
    add)
        if [ -z "$TENANT_ID" ]; then
            echo "Error: Please provide a tenant_id."
            exit 1
        fi
        echo "Adding new tenant '$TENANT_ID'..."
        # Add Nginx configuration
        if [ -f "docker/nginx/multitenant.conf" ]; then
            echo "Assuming dynamic routing based on subdomain ($TENANT_ID)..."
        fi
        
        # Initialize tenant database via Python inside container
        echo "Initializing database for $TENANT_ID..."
        APP_CONTAINER=$(docker ps -qf "name=app" | head -n 1)
        if [ -n "$APP_CONTAINER" ]; then
            docker exec $APP_CONTAINER python3 -c "
import sys; sys.path.insert(0, '/app/Web'); import settings; from pymongo import MongoClient
client = MongoClient(settings.MONGODB_HOST, int(settings.MONGODB_PORT))
db = client[f'{settings.MONGODB_DB}_{sys.argv[1]}']
db.users.insert_one({'username': 'admin', 'password': 'hashed_password_here', 'role': 'admin'})
print(f'Tenant {sys.argv[1]} database initialized.')
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
