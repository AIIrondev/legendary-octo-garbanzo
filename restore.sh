#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/restore.log"
WORK_DIR="$(mktemp -d /tmp/inventarsystem-restore-XXXXXX)"

DB_NAME="${INVENTAR_MONGODB_DB:-Inventarsystem}"
SOURCE_PATH=""
BACKUP_DATE=""
DROP_DATABASE=false
RESTART_SERVICES=false
STAGED_PATH=""

BACKUP_ROOT_LOCAL="$SCRIPT_DIR/backups"
BACKUP_ROOT_SYSTEM="/var/backups"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

DOCKER_COMPOSE=()

cleanup() {
    rm -rf "$WORK_DIR" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "$LOG_DIR"

log() {
    local msg="$1"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $msg" | tee -a "$LOG_FILE"
}

show_help() {
    cat <<EOF
Inventarsystem Restore / Porting Tool (Docker-first)

Usage:
  $0 --source <path> [options]
  $0 --date <YYYY-MM-DD|latest> [options]
  $0 --list

Options:
  --source <path>         Backup source path.
                          Supported:
                          - old folder with CSV files
                          - old Inventarsystem-*.tar.gz backup
                          - new mongodb-*.archive.gz backup
                          - folder containing mongodb-*.archive.gz
  --date <value>          Resolve source from known backup locations.
                          - YYYY-MM-DD: checks backups/YYYY-MM-DD and /var/backups/Inventarsystem-YYYY-MM-DD(.tar.gz)
                          - latest: newest from local/system backup roots
  --drop-database         Drop target DB before import (recommended for full restore)
  --restart-services      Restart stack after restore
  --list                  List detected backup candidates
  --help                  Show this help

Notes:
  - Always restores into current DB name: $DB_NAME
  - Supports both legacy CSV and new archive backups
  - Normalizes collection names to current structure (users, items, ausleihungen, filter_presets, settings)
EOF
}

setup_compose() {
    if docker compose version >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
        DOCKER_COMPOSE=(docker compose)
        return 0
    fi

    if [ -n "$SUDO" ] && $SUDO docker compose version >/dev/null 2>&1 && $SUDO docker info >/dev/null 2>&1; then
        DOCKER_COMPOSE=($SUDO docker compose)
        return 0
    fi

    log "ERROR: docker compose is not available"
    exit 1
}

compose() {
    "${DOCKER_COMPOSE[@]}" "$@"
}

list_backups() {
    echo "Detected backup candidates:"

    if [ -d "$BACKUP_ROOT_LOCAL" ]; then
        find "$BACKUP_ROOT_LOCAL" -maxdepth 2 \( -type d -name "20*" -o -type f -name "*.archive.gz" -o -type f -name "Inventarsystem-*.tar.gz" \) 2>/dev/null | sort
    fi

    if [ -d "$BACKUP_ROOT_SYSTEM" ]; then
        find "$BACKUP_ROOT_SYSTEM" -maxdepth 1 \( -type d -name "Inventarsystem-*" -o -type f -name "Inventarsystem-*.tar.gz" \) 2>/dev/null | sort
    fi
}

resolve_latest_source() {
    local latest
    latest="$({
        if [ -d "$BACKUP_ROOT_LOCAL" ]; then
            find "$BACKUP_ROOT_LOCAL" -maxdepth 2 \( -type d -name "20*" -o -type f -name "*.archive.gz" -o -type f -name "Inventarsystem-*.tar.gz" \) -printf '%T@ %p\n' 2>/dev/null
        fi
        if [ -d "$BACKUP_ROOT_SYSTEM" ]; then
            find "$BACKUP_ROOT_SYSTEM" -maxdepth 1 \( -type d -name "Inventarsystem-*" -o -type f -name "Inventarsystem-*.tar.gz" \) -printf '%T@ %p\n' 2>/dev/null
        fi
    } | sort -nr | head -n1 | cut -d' ' -f2-)"

    if [ -z "$latest" ]; then
        log "ERROR: no backup candidates found"
        exit 1
    fi

    SOURCE_PATH="$latest"
}

resolve_date_source() {
    local d="$1"

    if [ "$d" = "latest" ]; then
        resolve_latest_source
        return
    fi

    local p1="$BACKUP_ROOT_LOCAL/$d"
    local p2="$BACKUP_ROOT_SYSTEM/Inventarsystem-$d"
    local p3="$BACKUP_ROOT_SYSTEM/Inventarsystem-$d.tar.gz"

    if [ -e "$p1" ]; then
        SOURCE_PATH="$p1"
    elif [ -e "$p2" ]; then
        SOURCE_PATH="$p2"
    elif [ -e "$p3" ]; then
        SOURCE_PATH="$p3"
    else
        log "ERROR: no backup found for date $d"
        exit 1
    fi
}

ensure_stack() {
    log "Ensuring mongodb/app services are running..."
    compose up -d mongodb app >/dev/null

    if ! compose ps --status running mongodb | grep -q mongodb; then
        log "ERROR: mongodb container is not running"
        exit 1
    fi

    if ! compose ps --status running app | grep -q app; then
        log "ERROR: app container is not running"
        exit 1
    fi
}

stage_source() {
    local src="$1"

    if [ ! -e "$src" ]; then
        log "ERROR: source path does not exist: $src"
        exit 1
    fi

    if [ -f "$src" ] && [[ "$src" == *.tar.gz ]]; then
        log "Extracting tar backup: $src"
        tar -xzf "$src" -C "$WORK_DIR"
        STAGED_PATH="$WORK_DIR"
        return
    fi

    if [ -f "$src" ]; then
        cp -f "$src" "$WORK_DIR/"
        STAGED_PATH="$WORK_DIR"
        return
    fi

    if [ -d "$src" ]; then
        STAGED_PATH="$src"
        return
    fi

    log "ERROR: unsupported source type: $src"
    exit 1
}

find_archive_file() {
    local root="$1"
    find "$root" -type f \( -name "*.archive.gz" -o -name "*.archive" \) 2>/dev/null | head -n1 || true
}

find_best_csv_dir() {
    local root="$1"
    local best_dir=""
    local best_count=0

    while IFS= read -r dir; do
        [ -z "$dir" ] && continue
        local count
        count="$(find "$dir" -maxdepth 1 -type f -name '*.csv' | wc -l | tr -d ' ')"
        if [ "$count" -gt "$best_count" ]; then
            best_count="$count"
            best_dir="$dir"
        fi
    done < <(find "$root" -type f -name '*.csv' -printf '%h\n' 2>/dev/null | sort -u)

    if [ "$best_count" -gt 0 ]; then
        echo "$best_dir"
    fi
}

normalize_structure() {
    local py="$WORK_DIR/normalize_db.py"

    cat > "$py" <<'PY'
from pymongo import MongoClient
import os

db_name = os.getenv("DB_NAME", "Inventarsystem")
host = os.getenv("INVENTAR_MONGODB_HOST", "mongodb")
port = int(os.getenv("INVENTAR_MONGODB_PORT", "27017"))

client = MongoClient(host, port)
db = client[db_name]

rename_map = {
    "user": "users",
    "item": "items",
    "ausleihung": "ausleihungen",
    "filter_preset": "filter_presets",
    "preset": "filter_presets",
    "setting": "settings",
}

for old, new in rename_map.items():
    if old not in db.list_collection_names():
        continue

    if new not in db.list_collection_names():
        db[old].rename(new)
        print(f"Renamed collection {old} -> {new}")
        continue

    moved = 0
    for doc in db[old].find({}):
        db[new].insert_one(doc)
        moved += 1
    db[old].drop()
    print(f"Merged {moved} docs from {old} into {new}")

print("Final collections:", sorted(db.list_collection_names()))
PY

    local app_cid
    app_cid="$(compose ps -q app)"

    $SUDO docker cp "$py" "$app_cid:/tmp/normalize_db.py"
    compose exec -T app env DB_NAME="$DB_NAME" python /tmp/normalize_db.py
}

import_archive() {
    local archive_file="$1"
    local mongo_cid

    mongo_cid="$(compose ps -q mongodb)"
    if [ -z "$mongo_cid" ]; then
        log "ERROR: could not resolve mongodb container id"
        exit 1
    fi

    log "Importing archive backup: $archive_file"
    $SUDO docker cp "$archive_file" "$mongo_cid:/tmp/restore.archive.gz"

    local drop_flag=""
    if [ "$DROP_DATABASE" = true ]; then
        drop_flag="--drop"
    fi

    compose exec -T mongodb sh -lc "mongorestore --archive=/tmp/restore.archive.gz --gzip $drop_flag"
    compose exec -T mongodb rm -f /tmp/restore.archive.gz >/dev/null 2>&1 || true

    normalize_structure
}

import_csv() {
    local csv_dir="$1"
    local app_cid py

    app_cid="$(compose ps -q app)"
    if [ -z "$app_cid" ]; then
        log "ERROR: could not resolve app container id"
        exit 1
    fi

    log "Importing CSV backup directory: $csv_dir"
    compose exec -T app sh -lc "rm -rf /tmp/restore_csv && mkdir -p /tmp/restore_csv"
    $SUDO docker cp "$csv_dir/." "$app_cid:/tmp/restore_csv"

    py="$WORK_DIR/import_csv.py"
    cat > "$py" <<'PY'
import os
import csv
import ast
import re
from pymongo import MongoClient
from bson.objectid import ObjectId

DB_NAME = os.getenv("DB_NAME", "Inventarsystem")
CSV_DIR = os.getenv("CSV_DIR", "/tmp/restore_csv")
DROP_DATABASE = os.getenv("DROP_DATABASE", "false").lower() == "true"
HOST = os.getenv("INVENTAR_MONGODB_HOST", "mongodb")
PORT = int(os.getenv("INVENTAR_MONGODB_PORT", "27017"))

COLLECTION_MAP = {
    "users": "users",
    "user": "users",
    "items": "items",
    "item": "items",
    "ausleihungen": "ausleihungen",
    "ausleihung": "ausleihungen",
    "filter_presets": "filter_presets",
    "filter_preset": "filter_presets",
    "settings": "settings",
    "setting": "settings",
}

BOOL_FIELDS = {"Admin", "Verfuegbar", "enabled"}
INT_FIELDS = {"Anschaffungskosten", "filter_num"}
OID_LIKE_FIELDS = {"_id", "Item"}

client = MongoClient(HOST, PORT)
db = client[DB_NAME]

if DROP_DATABASE:
    client.drop_database(DB_NAME)
    db = client[DB_NAME]


def parse_scalar(key, value):
    if value is None:
        return None

    value = value.strip()
    if value == "":
        return None

    if key in BOOL_FIELDS:
        lowered = value.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

    if key in INT_FIELDS:
        try:
            return int(value)
        except Exception:
            pass

    if key in OID_LIKE_FIELDS and re.fullmatch(r"[0-9a-fA-F]{24}", value):
        return ObjectId(value)

    if value.startswith("[") and value.endswith("]"):
        try:
            return ast.literal_eval(value)
        except Exception:
            pass

    return value


def load_csv_file(csv_path):
    docs = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            doc = {}
            for key, value in row.items():
                doc[key] = parse_scalar(key, value)
            docs.append(doc)
    return docs


csv_files = [
    os.path.join(CSV_DIR, f)
    for f in sorted(os.listdir(CSV_DIR))
    if f.endswith(".csv")
]

if not csv_files:
    raise SystemExit(f"No CSV files found in {CSV_DIR}")

for csv_file in csv_files:
    base = os.path.splitext(os.path.basename(csv_file))[0]
    coll = COLLECTION_MAP.get(base, base)

    docs = load_csv_file(csv_file)
    db[coll].drop()
    if docs:
        db[coll].insert_many(docs)
    print(f"Imported {len(docs)} docs into {coll} from {os.path.basename(csv_file)}")

print("Collections after CSV import:", sorted(db.list_collection_names()))
PY

    $SUDO docker cp "$py" "$app_cid:/tmp/import_csv.py"
    compose exec -T app env DB_NAME="$DB_NAME" CSV_DIR="/tmp/restore_csv" DROP_DATABASE="$DROP_DATABASE" python /tmp/import_csv.py

    normalize_structure
}

print_counts() {
    local py="$WORK_DIR/print_counts.py"

    cat > "$py" <<'PY'
from pymongo import MongoClient
import os

db_name = os.getenv("DB_NAME", "Inventarsystem")
host = os.getenv("INVENTAR_MONGODB_HOST", "mongodb")
port = int(os.getenv("INVENTAR_MONGODB_PORT", "27017"))

client = MongoClient(host, port)
db = client[db_name]

for name in ["users", "items", "ausleihungen", "filter_presets", "settings"]:
    try:
        count = db[name].count_documents({})
    except Exception:
        count = -1
    print(f"{name}: {count}")
PY

    local app_cid
    app_cid="$(compose ps -q app)"
    $SUDO docker cp "$py" "$app_cid:/tmp/print_counts.py"

    log "Post-restore collection counts:"
    compose exec -T app env DB_NAME="$DB_NAME" python /tmp/print_counts.py | tee -a "$LOG_FILE"
}

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --source)
                SOURCE_PATH="${2:-}"
                shift 2
                ;;
            --date)
                BACKUP_DATE="${2:-}"
                shift 2
                ;;
            --drop-database)
                DROP_DATABASE=true
                shift
                ;;
            --restart-services)
                RESTART_SERVICES=true
                shift
                ;;
            --list)
                list_backups
                exit 0
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                echo "Unknown argument: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

main() {
    parse_args "$@"
    setup_compose

    if [ -n "$SOURCE_PATH" ] && [ -n "$BACKUP_DATE" ]; then
        log "ERROR: use either --source or --date, not both"
        exit 1
    fi

    if [ -z "$SOURCE_PATH" ] && [ -n "$BACKUP_DATE" ]; then
        resolve_date_source "$BACKUP_DATE"
    fi

    if [ -z "$SOURCE_PATH" ]; then
        log "ERROR: provide --source <path> or --date <YYYY-MM-DD|latest>"
        show_help
        exit 1
    fi

    ensure_stack

    local staged archive_file csv_dir
    stage_source "$SOURCE_PATH"
    staged="$STAGED_PATH"
    archive_file="$(find_archive_file "$staged")"

    if [ -n "$archive_file" ]; then
        import_archive "$archive_file"
        print_counts
    else
        csv_dir="$(find_best_csv_dir "$staged")"
        if [ -z "$csv_dir" ]; then
            log "ERROR: no supported backup data found under: $SOURCE_PATH"
            log "Expected either *.archive.gz or CSV files"
            exit 1
        fi
        import_csv "$csv_dir"
        print_counts
    fi

    if [ "$RESTART_SERVICES" = true ]; then
        log "Restarting services..."
        "$SCRIPT_DIR/restart.sh"
    fi

    log "Restore completed successfully into DB: $DB_NAME"
}

main "$@"
