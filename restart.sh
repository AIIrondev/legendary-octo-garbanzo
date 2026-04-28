#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose-multitenant.yml"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --multitenant)
            COMPOSE_FILE="docker-compose-multitenant.yml"
            shift
            ;;
        --singletenant)
            COMPOSE_FILE="docker-compose.yml"
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

echo "Rebuilding and restarting app container using $COMPOSE_FILE..."
docker compose -f "$COMPOSE_FILE" up -d --build app

echo "Cleaning up unused Docker images..."
docker image prune -f

echo "App rebuild complete."
