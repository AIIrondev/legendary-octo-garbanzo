#!/usr/bin/env bash
set -euo pipefail

# Release-only updater for Docker deployment.
# Updates are pulled exclusively from GitHub Releases assets.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/update.log"
STATE_FILE="$PROJECT_DIR/.release-version"
REPO_SLUG="AIIrondev/legendary-octo-garbanzo"
API_URL="https://api.github.com/repos/$REPO_SLUG/releases/latest"
BUNDLE_ASSET="inventarsystem-docker-bundle.tar.gz"
APP_IMAGE_ASSET_PREFIX="inventarsystem-image-"
ENV_FILE="$PROJECT_DIR/.docker-build.env"
APP_IMAGE_REPO="ghcr.io/aiirondev/legendary-octo-garbanzo"
DIST_DIR="$PROJECT_DIR/dist"
COMPOSE_FILE="docker-compose-multitenant.yml"
MIN_ROOT_FREE_MB="${INVENTAR_MIN_ROOT_FREE_MB:-2048}"
DIST_KEEP_COUNT="${INVENTAR_DIST_KEEP_COUNT:-2}"

mkdir -p "$LOG_DIR"
chmod 777 "$LOG_DIR" 2>/dev/null || true

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        log_message "ERROR: Required command not found: $1"
        exit 1
    fi
}

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

IS_ROOT="false"
if [ "$(id -u)" -eq 0 ]; then
    IS_ROOT="true"
fi

apt_install() {
    $SUDO apt-get update -y
    $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

ensure_runtime_dependencies() {
    local missing=()

    if ! command -v docker >/dev/null 2>&1; then
        missing+=(docker)
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

    if [ "${#missing[@]}" -gt 0 ]; then
        if [ "$IS_ROOT" = "true" ]; then
            log_message "Installing missing dependencies: ${missing[*]}"
            apt_install "${missing[@]}"
        else
            log_message "ERROR: Missing dependencies: ${missing[*]}"
            log_message "Install the missing tools manually or re-run as root."
            exit 1
        fi
    fi

    if [ "$IS_ROOT" = "true" ] && command -v systemctl >/dev/null 2>&1; then
        systemctl enable --now docker >/dev/null 2>&1 || true
    fi
}

ensure_min_root_disk_space() {
    local available_kb available_mb

    if ! command -v df >/dev/null 2>&1; then
        return 0
    fi

    available_kb="$(df -Pk "$PROJECT_DIR" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
    if [ -z "$available_kb" ]; then
        return 0
    fi

    available_mb=$((available_kb / 1024))
    if [ "$available_mb" -lt "$MIN_ROOT_FREE_MB" ]; then
        log_message "ERROR: Low disk space on filesystem containing $PROJECT_DIR"
        log_message "Available: ${available_mb} MB; required minimum: ${MIN_ROOT_FREE_MB} MB"
        log_message "Free disk space and rerun update."
        exit 1
    fi
}

cleanup_old_dist_artifacts() {
    local keep_count
    keep_count="$DIST_KEEP_COUNT"

    if [ ! -d "$DIST_DIR" ]; then
        return 0
    fi

    if ! [[ "$keep_count" =~ ^[0-9]+$ ]]; then
        keep_count=2
    fi

    mapfile -t archives < <(find "$DIST_DIR" -maxdepth 1 -type f \( -name 'inventarsystem-image-*.tar.gz' -o -name 'inventarsystem-image-*.tar' \) -printf '%T@ %p\n' | sort -nr | awk '{print $2}')
    if [ "${#archives[@]}" -le "$keep_count" ]; then
        return 0
    fi

    local index old_archive deleted=0
    for (( index=keep_count; index<${#archives[@]}; index++ )); do
        old_archive="${archives[$index]}"
        if rm -f "$old_archive"; then
            deleted=$((deleted + 1))
        fi
    done

    if [ "$deleted" -gt 0 ]; then
        log_message "Cleaned up $deleted old dist image archive(s)"
    fi
}

cleanup_docker_dangling_images() {
    if docker image prune -f >> "$LOG_FILE" 2>&1; then
        log_message "Cleaned up dangling Docker images"
    else
        log_message "WARNING: Could not prune dangling Docker images"
    fi
}

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --multitenant      Use docker-compose-multitenant.yml (default)
  -h, --help         Show this help message
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --multitenant)
                COMPOSE_FILE="docker-compose-multitenant.yml"
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                log_message "ERROR: Unknown option: $1"
                usage
                exit 2
                ;;
        esac
    done
}

archive_logs() {
    log_message "Checking for monthly log archival..."
    if [ -x "$PROJECT_DIR/archive-logs.sh" ]; then
        if "$PROJECT_DIR/archive-logs.sh" >> "$LOG_FILE" 2>&1; then
            log_message "Log archival check completed"
        else
            log_message "WARNING: Log archival encountered issues; continuing"
        fi
    fi
}

create_backup() {
    log_message "Creating database backup before update..."
    if [ -x "$PROJECT_DIR/backup.sh" ]; then
        if "$PROJECT_DIR/backup.sh" --mode auto >> "$LOG_FILE" 2>&1; then
            log_message "Universal backup completed"
            return 0
        else
            log_message "WARNING: Universal backup failed; trying legacy backup path"
        fi
    fi

    if [ -x "$PROJECT_DIR/run-backup.sh" ]; then
        if "$PROJECT_DIR/run-backup.sh" >> "$LOG_FILE" 2>&1; then
            log_message "Backup completed"
        else
            log_message "WARNING: Backup failed; continuing with release update"
        fi
    else
        log_message "WARNING: run-backup.sh not found; skipping backup"
    fi
}

fetch_release_metadata() {
    local meta_file
    meta_file="$1"
    curl -fsSL "$API_URL" -o "$meta_file"
}

parse_latest_tag() {
    local meta_file
    meta_file="$1"
    python3 - <<'PY' "$meta_file"
import json, sys
with open(sys.argv[1], 'r', encoding='utf-8') as f:
    data = json.load(f)
print(data.get('tag_name', '').strip())
PY
}

parse_asset_url() {
    local meta_file asset_name
    meta_file="$1"
    asset_name="$2"
    python3 - <<'PY' "$meta_file" "$asset_name"
import json, sys
meta_file, asset_name = sys.argv[1], sys.argv[2]
with open(meta_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
for asset in data.get('assets', []):
    if asset.get('name') == asset_name:
        print(asset.get('browser_download_url', '').strip())
        break
PY
}

load_release_image() {
    local meta_file tag image_asset image_url tmp_dir archive

    meta_file="$1"
    tag="$2"
    image_asset="${APP_IMAGE_ASSET_PREFIX}${tag}.tar.gz"
    image_url="$(parse_asset_url "$meta_file" "$image_asset")"

    if [ -z "$image_url" ]; then
        log_message "ERROR: Release image asset not found: $image_asset"
        return 1
    fi

    tmp_dir="$(mktemp -d)"
    archive="$tmp_dir/$image_asset"
    trap 'rm -rf "${tmp_dir:-}"' RETURN

    log_message "Loading app image from release asset $image_asset"
    curl -fL "$image_url" -o "$archive"
    docker load -i "$archive" >> "$LOG_FILE" 2>&1
    docker tag "$APP_IMAGE_REPO:$tag" "$APP_IMAGE_REPO:latest" >> "$LOG_FILE" 2>&1 || true

    trap - RETURN
}

refresh_runtime_scripts_from_main() {
    local start_url stop_url restart_url update_url
    start_url="https://raw.githubusercontent.com/$REPO_SLUG/main/start.sh"
    stop_url="https://raw.githubusercontent.com/$REPO_SLUG/main/stop.sh"
    restart_url="https://raw.githubusercontent.com/$REPO_SLUG/main/restart.sh"
    update_url="https://raw.githubusercontent.com/$REPO_SLUG/main/update.sh"

    curl -fsSL "$start_url" -o "$PROJECT_DIR/start.sh" || log_message "WARNING: Could not refresh start.sh from main"
    curl -fsSL "$stop_url" -o "$PROJECT_DIR/stop.sh" || log_message "WARNING: Could not refresh stop.sh from main"
    curl -fsSL "$restart_url" -o "$PROJECT_DIR/restart.sh" || log_message "WARNING: Could not refresh restart.sh from main"
    curl -fsSL "$update_url" -o "$PROJECT_DIR/update.sh" || log_message "WARNING: Could not refresh update.sh from main"

    chmod +x "$PROJECT_DIR/start.sh" "$PROJECT_DIR/stop.sh" "$PROJECT_DIR/restart.sh" "$PROJECT_DIR/update.sh"
}

find_local_dist_image_archive() {
    local tag="$1"
    local archive

    if [ ! -d "$DIST_DIR" ]; then
        return 1
    fi

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

load_local_dist_image() {
    local tag="$1"
    local archive

    archive="$(find_local_dist_image_archive "$tag" || true)"
    if [ -z "$archive" ]; then
        return 1
    fi

    log_message "Loading app image from local dist artifact: $archive"
    if docker load -i "$archive" >> "$LOG_FILE" 2>&1; then
        docker tag "$APP_IMAGE_REPO:$tag" "$APP_IMAGE_REPO:latest" >> "$LOG_FILE" 2>&1 || true
        return 0
    fi

    log_message "WARNING: Failed to load local dist artifact: $archive"
    return 1
}

download_and_extract_bundle() {
    local url tmp_dir archive
    url="$1"
    tmp_dir="$2"
    archive="$tmp_dir/$BUNDLE_ASSET"

    curl -fL "$url" -o "$archive"
    tar -xzf "$archive" -C "$tmp_dir"

    # The bundle must contain docker deployment files only.
    cp -f "$tmp_dir/docker-compose.yml" "$PROJECT_DIR/docker-compose.yml"
    cp -f "$tmp_dir/start.sh" "$PROJECT_DIR/start.sh"
    cp -f "$tmp_dir/stop.sh" "$PROJECT_DIR/stop.sh"

    if [ -f "$tmp_dir/restart.sh" ]; then
        cp -f "$tmp_dir/restart.sh" "$PROJECT_DIR/restart.sh"
    fi

    if [ -f "$tmp_dir/update.sh" ]; then
        cp -f "$tmp_dir/update.sh" "$PROJECT_DIR/update.sh"
    fi

    # Neu: Multi-Tenant Ressourcen kopieren, falls vorhanden
    if [ -f "$tmp_dir/docker-compose-multitenant.yml" ]; then
        cp -f "$tmp_dir/docker-compose-multitenant.yml" "$PROJECT_DIR/docker-compose-multitenant.yml"
    fi
    if [ -f "$tmp_dir/manage-tenant.sh" ]; then
        cp -f "$tmp_dir/manage-tenant.sh" "$PROJECT_DIR/manage-tenant.sh"
    fi
    if [ -f "$tmp_dir/run-tenant-cmd.sh" ]; then
        cp -f "$tmp_dir/run-tenant-cmd.sh" "$PROJECT_DIR/run-tenant-cmd.sh"
    fi
    for file in "MULTITENANT_DEPLOYMENT.md" "MULTITENANT_PYTHON_API.md"; do
        if [ -f "$tmp_dir/$file" ]; then
            cp -f "$tmp_dir/$file" "$PROJECT_DIR/$file"
        fi
    done

    # Ensure executable permissions on all copied scripts
    chmod +x "$PROJECT_DIR/start.sh" "$PROJECT_DIR/stop.sh" "$PROJECT_DIR/restart.sh" "$PROJECT_DIR/update.sh" "$PROJECT_DIR/backup.sh" "$PROJECT_DIR/init-admin.sh" "$PROJECT_DIR/manage-tenant.sh" "$PROJECT_DIR/run-tenant-cmd.sh" 2>/dev/null || true 2>/dev/null || true
    chmod +x "$PROJECT_DIR"/manage-tenant.sh "$PROJECT_DIR"/run-tenant-cmd.sh 2>/dev/null || true

    if [ ! -f "$PROJECT_DIR/config.json" ] && [ -f "$tmp_dir/config.json" ]; then
        cp -f "$tmp_dir/config.json" "$PROJECT_DIR/config.json"
        log_message "Installed default config.json from release bundle"
    fi

    chmod +x "$PROJECT_DIR/start.sh" "$PROJECT_DIR/stop.sh" "$PROJECT_DIR/restart.sh" "$PROJECT_DIR/update.sh" "$PROJECT_DIR/backup.sh" "$PROJECT_DIR/init-admin.sh" "$PROJECT_DIR/manage-tenant.sh" "$PROJECT_DIR/run-tenant-cmd.sh" 2>/dev/null || true
}

deploy() {
    local tag="$1"
    local meta_file="$2"
    local app_image="${APP_IMAGE_REPO}:${tag}"
    local compose_path

    compose_path="$PROJECT_DIR/$COMPOSE_FILE"
    if [ ! -f "$compose_path" ]; then
        log_message "ERROR: compose file not found: $compose_path"
        exit 1
    fi

    cd "$PROJECT_DIR"
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" <<EOF
NUITKA_BUILD=0
INVENTAR_HTTP_PORT=10000
INVENTAR_APP_IMAGE=$app_image
EOF
    elif grep -q '^INVENTAR_APP_IMAGE=' "$ENV_FILE"; then
        sed -i "s|^INVENTAR_APP_IMAGE=.*|INVENTAR_APP_IMAGE=$app_image|" "$ENV_FILE"
    else
        printf '\nINVENTAR_APP_IMAGE=%s\n' "$app_image" >> "$ENV_FILE"
    fi

    if ! load_local_dist_image "$tag"; then
        if ! load_release_image "$meta_file" "$tag"; then
            log_message "Falling back to tagged GHCR image $app_image"
            if ! docker pull "$app_image" >> "$LOG_FILE" 2>&1; then
                log_message "Falling back to local Docker build for $app_image"
                docker build -t "$app_image" "$PROJECT_DIR" >> "$LOG_FILE" 2>&1
            fi
        fi
    fi

    docker compose -f "$compose_path" --env-file "$ENV_FILE" pull app mongodb >> "$LOG_FILE" 2>&1
    docker compose -f "$compose_path" --env-file "$ENV_FILE" up -d --remove-orphans >> "$LOG_FILE" 2>&1
    docker tag "$app_image" "$APP_IMAGE_REPO:latest" >> "$LOG_FILE" 2>&1 || true
}

verify_stack_health() {
    local compose_args running_services
    local http_port
    compose_args=(-f "$PROJECT_DIR/$COMPOSE_FILE" --env-file "$ENV_FILE")
    http_port="$(awk -F= '/^INVENTAR_HTTP_PORT=/{print $2}' "$ENV_FILE" | tr -d ' ')"
    if [ -z "$http_port" ]; then
        http_port="10000"
    fi

    for _ in $(seq 1 60); do
        running_services="$(docker compose "${compose_args[@]}" ps --status running --services 2>/dev/null || true)"
        if printf '%s\n' "$running_services" | grep -Fxq app && \
           printf '%s\n' "$running_services" | grep -Fxq redis && \
           printf '%s\n' "$running_services" | grep -Fxq mongodb; then
            # Primary check: health endpoint responds (most reliable)
            if curl -fsS "http://127.0.0.1:$http_port/health" >/dev/null 2>&1; then
                return 0
            fi
        fi
        sleep 2
    done

    docker compose "${compose_args[@]}" ps >> "$LOG_FILE" 2>&1 || true
    docker compose "${compose_args[@]}" logs --tail=120 app redis mongodb >> "$LOG_FILE" 2>&1 || true
    return 1
}

cleanup_server_space() {
    log_message "Running server cleanup before update..."
    # Remove unused Docker objects
    if docker system prune -af --volumes >> "$LOG_FILE" 2>&1; then
        log_message "Docker system pruned (all unused images, containers, volumes, networks)"
    else
        log_message "WARNING: Docker system prune failed"
    fi
    # Clean up old dist artifacts
    cleanup_old_dist_artifacts
    # Clean up log files older than 7 days
    if find "$LOG_DIR" -type f -name '*.log' -mtime +7 -exec rm -f {} +; then
        log_message "Old log files (older than 7 days) cleaned up"
    else
        log_message "WARNING: Failed to clean up old log files"
    fi
}

main() {
    parse_args "$@"

    cleanup_server_space

    ensure_runtime_dependencies

    require_cmd curl
    require_cmd tar
    require_cmd docker
    require_cmd python3

    ensure_min_root_disk_space
    archive_logs
    create_backup

    local tmp_dir meta_file latest_tag current_tag bundle_url
    tmp_dir="$(mktemp -d)"
    meta_file="$tmp_dir/release.json"

    trap 'rm -rf "${tmp_dir:-}"' EXIT

    log_message "Checking latest GitHub release for $REPO_SLUG..."
    if ! fetch_release_metadata "$meta_file"; then
        log_message "WARNING: Could not fetch release metadata. Falling back to self-healing start path."
        if INVENTAR_SETUP_CRON=0 bash "$PROJECT_DIR/start.sh" >> "$LOG_FILE" 2>&1; then
            if verify_stack_health; then
                log_message "Fallback deployment completed"
            else
                log_message "ERROR: Fallback deployment failed health check"
                exit 1
            fi
        else
            log_message "ERROR: Fallback start path failed"
            exit 1
        fi
        exit 0
    fi

    latest_tag="$(parse_latest_tag "$meta_file")"
    if [ -z "$latest_tag" ]; then
        log_message "WARNING: Could not determine latest release tag. Falling back to self-healing start path."
        if INVENTAR_SETUP_CRON=0 bash "$PROJECT_DIR/start.sh" >> "$LOG_FILE" 2>&1; then
            if verify_stack_health; then
                log_message "Fallback deployment completed"
            else
                log_message "ERROR: Fallback deployment failed health check"
                exit 1
            fi
        else
            log_message "ERROR: Fallback start path failed"
            exit 1
        fi
        exit 0
    fi

    current_tag=""
    if [ -f "$STATE_FILE" ]; then
        current_tag="$(cat "$STATE_FILE")"
    fi

    if [ "$current_tag" = "$latest_tag" ]; then
        log_message "Already on latest release ($latest_tag). Refreshing containers from prebuilt image."
        deploy "$latest_tag" "$meta_file"
        if verify_stack_health; then
            log_message "Container refresh completed"
        else
            log_message "ERROR: Container refresh failed health check"
            exit 1
        fi
        exit 0
    fi

    bundle_url="$(parse_asset_url "$meta_file" "$BUNDLE_ASSET")"
    if [ -z "$bundle_url" ]; then
        log_message "WARNING: Release asset not found: $BUNDLE_ASSET. Falling back to self-healing start path."
        if INVENTAR_SETUP_CRON=0 bash "$PROJECT_DIR/start.sh" >> "$LOG_FILE" 2>&1; then
            if verify_stack_health; then
                log_message "Image-only deployment completed"
            else
                log_message "ERROR: Image-only fallback failed health check"
                exit 1
            fi
        else
            log_message "ERROR: Fallback start path failed"
            exit 1
        fi
        exit 0
    fi

    log_message "Updating from release $latest_tag"
    download_and_extract_bundle "$bundle_url" "$tmp_dir"
    refresh_runtime_scripts_from_main
    deploy "$latest_tag" "$meta_file"
    if ! verify_stack_health; then
        log_message "ERROR: Updated stack failed health check"
        exit 1
    fi

    echo "$latest_tag" > "$STATE_FILE"
    cleanup_old_dist_artifacts
    cleanup_docker_dangling_images
    log_message "Update completed successfully to release $latest_tag"
}

main "$@"
