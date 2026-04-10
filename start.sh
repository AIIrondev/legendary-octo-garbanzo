#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ENV_FILE="$SCRIPT_DIR/.docker-build.env"
APP_IMAGE_REPO="ghcr.io/aiirondev/legendary-octo-garbanzo"
DIST_DIR="$SCRIPT_DIR/dist"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

NUITKA_BUILD_VALUE="0"
HTTP_PORT_VALUE="80"
HTTPS_PORT_VALUE="443"
CRON_SETUP_VALUE="${INVENTAR_SETUP_CRON:-1}"
APP_IMAGE_VALUE="${INVENTAR_APP_IMAGE:-$APP_IMAGE_REPO:latest}"

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --no-cron         Do not create or update cron jobs
  --with-cron       Create/update cron jobs (default)
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
        install_docker_engine
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
        echo "Installing missing dependencies: ${missing[*]}"
        apt_install "${missing[@]}"
    fi

    if command -v systemctl >/dev/null 2>&1; then
        $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
        if cron_setup_enabled; then
            $SUDO systemctl enable --now cron >/dev/null 2>&1 || true
        fi
    fi
}

setup_boot_autostart_service() {
    local service_path
    local service_name="inventarsystem-docker.service"

    if [ "${INVENTAR_SKIP_AUTOSTART_SETUP:-0}" = "1" ]; then
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

    if ! command -v crontab >/dev/null 2>&1; then
        echo "Warning: crontab not available, skipping nightly update setup"
        return 0
    fi

    local update_line backup_line
    update_line="0 3 * * * cd $SCRIPT_DIR && ./update.sh >> $SCRIPT_DIR/logs/update.log 2>&1"
    backup_line="30 2 * * * cd $SCRIPT_DIR && ./backup.sh --mode auto >> $SCRIPT_DIR/logs/backup.log 2>&1"

    local existing_cron
    if [ "$(id -u)" -eq 0 ]; then
        existing_cron="$(crontab -l 2>/dev/null || true)"
        {
            printf '%s\n' "$existing_cron" | grep -vF "$SCRIPT_DIR/update.sh" | grep -vF "$SCRIPT_DIR/backup-docker.sh" | grep -vF "$SCRIPT_DIR/backup.sh" || true
            echo "$backup_line"
            echo "$update_line"
        } | crontab -
    else
        existing_cron="$($SUDO crontab -l 2>/dev/null || true)"
        {
            printf '%s\n' "$existing_cron" | grep -vF "$SCRIPT_DIR/update.sh" | grep -vF "$SCRIPT_DIR/backup-docker.sh" | grep -vF "$SCRIPT_DIR/backup.sh" || true
            echo "$backup_line"
            echo "$update_line"
        } | $SUDO crontab -
    fi

    echo "Nightly backup scheduled at 02:30"
    echo "Nightly auto-update scheduled at 03:00"
}

ensure_tls_certificates() {
    local cert_dir cert_path key_path cn
    cert_dir="$SCRIPT_DIR/certs"
    cert_path="$cert_dir/inventarsystem.crt"
    key_path="$cert_dir/inventarsystem.key"

    mkdir -p "$cert_dir"

    if [ -f "$cert_path" ] && [ -f "$key_path" ]; then
        return 0
    fi

    cn="${TLS_CN:-localhost}"
    echo "No TLS certificates found. Generating self-signed certificate for CN=$cn"

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$key_path" \
        -out "$cert_path" \
        -subj "/C=DE/ST=NA/L=NA/O=Inventarsystem/OU=IT/CN=$cn" >/dev/null 2>&1

    chmod 600 "$key_path"
    chmod 644 "$cert_path"
}

ensure_nginx_config_mount_source() {
    local nginx_dir config_path backup_path
    nginx_dir="$SCRIPT_DIR/docker/nginx"
    config_path="$nginx_dir/default.conf"

    mkdir -p "$nginx_dir"

    if [ -d "$config_path" ]; then
        backup_path="${config_path}.dir.$(date +%Y%m%d-%H%M%S).bak"
        mv "$config_path" "$backup_path"
        echo "Warning: moved unexpected directory $config_path to $backup_path"
    fi

    if [ ! -f "$config_path" ]; then
        cat > "$config_path" <<'EOF'
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/certs/inventarsystem.crt;
    ssl_certificate_key /etc/nginx/certs/inventarsystem.key;

    client_max_body_size 50M;

    location / {
        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
        default_type text/html;
        return 200 '<!doctype html><html><head><meta charset="utf-8"><title>Server Error</title></head><body><h1>Server Error</h1><p>The service is temporarily unavailable.</p></body></html>';
    }
}
EOF
        echo "Recreated missing nginx config at $config_path"
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

stack_owns_host_port() {
    local requested_port="$1"
    local container_port="$2"
    local mapped_port

    mapped_port="$(docker compose --env-file "$ENV_FILE" port nginx "$container_port" 2>/dev/null | tail -n1 || true)"
    if [ -z "$mapped_port" ]; then
        return 1
    fi

    mapped_port="${mapped_port##*:}"
    [ "$mapped_port" = "$requested_port" ]
}

stop_host_nginx_services() {
    local stopped_any=false
    local service_name

    if ! command -v systemctl >/dev/null 2>&1; then
        return 1
    fi

    while IFS= read -r service_name; do
        [ -z "$service_name" ] && continue
        echo "Stopping host service $service_name to free web ports..."
        $SUDO systemctl stop "$service_name" >/dev/null 2>&1 || true
        stopped_any=true
    done < <(systemctl list-units --type=service --state=active --no-pager 2>/dev/null | awk '{print $1}' | grep -E '(^nginx\.service$|nginx)' || true)

    if [ "$stopped_any" = true ]; then
        sleep 2
    fi

    if [ "$stopped_any" = true ]; then
        return 0
    fi

    return 1
}

configure_host_ports() {
    local requested_http requested_https

    requested_http=""
    if [ -f "$ENV_FILE" ]; then
        requested_http="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2}' "$ENV_FILE" | tr -d ' ' || true)"
    fi
    if [ -z "$requested_http" ]; then
        requested_http="80"
    fi

    if stack_owns_host_port "$requested_http" "80"; then
        HTTP_PORT_VALUE="$requested_http"
    elif port_in_use "$requested_http"; then
        stop_host_nginx_services || true

        if ! port_in_use "$requested_http"; then
            HTTP_PORT_VALUE="$requested_http"
            echo "Freed HTTP port $requested_http by stopping host nginx service"
        else
            HTTP_PORT_VALUE="$(find_free_port 8080)"
            echo "HTTP port 80 is in use. Using fallback HTTP port: $HTTP_PORT_VALUE"
        fi
    else
        HTTP_PORT_VALUE="$requested_http"
    fi

    requested_https=""
    if [ -f "$ENV_FILE" ]; then
        requested_https="$(awk -F= '/^INVENTAR_HTTPS_PORT=/{print $2}' "$ENV_FILE" | tr -d ' ' || true)"
    fi

    if [ -z "$requested_https" ]; then
        requested_https="443"
    fi

    if stack_owns_host_port "$requested_https" "443"; then
        HTTPS_PORT_VALUE="$requested_https"
    elif port_in_use "$requested_https"; then
        stop_host_nginx_services || true

        if ! port_in_use "$requested_https"; then
            HTTPS_PORT_VALUE="$requested_https"
            echo "Freed HTTPS port $requested_https by stopping host nginx service"
            return
        fi

        HTTPS_PORT_VALUE="$(find_free_port 8443)"
        echo "HTTPS port 443 is in use. Using fallback HTTPS port: $HTTPS_PORT_VALUE"
    else
        HTTPS_PORT_VALUE="$requested_https"
    fi
}

write_env_file() {
    cat > "$ENV_FILE" <<EOF
NUITKA_BUILD=$NUITKA_BUILD_VALUE
INVENTAR_HTTP_PORT=$HTTP_PORT_VALUE
INVENTAR_HTTPS_PORT=$HTTPS_PORT_VALUE
INVENTAR_APP_IMAGE=$APP_IMAGE_VALUE
EOF
}

verify_stack_health() {
    local compose_args running_services retry_count=0
    compose_args=(--env-file "$ENV_FILE")

    # Try health check with optional restart on first failure
    while [[ $retry_count -lt 2 ]]; do
        echo "Waiting for containers to become healthy... (attempt $((retry_count + 1))/2)"
        for _ in $(seq 1 60); do
            running_services="$(docker compose "${compose_args[@]}" ps --status running --services 2>/dev/null || true)"
            if printf '%s\n' "$running_services" | grep -Fxq app && \
               printf '%s\n' "$running_services" | grep -Fxq nginx && \
               printf '%s\n' "$running_services" | grep -Fxq mongodb; then
                if docker compose "${compose_args[@]}" exec -T app python3 -c "import flask, pymongo" >/dev/null 2>&1; then
                    if curl -kfsS "https://127.0.0.1:$HTTPS_PORT_VALUE" >/dev/null 2>&1; then
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
            docker compose "${compose_args[@]}" logs --tail=120 app nginx mongodb || true
            docker compose "${compose_args[@]}" restart app nginx mongodb
            sleep 3
            ((retry_count++))
        else
            break
        fi
    done

    # Final failure
    echo "Error: stack health check failed after restart attempt."
    docker compose "${compose_args[@]}" ps || true
    docker compose "${compose_args[@]}" logs --tail=120 app nginx mongodb || true
    return 1
}

parse_args "$@"

ensure_runtime_dependencies
setup_boot_autostart_service
ensure_tls_certificates
ensure_nginx_config_mount_source
setup_scheduled_jobs
configure_nuitka_mode
resolve_app_image
configure_host_ports
ensure_app_image_loaded
write_env_file

echo "Starting Inventarsystem Docker stack (app + mongodb)..."
docker compose --env-file "$ENV_FILE" up -d --remove-orphans

verify_stack_health

echo "Stack started."
echo "Open: https://<server-ip>:$HTTPS_PORT_VALUE"
