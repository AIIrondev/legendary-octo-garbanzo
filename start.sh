#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.docker-build.env"
APP_IMAGE_REPO="ghcr.io/aiirondev/legendary-octo-garbanzo"
DIST_DIR="$SCRIPT_DIR/dist"
RUNTIME_COMPOSE_OVERRIDE_FILE="$SCRIPT_DIR/.docker-compose.runtime.override.yml"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

IS_ROOT="false"
if [ "$(id -u)" -eq 0 ]; then
    IS_ROOT="true"
fi

NUITKA_BUILD_VALUE="0"
HTTP_PORT_VALUE="10000"
HTTP_PORTS_VALUE=""
DEFAULT_TENANT_PORT_START="${INVENTAR_TENANT_PORT_START:-10000}"
CRON_SETUP_VALUE="${INVENTAR_SETUP_CRON:-1}"
APP_IMAGE_VALUE="${INVENTAR_APP_IMAGE:-$APP_IMAGE_REPO:latest}"
COMPOSE_FILE="docker-compose-multitenant.yml"
COMPOSE_PROFILES_VALUE=""
MIN_DOCKER_FREE_MB="${INVENTAR_MIN_DOCKER_FREE_MB:-1024}"

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --no-cron         Do not create or update cron jobs
  --with-cron       Create/update cron jobs (default)
  --multitenant     Use the multi-tenant architecture deployment
  -h, --help        Show this help message
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --no-cron)
                CRON_SETUP_VALUE="0"
                shift
                ;;
            --with-cron)
                CRON_SETUP_VALUE="1"
                shift
                ;;
            --multitenant)
                COMPOSE_FILE="docker-compose-multitenant.yml"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Error: unknown option '$1'"
                usage
                exit 2
                ;;
        esac
    done
}

cron_setup_enabled() {
    case "${CRON_SETUP_VALUE,,}" in
        0|false|no|off)
            return 1
            ;;
        *)
            return 0
            ;;
    esac
}

apt_install() {
    $SUDO apt-get update -y
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

install_docker_engine() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    fi

    echo "Docker not found. Trying distro package docker.io..."
    if apt_install docker.io; then
        return 0
    fi

    echo "docker.io install failed. Trying Docker CE package docker-ce..."
    apt_install ca-certificates curl gnupg lsb-release

    $SUDO install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | $SUDO gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    $SUDO chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      $SUDO tee /etc/apt/sources.list.d/docker.list >/dev/null

    $SUDO apt-get update -y
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

ensure_runtime_dependencies() {
    local missing=()

    if ! command -v docker >/dev/null 2>&1; then
        if [ "$IS_ROOT" = "true" ]; then
            install_docker_engine
        else
            missing+=(docker)
        fi
    fi

    if ! docker compose version >/dev/null 2>&1; then
        missing+=(docker-compose-v2)
    fi

    if ! command -v openssl >/dev/null 2>&1; then
        missing+=(openssl)
    fi

    if ! command -v curl >/dev/null 2>&1; then
        missing+=(curl)
    fi

    if ! command -v python3 >/dev/null 2>&1; then
        missing+=(python3)
    fi

    if cron_setup_enabled && ! command -v crontab >/dev/null 2>&1; then
        missing+=(cron)
    fi

    if [ "${#missing[@]}" -gt 0 ]; then
        if [ "$IS_ROOT" = "true" ]; then
            echo "Installing missing dependencies: ${missing[*]}"
            apt_install "${missing[@]}"
        else
            echo "ERROR: Missing dependencies: ${missing[*]}"
            echo "Please install the missing tools or run this script as root."
            exit 1
        fi
    fi

    if [ "$IS_ROOT" = "true" ] && command -v systemctl >/dev/null 2>&1; then
        systemctl enable --now docker >/dev/null 2>&1 || true
        if cron_setup_enabled; then
            systemctl enable --now cron >/dev/null 2>&1 || true
        fi
    fi
}

setup_boot_autostart_service() {
    local service_path
    local service_name="inventarsystem-docker.service"

    if [ "${INVENTAR_SKIP_AUTOSTART_SETUP:-0}" = "1" ]; then
        return 0
    fi

    if [ "$IS_ROOT" != "true" ]; then
        echo "Skipping systemd autostart setup when not running as root."
        return 0
    fi

    if ! command -v systemctl >/dev/null 2>&1; then
        return 0
    fi

    service_path="/etc/systemd/system/$service_name"

    if [ ! -f "$service_path" ] || ! grep -Fq "$SCRIPT_DIR/start.sh --no-cron" "$service_path"; then
        $SUDO tee "$service_path" >/dev/null <<EOF
[Unit]
Description=Inventarsystem Docker Stack Autostart
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
RequiresMountsFor=$SCRIPT_DIR

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$SCRIPT_DIR
Environment=INVENTAR_SKIP_AUTOSTART_SETUP=1
Environment=INVENTAR_SETUP_CRON=0
ExecStart=/bin/bash "$SCRIPT_DIR/start.sh" --no-cron
ExecStop=/bin/bash "$SCRIPT_DIR/stop.sh"
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

        $SUDO systemctl daemon-reload
    fi

    $SUDO systemctl enable "$service_name" >/dev/null 2>&1 || true
}

setup_scheduled_jobs() {
    if ! cron_setup_enabled; then
        echo "Cron job setup disabled (INVENTAR_SETUP_CRON=$CRON_SETUP_VALUE)"
        return 0
    fi

    if [ "$IS_ROOT" != "true" ]; then
        echo "Skipping cron job setup when not running as root."
        return 0
    fi

    if ! command -v crontab >/dev/null 2>&1; then
        echo "Warning: crontab not available, skipping nightly update setup"
        return 0
    fi

    local update_line backup_line
    update_line="0 3 * * * cd $SCRIPT_DIR && ./update.sh >> $SCRIPT_DIR/logs/update.log 2>&1"
    backup_line="30 2 * * * cd $SCRIPT_DIR && ./backup.sh --mode auto >> $SCRIPT_DIR/logs/backup.log 2>&1"

    local existing_cron
    existing_cron="$(crontab -l 2>/dev/null || true)"
    {
        printf '%s\n' "$existing_cron" | grep -vF "$SCRIPT_DIR/update.sh" | grep -vF "$SCRIPT_DIR/backup-docker.sh" | grep -vF "$SCRIPT_DIR/backup.sh" || true
        echo "$backup_line"
        echo "$update_line"
    } | crontab -

    echo "Nightly backup scheduled at 02:30"
    echo "Nightly auto-update scheduled at 03:00"
}

ensure_runtime_config_json() {
        local config_path backup_path
        config_path="$SCRIPT_DIR/config.json"

        if [ -d "$config_path" ]; then
                backup_path="${config_path}.dir.$(date +%Y%m%d-%H%M%S).bak"
                mv "$config_path" "$backup_path"
                echo "Warning: moved unexpected directory $config_path to $backup_path"
        fi

        if [ ! -f "$config_path" ]; then
                cat > "$config_path" <<'EOF'
{
    "ver": "2.6.5",
    "dbg": false,
    "host": "0.0.0.0",
    "port": 8000,
    "mongodb": {
        "host": "mongodb",
        "port": 27017,
        "db": "Inventarsystem"
    },
    "modules": {
        "library": {
            "enabled": false
        },
        "student_cards": {
            "enabled": false,
            "default_borrow_days": 14,
            "max_borrow_days": 365
        }
    }
}
EOF
                echo "Created default runtime config at $config_path"
        fi
}

ensure_app_image_loaded() {
    if docker image inspect "$APP_IMAGE_VALUE" >/dev/null 2>&1; then
        return 0
    fi

    local image_archive
    image_archive="$(find_local_dist_image_archive || true)"
    if [ -n "$image_archive" ]; then
        echo "Loading app image from local dist artifact: $image_archive"
        if docker load -i "$image_archive" >/dev/null 2>&1 && docker image inspect "$APP_IMAGE_VALUE" >/dev/null 2>&1; then
            return 0
        fi
        echo "Warning: failed to load expected app image from $image_archive"
    fi

    echo "Error: local app image not found: $APP_IMAGE_VALUE"
    echo "Run ./update.sh so the nightly updater loads the release image first."
    exit 1
}

find_local_dist_image_archive() {
    local tag archive

    if [ ! -d "$DIST_DIR" ]; then
        return 1
    fi

    tag="${APP_IMAGE_VALUE##*:}"
    for archive in \
        "$DIST_DIR/inventarsystem-image-$tag.tar.gz" \
        "$DIST_DIR/inventarsystem-image-$tag.tar" \
        "$DIST_DIR/inventarsystem-image.tar.gz" \
        "$DIST_DIR/inventarsystem-image.tar"; do
        if [ -f "$archive" ]; then
            echo "$archive"
            return 0
        fi
    done

    archive="$(find "$DIST_DIR" -maxdepth 1 -type f \( -name 'inventarsystem-image-*.tar.gz' -o -name 'inventarsystem-image-*.tar' \) | sort | tail -n1)"
    if [ -n "$archive" ]; then
        echo "$archive"
        return 0
    fi

    return 1
}

configure_nuitka_mode() {
    local nuitka_mode

    if [ "${NUITKA_SERVICE:-false}" = "true" ]; then
        nuitka_mode="1"
    else
        nuitka_mode="0"
    fi

    if [ -f "$ENV_FILE" ] && [ -z "${NUITKA_SERVICE+x}" ]; then
        nuitka_mode="$(awk -F= '/^NUITKA_BUILD=/{print $2}' "$ENV_FILE" | tr -d ' ' || true)"
        if [ -z "$nuitka_mode" ]; then
            nuitka_mode="0"
        fi
    fi

    NUITKA_BUILD_VALUE="$nuitka_mode"

    if [ "$nuitka_mode" = "1" ]; then
        echo "Nuitka service mode: enabled (compiled app module)"
    else
        echo "Nuitka service mode: disabled (standard Python app module)"
    fi
}

resolve_app_image() {
    local env_image="" release_tag="" default_latest
    default_latest="$APP_IMAGE_REPO:latest"

    if [ -f "$ENV_FILE" ]; then
        env_image="$(awk -F= '/^INVENTAR_APP_IMAGE=/{print $2}' "$ENV_FILE" | tail -n1 | tr -d ' ' || true)"
        if [ -n "$env_image" ] && [ "$env_image" != "$default_latest" ]; then
            APP_IMAGE_VALUE="$env_image"
            return 0
        fi
    fi

    if [ -f "$SCRIPT_DIR/.release-version" ]; then
        release_tag="$(tr -d '[:space:]' < "$SCRIPT_DIR/.release-version")"
    fi

    if [ -n "$release_tag" ]; then
        APP_IMAGE_VALUE="$APP_IMAGE_REPO:$release_tag"
        return 0
    fi

    if [ -n "$env_image" ]; then
        APP_IMAGE_VALUE="$env_image"
    fi
}

port_in_use() {
    local port="$1"

    if ! command -v ss >/dev/null 2>&1; then
        return 1
    fi

    ss -ltn "( sport = :$port )" 2>/dev/null | awk 'NR>1 {print $4}' | grep -q .
}

find_free_port() {
    local port="$1"
    while port_in_use "$port"; do
        port=$((port + 1))
    done
    echo "$port"
}

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

configure_host_ports() {
    local requested_http
    local requested_ports
    local ports=()
    local occupied_ports=()

    requested_http=""
    requested_ports=""
    if [ -f "$ENV_FILE" ]; then
        requested_http="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2}' "$ENV_FILE" | tr -d ' ' || true)"
        requested_ports="$(awk -F= '/^INVENTAR_HTTP_PORTS=/{print $2}' "$ENV_FILE" | tr -d ' ' || true)"
    fi

    if [ -n "${INVENTAR_HTTP_PORTS:-}" ]; then
        requested_ports="$INVENTAR_HTTP_PORTS"
    fi

    if [ -n "${INVENTAR_HTTP_PORT:-}" ] && [ -z "$requested_ports" ]; then
        requested_ports="$INVENTAR_HTTP_PORT"
    fi

    if [ -n "$requested_ports" ]; then
        mapfile -t ports < <(parse_port_list "$requested_ports")
    fi

    if [ ${#ports[@]} -gt 0 ]; then
        HTTP_PORTS_VALUE="${ports[*]}"
        HTTP_PORT_VALUE="${ports[0]}"

        for port in "${ports[@]}"; do
            if port_in_use "$port"; then
                occupied_ports+=("$port")
            fi
        done

        if [ ${#occupied_ports[@]} -gt 0 ]; then
            if [ ${#ports[@]} -eq 1 ]; then
                HTTP_PORT_VALUE="$(find_free_port "$DEFAULT_TENANT_PORT_START")"
                echo "Host port ${ports[0]} is already occupied. Assigned new tenant port: $HTTP_PORT_VALUE"
                HTTP_PORTS_VALUE="$HTTP_PORT_VALUE"
            else
                echo "Error: requested host port(s) already in use: ${occupied_ports[*]}"
                echo "Remove the occupied port(s) from INVENTAR_HTTP_PORTS or stop the conflicting service."
                exit 1
            fi
        fi
    else
        HTTP_PORT_VALUE="$DEFAULT_TENANT_PORT_START"
        HTTP_PORTS_VALUE="$HTTP_PORT_VALUE"

        if port_in_use "$HTTP_PORT_VALUE"; then
            HTTP_PORT_VALUE="$(find_free_port "$DEFAULT_TENANT_PORT_START")"
            echo "Host port $DEFAULT_TENANT_PORT_START is already occupied. Assigned new tenant port: $HTTP_PORT_VALUE"
            HTTP_PORTS_VALUE="$HTTP_PORT_VALUE"
        fi
    fi
}

ensure_min_docker_disk_space() {
    local docker_root available_kb available_mb

    if ! command -v df >/dev/null 2>&1; then
        return 0
    fi

    docker_root="$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || true)"
    if [ -z "$docker_root" ]; then
        docker_root="/var/lib/docker"
    fi

    if [ ! -d "$docker_root" ]; then
        return 0
    fi

    available_kb="$(df -Pk "$docker_root" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
    if [ -z "$available_kb" ]; then
        return 0
    fi

    available_mb=$((available_kb / 1024))

    if [ "$available_mb" -lt "$MIN_DOCKER_FREE_MB" ]; then
        echo "Error: low disk space in Docker data root ($docker_root)."
        echo "Available: ${available_mb} MB; required minimum: ${MIN_DOCKER_FREE_MB} MB"
        echo "MongoDB may fail with 'No space left on device'. Free space and retry."
        exit 1
    fi
}

detect_server_capacity() {
    local cpus mem_kb mem_gb app_workers app_cpus app_mem app_mem_swap

    cpus="$(nproc 2>/dev/null || echo 1)"
    mem_kb="$(awk '/MemAvailable:/ {print $2; exit}' /proc/meminfo 2>/dev/null || awk '/MemTotal:/ {print $2; exit}' /proc/meminfo || echo 0)"
    mem_gb=$(( (mem_kb + 1024*1024 - 1) / (1024*1024) ))

    if [ "$cpus" -ge 8 ] && [ "$mem_gb" -ge 16 ]; then
        app_workers=8
        app_cpus="2.0"
        app_mem="512m"
        app_mem_swap="1024m"
    elif [ "$cpus" -ge 4 ] && [ "$mem_gb" -ge 8 ]; then
        app_workers=4
        app_cpus="1.0"
        app_mem="384m"
        app_mem_swap="768m"
    elif [ "$cpus" -ge 2 ] && [ "$mem_gb" -ge 4 ]; then
        app_workers=2
        app_cpus="0.75"
        app_mem="320m"
        app_mem_swap="640m"
    else
        app_workers=1
        app_cpus="0.5"
        app_mem="256m"
        app_mem_swap="512m"
    fi

    if [ -f "$ENV_FILE" ]; then
        local env_app_cpus env_app_mem env_app_mem_swap env_workers
        env_app_cpus="$(awk -F= '/^INVENTAR_APP_CPUS=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        env_app_mem="$(awk -F= '/^INVENTAR_APP_MEM_LIMIT=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        env_app_mem_swap="$(awk -F= '/^INVENTAR_APP_MEM_SWAP_LIMIT=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"
        env_workers="$(awk -F= '/^INVENTAR_WORKERS=/{print $2; exit}' "$ENV_FILE" | tr -d ' ' || true)"

        [ -n "$env_app_cpus" ] && app_cpus="$env_app_cpus"
        [ -n "$env_app_mem" ] && app_mem="$env_app_mem"
        [ -n "$env_app_mem_swap" ] && app_mem_swap="$env_app_mem_swap"
        [ -n "$env_workers" ] && app_workers="$env_workers"
    fi

    INVENTAR_APP_CPUS="${INVENTAR_APP_CPUS:-$app_cpus}"
    INVENTAR_APP_MEM_LIMIT="${INVENTAR_APP_MEM_LIMIT:-$app_mem}"
    INVENTAR_APP_MEM_SWAP_LIMIT="${INVENTAR_APP_MEM_SWAP_LIMIT:-$app_mem_swap}"
    INVENTAR_WORKERS="${INVENTAR_WORKERS:-$app_workers}"
    INVENTAR_THREADS="${INVENTAR_THREADS:-2}"

    echo "Detected host capacity: CPUs=$cpus, RAM=${mem_gb}GB"
    echo "Configured app runtime: INVENTAR_WORKERS=$INVENTAR_WORKERS, INVENTAR_APP_CPUS=$INVENTAR_APP_CPUS, INVENTAR_APP_MEM_LIMIT=$INVENTAR_APP_MEM_LIMIT"
}

write_env_file() {
    cat > "$ENV_FILE" <<EOF
NUITKA_BUILD=$NUITKA_BUILD_VALUE
INVENTAR_HTTP_PORT=$HTTP_PORT_VALUE
INVENTAR_HTTP_PORTS=${HTTP_PORTS_VALUE// /,}
INVENTAR_APP_IMAGE=$APP_IMAGE_VALUE
INVENTAR_APP_CPUS=$INVENTAR_APP_CPUS
INVENTAR_APP_MEM_LIMIT=$INVENTAR_APP_MEM_LIMIT
INVENTAR_APP_MEM_SWAP_LIMIT=$INVENTAR_APP_MEM_SWAP_LIMIT
INVENTAR_WORKERS=$INVENTAR_WORKERS
INVENTAR_THREADS=$INVENTAR_THREADS
INVENTAR_WORKER_TIMEOUT=${INVENTAR_WORKER_TIMEOUT:-30}
INVENTAR_WORKER_CONNECTIONS=${INVENTAR_WORKER_CONNECTIONS:-100}
EOF
}

write_runtime_compose_override() {
    cat > "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
services:
  app:
    working_dir: /app/Web
    command: ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "${INVENTAR_WORKERS:-2}", "--threads", "${INVENTAR_THREADS:-2}", "--timeout", "${INVENTAR_WORKER_TIMEOUT:-30}", "--graceful-timeout", "20", "--worker-connections", "${INVENTAR_WORKER_CONNECTIONS:-100}", "--max-requests", "200", "--max-requests-jitter", "50", "--log-level", "info", "--access-logfile", "-", "--error-logfile", "-"]
    image: ${APP_IMAGE_VALUE}
    build: null
EOF

    if [ -n "$HTTP_PORTS_VALUE" ]; then
        local ports_array
        local ports_list
        ports_list="${HTTP_PORTS_VALUE//,/ }"
        read -r -a ports_array <<<"$ports_list"
        if [ "${#ports_array[@]}" -gt 0 ]; then
            cat >> "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
    ports:
EOF
            for port in "${ports_array[@]}"; do
                if [ -n "$port" ]; then
                    cat >> "$RUNTIME_COMPOSE_OVERRIDE_FILE" <<EOF
      - "$port:8000"
EOF
                fi
            done
        fi
    fi
}

verify_stack_health() {
    local compose_args running_services retry_count=0
    compose_args=(-f "$COMPOSE_FILE")
    if [ -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" ]; then
        compose_args+=(-f "$RUNTIME_COMPOSE_OVERRIDE_FILE")
    fi
    compose_args+=(--env-file "$ENV_FILE")

    # Try health check with optional restart on first failure
    while [[ $retry_count -lt 2 ]]; do
        echo "Waiting for containers to become healthy... (attempt $((retry_count + 1))/2)"
        for _ in $(seq 1 60); do
            running_services="$(docker compose "${compose_args[@]}" ps --status running --services 2>/dev/null || true)"
            if printf '%s\n' "$running_services" | grep -Fxq app && \
               printf '%s\n' "$running_services" | grep -Fxq redis && \
               printf '%s\n' "$running_services" | grep -Fxq mongodb; then
                if docker compose "${compose_args[@]}" exec -T app python3 -c "import flask, pymongo" >/dev/null 2>&1; then
                    if curl -fsS "http://127.0.0.1:$HTTP_PORT_VALUE/health" >/dev/null 2>&1; then
                        echo "Health check passed."
                        return 0
                    fi
                fi
            fi
            sleep 2
        done

        # First failure: attempt recovery by restarting containers
        if [[ $retry_count -eq 0 ]]; then
            echo "Health check failed. Attempting to restart containers..."
            docker compose "${compose_args[@]}" ps || true
            docker compose "${compose_args[@]}" logs --tail=120 app redis mongodb || true
            docker compose "${compose_args[@]}" restart app redis mongodb
            sleep 3
            ((retry_count++))
        else
            break
        fi
    done

    # Final failure
    echo "Error: stack health check failed after restart attempt."
    docker compose "${compose_args[@]}" ps || true
    docker compose "${compose_args[@]}" logs --tail=120 app redis mongodb || true
    return 1
}

parse_args "$@"

ensure_runtime_dependencies
setup_boot_autostart_service
ensure_runtime_config_json
setup_scheduled_jobs
configure_nuitka_mode
resolve_app_image
configure_host_ports
ensure_min_docker_disk_space
detect_server_capacity
ensure_app_image_loaded
write_env_file
write_runtime_compose_override

echo "Starting Inventarsystem Docker stack (app + mongodb)..."
compose_up_args=(-f "$COMPOSE_FILE")
if [ -f "$RUNTIME_COMPOSE_OVERRIDE_FILE" ]; then
    compose_up_args+=(-f "$RUNTIME_COMPOSE_OVERRIDE_FILE")
fi
compose_up_args+=(--env-file "$ENV_FILE")
if [ -n "$COMPOSE_PROFILES_VALUE" ]; then
    export COMPOSE_PROFILES="$COMPOSE_PROFILES_VALUE"
fi
if ! docker compose "${compose_up_args[@]}" up -d --remove-orphans; then
    echo "Docker Compose startup failed once. Waiting briefly and retrying..."
    sleep 5
    docker compose "${compose_up_args[@]}" up -d --remove-orphans
fi

verify_stack_health

echo "Stack started."
echo "Open: http://<server-ip>:$HTTP_PORT_VALUE"
