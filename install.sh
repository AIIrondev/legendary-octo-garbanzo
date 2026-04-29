#!/usr/bin/env bash
set -euo pipefail

INSTALLER_SOURCE="${BASH_SOURCE[0]-$0}"
if [ -n "$INSTALLER_SOURCE" ] && [ "$INSTALLER_SOURCE" != "bash" ] && [ "$INSTALLER_SOURCE" != "-bash" ] && [ "$INSTALLER_SOURCE" != "sh" ] && [ "$INSTALLER_SOURCE" != "-" ] && [ -e "$INSTALLER_SOURCE" ]; then
    INSTALLER_DIR="$(cd "$(dirname "$INSTALLER_SOURCE")" && pwd)"
else
    INSTALLER_DIR="$(pwd)"
fi
PROJECT_DIR="/opt/Inventarsystem"
REPO_SLUG="AIIrondev/legendary-octo-garbanzo"
API_URL="https://api.github.com/repos/$REPO_SLUG/releases/latest"
BUNDLE_ASSET="inventarsystem-docker-bundle.tar.gz"
APP_IMAGE_ASSET_PREFIX="inventarsystem-image-"
LEGACY_DB_NAME="Inventarsystem"
LEGACY_MONGO_URI="mongodb://127.0.0.1:27017"
MIGRATE_LEGACY_DB=false
REMOVE_LEGACY_SYSTEM=false
LEGACY_SERVICE_CLEANUP=true
LEGACY_SYSTEM_DIR=""
LEGACY_BACKUP_ARCHIVE=""
CLEANUP_OLD_SERVICES=true
CLEANUP_OLD_REMOVE_CRON=false
TMP_DIR=""
COMPOSE_FILE="docker-compose-multitenant.yml"

cleanup_tmp_dir() {
    if [ -n "${TMP_DIR:-}" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Error: missing command: $1"
        exit 1
    fi
}

refresh_start_script_from_main() {
    local start_url
    start_url="https://raw.githubusercontent.com/$REPO_SLUG/main/start.sh"

    if curl -fsSL "$start_url" -o "$TMP_DIR/start.sh"; then
        sudo install -m 755 "$TMP_DIR/start.sh" "$PROJECT_DIR/start.sh"
    else
        echo "Warning: failed to refresh start.sh from main; using bundled start.sh"
    fi
}

pin_compose_app_image() {
    local tag="$1"
    local compose_file

    for compose_file in "$PROJECT_DIR/docker-compose-multitenant.yml" "$PROJECT_DIR/docker-compose.yml"; do
        if [ ! -f "$compose_file" ]; then
            continue
        fi

        python3 - <<'PY' "$compose_file" "$tag"
import re
import sys

compose_file, tag = sys.argv[1], sys.argv[2]
target_image = f"ghcr.io/aiirondev/legendary-octo-garbanzo:{tag}"

with open(compose_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

out = []
in_app_service = False
app_indent = None
app_service_indent = None
build_found = False

def leading_spaces(text):
    return len(text) - len(text.lstrip(" "))

i = 0
while i < len(lines):
    line = lines[i]
    stripped = line.lstrip(" ")
    indent = leading_spaces(line)

    # Check if we're starting the app service
    if not in_app_service and re.match(r"^\s*app:\s*$", line):
        in_app_service = True
        app_indent = indent
        app_service_indent = None
        build_found = False
        out.append(line)
        i += 1
        continue

    # Check if we've exited the app service (found another top-level service)
    if in_app_service and indent <= app_indent and re.match(r"^[A-Za-z0-9_-]+:\s*$", stripped):
        # We've left the app service - insert image if we haven't already
        if build_found and app_service_indent is not None:
            out.append(f"{' ' * app_service_indent}image: {target_image}\n")
        in_app_service = False
        out.append(line)
        i += 1
        continue

    # Process lines within the app service
    if in_app_service:
        if app_service_indent is None and indent > app_indent:
            app_service_indent = indent

        # Check for image key (already has an image, don't add)
        if re.match(rf"^\s+image:\s*", line):
            in_app_service = False
            out.append(line)
            i += 1
            continue

        # Check for build block
        if re.match(rf"^\s+build:\s*$", line):
            build_found = True
            out.append(line)
            i += 1
            # Skip all lines that are part of the build block (indented more than app_service_indent)
            while i < len(lines):
                next_line = lines[i]
                next_indent = leading_spaces(next_line)
                if next_indent > app_service_indent and next_line.strip():
                    out.append(next_line)
                    i += 1
                else:
                    break
            continue

        # Insert image after build block before first property
        if build_found and app_service_indent is not None and indent == app_service_indent:
            # Check if this is a property line (not build)
            if not re.match(rf"^\s+build:", line):
                out.append(f"{' ' * app_service_indent}image: {target_image}\n")
                build_found = False  # Mark that we've inserted the image

        out.append(line)
        i += 1
        continue

    out.append(line)
    i += 1

# If we ended while still in the app service, append image at the end
if in_app_service and build_found and app_service_indent is not None:
    out.append(f"{' ' * app_service_indent}image: {target_image}\n")

with open(compose_file, "w", encoding="utf-8") as f:
    f.writelines(out)
PY

    done
}

install_docker_if_missing() {
    if command -v docker >/dev/null 2>&1; then
        return 0
    fi

    echo "Installing Docker..."
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose-v2 curl python3
    sudo systemctl enable --now docker
}

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --migrate-legacy-db           Back up host MongoDB and import into Docker MongoDB
  --remove-legacy-system        Remove old host MongoDB/system after successful import
    --skip-cleanup-old            Do not run cleanup-old.sh after install
    --cleanup-old-remove-cron     Also remove matching cron entries during old-system cleanup
    --multitenant                Use docker-compose-multitenant.yml (default)
  --legacy-db-name <name>       Legacy database name (default: $LEGACY_DB_NAME)
  --legacy-mongo-uri <uri>      Legacy Mongo URI (default: $LEGACY_MONGO_URI)
  --legacy-system-dir <path>    Optional old system directory to remove after migration
  -h, --help                    Show this help message
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --migrate-legacy-db)
                MIGRATE_LEGACY_DB=true
                shift
                ;;
            --remove-legacy-system)
                REMOVE_LEGACY_SYSTEM=true
                shift
                ;;
            --skip-cleanup-old)
                CLEANUP_OLD_SERVICES=false
                shift
                ;;
            --cleanup-old-remove-cron)
                CLEANUP_OLD_REMOVE_CRON=true
                shift
                ;;
            --multitenant)
                COMPOSE_FILE="docker-compose-multitenant.yml"
                shift
                ;;
            --legacy-db-name)
                LEGACY_DB_NAME="$2"
                shift 2
                ;;
            --legacy-mongo-uri)
                LEGACY_MONGO_URI="$2"
                shift 2
                ;;
            --legacy-system-dir)
                LEGACY_SYSTEM_DIR="$2"
                shift 2
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

install_mongo_tools_if_missing() {
    if command -v mongodump >/dev/null 2>&1 && command -v mongorestore >/dev/null 2>&1; then
        return 0
    fi

    echo "Installing MongoDB database tools..."
    sudo apt-get update
    sudo apt-get install -y mongodb-database-tools || sudo apt-get install -y mongo-tools
}

backup_legacy_database() {
    local backup_dir timestamp archive collection_count

    if [ "$MIGRATE_LEGACY_DB" != "true" ]; then
        return 0
    fi

    install_mongo_tools_if_missing

    if ! command -v mongosh >/dev/null 2>&1; then
        echo "Warning: mongosh not found, skipping legacy DB migration"
        MIGRATE_LEGACY_DB=false
        return 0
    fi

    if ! mongosh --quiet "$LEGACY_MONGO_URI/$LEGACY_DB_NAME" --eval "db.runCommand({ping:1}).ok" >/dev/null 2>&1; then
        echo "No legacy MongoDB reachable at $LEGACY_MONGO_URI, skipping migration"
        MIGRATE_LEGACY_DB=false
        return 0
    fi

    collection_count="$(mongosh --quiet "$LEGACY_MONGO_URI/$LEGACY_DB_NAME" --eval "db.getCollectionNames().length" 2>/dev/null || echo 0)"
    if [ "${collection_count:-0}" -eq 0 ]; then
        echo "Legacy DB '$LEGACY_DB_NAME' has no collections, skipping migration"
        MIGRATE_LEGACY_DB=false
        return 0
    fi

    backup_dir="$PROJECT_DIR/backups/legacy-migration"
    timestamp="$(date +%Y-%m-%d_%H-%M-%S)"
    archive="$backup_dir/${LEGACY_DB_NAME}-${timestamp}.archive.gz"

    sudo mkdir -p "$backup_dir"
    echo "Creating legacy MongoDB backup: $archive"
    mongodump --uri "$LEGACY_MONGO_URI" --db "$LEGACY_DB_NAME" --archive="$archive" --gzip

    if [ ! -s "$archive" ]; then
        echo "Error: legacy backup archive was not created"
        exit 1
    fi

    LEGACY_BACKUP_ARCHIVE="$archive"
}

restore_legacy_backup_into_docker() {
    local i
    local compose_path

    if [ "$MIGRATE_LEGACY_DB" != "true" ] || [ -z "$LEGACY_BACKUP_ARCHIVE" ]; then
        return 0
    fi

    compose_path="$PROJECT_DIR/$COMPOSE_FILE"
    if [ ! -f "$compose_path" ]; then
        echo "Error: compose file not found: $compose_path"
        exit 1
    fi

    echo "Waiting for Docker MongoDB to become ready..."
    for i in $(seq 1 60); do
        if sudo docker compose -f "$compose_path" exec -T mongodb mongosh --quiet --eval "db.adminCommand({ping:1}).ok" >/dev/null 2>&1; then
            break
        fi
        sleep 2
    done

    if [ "$i" -eq 60 ]; then
        echo "Error: Docker MongoDB did not become ready in time"
        exit 1
    fi

    echo "Importing legacy backup into Docker MongoDB..."
    sudo docker compose -f "$compose_path" exec -T mongodb mongorestore --archive --gzip --drop --nsInclude "${LEGACY_DB_NAME}.*" < "$LEGACY_BACKUP_ARCHIVE"
    echo "Legacy DB import completed."
}

cleanup_legacy_system() {
    if [ "$REMOVE_LEGACY_SYSTEM" != "true" ] || [ "$MIGRATE_LEGACY_DB" != "true" ] || [ -z "$LEGACY_BACKUP_ARCHIVE" ]; then
        return 0
    fi

    echo "Cleaning up old host MongoDB/system..."

    if [ "$LEGACY_SERVICE_CLEANUP" = "true" ] && command -v systemctl >/dev/null 2>&1; then
        sudo systemctl stop mongod >/dev/null 2>&1 || true
        sudo systemctl stop mongodb >/dev/null 2>&1 || true
        sudo systemctl disable mongod >/dev/null 2>&1 || true
        sudo systemctl disable mongodb >/dev/null 2>&1 || true
    fi

    sudo rm -rf /var/lib/mongodb /var/log/mongodb 2>/dev/null || true
    sudo apt-get purge -y mongodb mongodb-server mongodb-org mongodb-org-server mongodb-org-shell mongodb-org-mongos mongodb-database-tools mongo-tools >/dev/null 2>&1 || true
    sudo apt-get autoremove -y >/dev/null 2>&1 || true

    if [ -n "$LEGACY_SYSTEM_DIR" ] && [ -d "$LEGACY_SYSTEM_DIR" ] && [ "$LEGACY_SYSTEM_DIR" != "$PROJECT_DIR" ]; then
        echo "Removing legacy system directory: $LEGACY_SYSTEM_DIR"
        sudo rm -rf "$LEGACY_SYSTEM_DIR"
    fi

    echo "Legacy cleanup complete."
}

cleanup_old_services() {
    local cleanup_script
    cleanup_script="$PROJECT_DIR/cleanup-old.sh"

    if [ "$CLEANUP_OLD_SERVICES" != "true" ]; then
        return 0
    fi

    if [ ! -x "$cleanup_script" ]; then
        echo "Warning: cleanup script not found at $cleanup_script, skipping old-system service cleanup"
        return 0
    fi

    echo "Cleaning up old services/processes..."
    if [ "$CLEANUP_OLD_REMOVE_CRON" = "true" ]; then
        sudo bash "$cleanup_script" --remove-cron || true
    else
        sudo bash "$cleanup_script" || true
    fi
}

latest_tag_and_bundle_url() {
    local meta_file
    meta_file="$1"

    curl -fsSL "$API_URL" -o "$meta_file"

    python3 - <<'PY' "$meta_file" "$BUNDLE_ASSET"
import json, sys
meta_file, asset_name = sys.argv[1], sys.argv[2]
with open(meta_file, 'r', encoding='utf-8') as f:
    data = json.load(f)
tag = data.get('tag_name', '').strip()
url = ''
image_url = ''
for asset in data.get('assets', []):
    if asset.get('name') == asset_name:
        url = asset.get('browser_download_url', '').strip()
        break
for asset in data.get('assets', []):
    if asset.get('name') == f'inventarsystem-image-{tag}.tar.gz':
        image_url = asset.get('browser_download_url', '').strip()
        break
print(tag)
print(url)
print(image_url)
PY
}

main() {
    parse_args "$@"

    install_docker_if_missing
    need_cmd docker
    need_cmd tar
    need_cmd python3
    need_cmd curl

    local meta_file tag bundle_url image_url
    TMP_DIR="$(mktemp -d)"
    meta_file="$TMP_DIR/release.json"
    trap cleanup_tmp_dir EXIT

    mapfile -t release_info < <(latest_tag_and_bundle_url "$meta_file")
    tag="${release_info[0]:-}"
    bundle_url="${release_info[1]:-}"
    image_url="${release_info[2]:-}"

    if [ -z "$tag" ] || [ -z "$bundle_url" ]; then
        echo "Error: latest release metadata is incomplete."
        echo "Expected release asset: $BUNDLE_ASSET"
        exit 1
    fi

    echo "Installing Inventarsystem release $tag into $PROJECT_DIR"
    sudo mkdir -p "$PROJECT_DIR"

    curl -fL "$bundle_url" -o "$TMP_DIR/$BUNDLE_ASSET"
    sudo tar -xzf "$TMP_DIR/$BUNDLE_ASSET" -C "$PROJECT_DIR"

    pin_compose_app_image "$tag"

    if [ -z "$image_url" ]; then
        echo "Error: release image asset is missing"
        exit 1
    fi

    curl -fL "$image_url" -o "$TMP_DIR/inventarsystem-image-$tag.tar.gz"
    sudo docker load -i "$TMP_DIR/inventarsystem-image-$tag.tar.gz" >/dev/null
    # Compatibility alias: some legacy compose bundles may still reference :latest.
    sudo docker tag "ghcr.io/aiirondev/legendary-octo-garbanzo:$tag" "ghcr.io/aiirondev/legendary-octo-garbanzo:latest" >/dev/null 2>&1 || true

    if [ ! -f "$PROJECT_DIR/start.sh" ]; then
        echo "Error: release bundle is missing start.sh"
        exit 1
    fi
    if [ ! -f "$PROJECT_DIR/stop.sh" ]; then
        echo "Error: release bundle is missing stop.sh"
        exit 1
    fi
    if [ ! -f "$PROJECT_DIR/restart.sh" ]; then
        cat > "$TMP_DIR/restart.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$SCRIPT_DIR/stop.sh"
"$SCRIPT_DIR/start.sh"
EOF
        sudo install -m 755 "$TMP_DIR/restart.sh" "$PROJECT_DIR/restart.sh"
    fi

    refresh_start_script_from_main

    if [ ! -f "$PROJECT_DIR/cleanup-old.sh" ] && [ -f "$INSTALLER_DIR/cleanup-old.sh" ]; then
        sudo install -m 755 "$INSTALLER_DIR/cleanup-old.sh" "$PROJECT_DIR/cleanup-old.sh"
    fi

    sudo chmod +x "$PROJECT_DIR/start.sh" "$PROJECT_DIR/stop.sh" "$PROJECT_DIR/restart.sh"
    [ -f "$PROJECT_DIR/cleanup-old.sh" ] && sudo chmod +x "$PROJECT_DIR/cleanup-old.sh"

    echo "$tag" | sudo tee "$PROJECT_DIR/.release-version" >/dev/null

    if [ ! -f "$PROJECT_DIR/.docker-build.env" ]; then
        cat > "$TMP_DIR/.docker-build.env" <<EOF
NUITKA_BUILD=0
INVENTAR_HTTP_PORT=10000
INVENTAR_HTTPS_PORT=10001
INVENTAR_APP_IMAGE=ghcr.io/aiirondev/legendary-octo-garbanzo:$tag
EOF
        sudo install -m 644 "$TMP_DIR/.docker-build.env" "$PROJECT_DIR/.docker-build.env"
    elif sudo grep -q '^INVENTAR_APP_IMAGE=' "$PROJECT_DIR/.docker-build.env"; then
        sudo sed -i "s|^INVENTAR_APP_IMAGE=.*|INVENTAR_APP_IMAGE=ghcr.io/aiirondev/legendary-octo-garbanzo:$tag|" "$PROJECT_DIR/.docker-build.env"
    else
        echo "INVENTAR_APP_IMAGE=ghcr.io/aiirondev/legendary-octo-garbanzo:$tag" | sudo tee -a "$PROJECT_DIR/.docker-build.env" >/dev/null
    fi

    backup_legacy_database

    echo "Starting stack..."
    sudo env INVENTAR_APP_IMAGE="ghcr.io/aiirondev/legendary-octo-garbanzo:$tag" bash "$PROJECT_DIR/start.sh"

    restore_legacy_backup_into_docker
    cleanup_old_services
    cleanup_legacy_system

    echo "Installation complete."
    echo "Open: https://localhost"
}

main "$@"
