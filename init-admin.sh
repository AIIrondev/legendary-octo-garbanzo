#!/bin/bash
set -euo pipefail

# Initialize first admin user if database is empty
# Usage: ./init-admin.sh [username] [password] [first_name] [last_name]
# Default: admin / admin123456 / Admin / User

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

USERNAME="${1:-admin}"
PASSWORD="${2:-admin123456}"
FIRST_NAME="${3:-Admin}"
LAST_NAME="${4:-User}"

# Wait for MongoDB to be ready
echo "Waiting for MongoDB to be ready..."
for i in {1..30}; do
    if docker exec inventarsystem-mongodb mongosh --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
        echo "MongoDB is ready."
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Error: MongoDB did not start in time."
        exit 1
    fi
    sleep 1
done

# Check if any users already exist
USER_COUNT=$(docker exec inventarsystem-mongodb mongosh --quiet --eval "db.users.countDocuments({})" Inventarsystem 2>/dev/null || echo "0")

if [ "$USER_COUNT" -eq 0 ]; then
    echo "Database is empty. Creating initial admin user: $USERNAME"
    
    # Hash the password
    PASSWORD_HASH=$(python3 -c "import hashlib; print(hashlib.sha512(b'$PASSWORD').hexdigest())")
    
    # Insert admin user
    docker exec inventarsystem-mongodb mongosh --eval "
    db.users.insertOne({
      Username: '$USERNAME',
      Password: '$PASSWORD_HASH',
      Admin: true,
      active_ausleihung: null,
      name: '$FIRST_NAME',
      last_name: '$LAST_NAME',
      favorites: []
    })
    " Inventarsystem
    
    echo "✓ Admin user '$USERNAME' created successfully."
    echo "  Username: $USERNAME"
    echo "  Password: $PASSWORD"
else
    echo "Database already has $USER_COUNT user(s). Skipping initialization."
fi
