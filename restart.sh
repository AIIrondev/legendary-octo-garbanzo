#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose-multitenant.yml"
ENV_FILE="$SCRIPT_DIR/.docker-build.env"
RUNTIME_COMPOSE_OVERRIDE_FILE="$SCRIPT_DIR/.docker-compose.runtime.override.yml"
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

echo "Rebuilding and/or restarting app container using $COMPOSE_FILE..."
compose_args=(-f "$COMPOSE_FILE")
if [ -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" ]; then
    compose_args+=( -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" )
fi
if [ -f "$ENV_FILE" ]; then
    compose_args+=( --env-file "$ENV_FILE" )
fi

if [ -f "$SCRIPT_DIR/Dockerfile" ]; then
    docker compose "${compose_args[@]}" up -d --build app
else
    echo "Warning: Dockerfile not found in $SCRIPT_DIR. Skipping build and restarting existing app container."
    if ! docker compose "${compose_args[@]}" up -d --no-build app; then
        echo "Warning: app image not found or not available locally. Attempting docker compose pull app..."
        docker compose "${compose_args[@]}" pull app
        docker compose "${compose_args[@]}" up -d --no-build app
    fi
fi

echo "Cleaning up unused Docker images..."
docker image prune -f

echo "App restart complete."
