#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose-multitenant.yml"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --multitenant)
            COMPOSE_FILE="docker-compose-multitenant.yml"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker command not found. Install Docker first."
    exit 1
fi

echo "Stopping Inventarsystem Docker stack..."
docker compose -f "$COMPOSE_FILE" down

echo "Stack stopped."
