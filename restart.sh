#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

COMPOSE_FILE="docker-compose-multitenant.yml"
ENV_FILE="$SCRIPT_DIR/.docker-build.env"
RUNTIME_COMPOSE_OVERRIDE_FILE="$SCRIPT_DIR/.docker-compose.runtime.override.yml"

parse_port_list() {
    local raw="$1"
    local port
    local ports=()
    raw="${raw//,/ }"
    for port in $raw; do
        port="${port//[[:space:]]/}"
        if [ -n "$port" ] && printf '%s\n' "$port" | grep -qE '^[0-9]+$'; then
            ports+=("$port")
        fi
    done
    printf '%s\n' "${ports[@]}"
}

write_runtime_override() {
    local current_ports=""
    local app_image=""
    local ports=()

    if [ -f "$ENV_FILE" ]; then
        app_image="$(awk -F= '/^INVENTAR_APP_IMAGE=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        current_ports="$(awk -F= '/^INVENTAR_HTTP_PORTS=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        if [ -z "$current_ports" ]; then
            current_ports="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        fi
    fi

    if [ -n "$app_image" ]; then
        if [ -n "$current_ports" ]; then
            mapfile -t ports < <(parse_port_list "$current_ports")
        fi

        cat > "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
services:
  app:
    image: $app_image
    build: null
EOF
        if [ ${#ports[@]} -gt 0 ]; then
            cat >> "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
    ports:
EOF
            for port in "${ports[@]}"; do
                if [ -n "$port" ]; then
                    cat >> "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
      - "$port:8000"
EOF
                fi
            done
        fi
    else
        rm -f "$RUNTIME_COMPOSE_OVERRIDE_FILE"
    fi
}

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

echo "Rebuilding and/or restarting app container using $COMPOSE_FILE..."
write_runtime_override
compose_args=(-f "$COMPOSE_FILE")
if [ -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" ]; then
    compose_args+=( -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" )
fi
if [ -f "$ENV_FILE" ]; then
    compose_args+=( --env-file "$ENV_FILE" )
fi

if [ -f "$SCRIPT_DIR/Dockerfile" ]; then
    docker compose "${compose_args[@]}" up -d --build --force-recreate app
else
    echo "Warning: Dockerfile not found in $SCRIPT_DIR. Skipping build and restarting existing app container."
    if ! docker compose "${compose_args[@]}" up -d --no-build --force-recreate app; then
        echo "Warning: app image not found or not available locally. Attempting docker compose pull app..."
        docker compose "${compose_args[@]}" pull app
        docker compose "${compose_args[@]}" up -d --no-build --force-recreate app
    fi
fi

echo "Cleaning up unused Docker images..."
docker image prune -f

echo "App restart complete."
