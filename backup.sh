#!/usr/bin/env bash
set -euo pipefail

# ========================================================
# Inventarsystem backup helper
# - Creates a dated backup folder/archive under /var/backups (by default)
# - Exports MongoDB via run-backup.sh into mongodb_backup/
# - Cleans up backups older than KEEP_DAYS
#
# Options:
#   --dest|--out|--backup-dir <dir>   Destination base directory (default: /var/backups)
#   --db|--db-name <name>             MongoDB database name (default: Inventarsystem)
#   --uri|--mongo-uri <uri>           MongoDB URI (default: mongodb://localhost:27017/)
#   --invoice-archive-dir <dir>       Invoice archive directory (default: <dest>/invoice-archive)
#   --invoice-keep-days <N>           Retention for invoice archive in days (default: 3650)
#   --log <file>                      Log file (default: ./logs/backup.log)
#   --no-compress                     Disable compression (keeps directory instead of .tar.gz)
#   --compress-level <0-9>            Compression level flag (only 0 is special here)
#   --keep-days <N>                   Age-based retention in days (default: 7; 0 disables age filter)
#   --min-keep <N>                    Always keep at least N most recent backups (default: 7)
#   --mode <auto|host|docker>         Backup mode (default: auto)
#   -h|--help                         Show help
# ========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SCRIPT_DIR}"
# Default destination now /var/backups; override with --dest or BACKUP_BASE_DIR env
BACKUP_BASE_DIR="${BACKUP_BASE_DIR:-/var/backups}"
LOG_DIR="$PROJECT_DIR/logs"
# Create only the log directory here; backup dir is created later with sudo if needed
mkdir -p "$LOG_DIR"
LOG_FILE="${LOG_FILE:-$LOG_DIR/backup.log}"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-9}"
KEEP_DAYS="${KEEP_DAYS:-7}"
MIN_KEEP="${MIN_KEEP:-7}"
DB_NAME="${DB_NAME:-Inventarsystem}"
MONGO_URI="${MONGO_URI:-mongodb://localhost:27017/}"
INVOICE_KEEP_DAYS="${INVOICE_KEEP_DAYS:-3650}"
INVOICE_ARCHIVE_DIR="${INVOICE_ARCHIVE_DIR:-$BACKUP_BASE_DIR/invoice-archive}"
BACKUP_MODE="${BACKUP_MODE:-auto}"
DOCKER_AVAILABLE=0
DOCKER_COMPOSE_CMD=()
USE_NULL_OUTPUT=false

usage() {
    cat <<EOF
Usage: $(basename "$0") [options]

Options:
  --dest|--out|--backup-dir <dir>   Destination base directory (default: $BACKUP_BASE_DIR)
  --db|--db-name <name>             MongoDB database name (default: $DB_NAME)
  --uri|--mongo-uri <uri>           MongoDB URI (default: $MONGO_URI)
    --invoice-archive-dir <dir>       Invoice archive directory (default: $INVOICE_ARCHIVE_DIR)
    --invoice-keep-days <N>           Retention for invoice archive in days (default: $INVOICE_KEEP_DAYS)
  --log <file>                      Log file (default: $LOG_FILE)
  --no-compress                     Disable compression (keeps directory instead of .tar.gz)
  --compress-level <0-9>            Compression level flag (only 0 is special here)
    --keep-days <N>                   Age-based retention in days (default: $KEEP_DAYS; 0 disables age filter)
    --min-keep <N>                    Always keep at least this many backups (default: $MIN_KEEP)
    --mode <auto|host|docker>         Backup mode (default: $BACKUP_MODE)
  -h|--help                         Show this help and exit
EOF
}

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dest|--out|--backup-dir)
            BACKUP_BASE_DIR="$2"; shift 2;;
        --db|--db-name)
            DB_NAME="$2"; shift 2;;
        --uri|--mongo-uri)
            MONGO_URI="$2"; shift 2;;
        --invoice-archive-dir)
            INVOICE_ARCHIVE_DIR="$2"; shift 2;;
        --invoice-keep-days)
            INVOICE_KEEP_DAYS="$2"; shift 2;;
        --log)
            LOG_FILE="$2"; shift 2;;
        --no-compress)
            COMPRESSION_LEVEL=0; shift;;
        --compress-level)
            COMPRESSION_LEVEL="${2:-6}"; shift 2;;
        --keep-days)
            KEEP_DAYS="$2"; shift 2;;
        --min-keep)
            MIN_KEEP="$2"; shift 2;;
        --mode)
            BACKUP_MODE="$2"; shift 2;;
        -h|--help)
            usage; exit 0;;
        *)
            echo "Unknown option: $1" >&2; usage; exit 2;;
    esac
done

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE" 2>/dev/null || echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

init_docker_compose() {
    if docker compose version >/dev/null 2>&1; then
        DOCKER_AVAILABLE=1
        DOCKER_COMPOSE_CMD=(docker compose -f "$PROJECT_DIR/docker-compose.yml")
        return 0
    fi
    if sudo docker compose version >/dev/null 2>&1; then
        DOCKER_AVAILABLE=1
        DOCKER_COMPOSE_CMD=(sudo docker compose -f "$PROJECT_DIR/docker-compose.yml")
        return 0
    fi

    DOCKER_AVAILABLE=0
    DOCKER_COMPOSE_CMD=()
    return 1
}

compose_cmd() {
    if [ "$DOCKER_AVAILABLE" -ne 1 ]; then
        return 1
    fi
    "${DOCKER_COMPOSE_CMD[@]}" "$@"
}

try_backup_db_docker() {
    local out_dir="$1"
    local stamp
    stamp="$(date +"%Y-%m-%d_%H-%M-%S")"
    local archive_path="$out_dir/mongodb-${stamp}.archive.gz"

    [ "$DOCKER_AVAILABLE" -eq 1 ] || return 1

    log_message "Attempting Docker-based MongoDB backup..."
    compose_cmd up -d mongodb >/dev/null 2>&1 || return 1
    if ! compose_cmd ps --status running mongodb | grep -q mongodb; then
        return 1
    fi

    if compose_cmd exec -T mongodb sh -c "mongodump --archive --gzip --db '$DB_NAME'" > "$archive_path"; then
        log_message "Docker DB backup successful: $archive_path"
        return 0
    fi
    return 1
}

try_backup_invoices_docker() {
    local archive_base="$1"
    [ "$DOCKER_AVAILABLE" -eq 1 ] || return 1

    local tmp_base
    tmp_base="/tmp/$(basename "$archive_base")"

    log_message "Attempting Docker-based invoice archive export..."
    compose_cmd up -d mongodb app >/dev/null 2>&1 || return 1
    if ! compose_cmd ps --status running app | grep -q app; then
        return 1
    fi

    local app_cid
    app_cid="$(compose_cmd ps -q app)"
    [ -n "$app_cid" ] || return 1

    if ! sudo docker cp "$PROJECT_DIR/Backup-Invoices.py" "$app_cid:/tmp/Backup-Invoices.py" >/dev/null 2>&1; then
        return 1
    fi

    if ! compose_cmd exec -T app python /tmp/Backup-Invoices.py \
        --uri "mongodb://mongodb:27017/" \
        --db "$DB_NAME" \
        --out "$tmp_base" >/dev/null 2>&1; then
        return 1
    fi

    sudo docker cp "$app_cid:${tmp_base}.jsonl" "${archive_base}.jsonl" >/dev/null 2>&1 || return 1
    sudo docker cp "$app_cid:${tmp_base}.csv" "${archive_base}.csv" >/dev/null 2>&1 || return 1
    sudo docker cp "$app_cid:${tmp_base}.meta.json" "${archive_base}.meta.json" >/dev/null 2>&1 || return 1

    compose_cmd exec -T app sh -c "rm -f /tmp/Backup-Invoices.py ${tmp_base}.jsonl ${tmp_base}.csv ${tmp_base}.meta.json" >/dev/null 2>&1 || true
    return 0
}

backup_invoices_archive() {
    log_message "Starting invoice archive export..."

    # Ensure archive dir exists and is writable
    if [ ! -d "$INVOICE_ARCHIVE_DIR" ]; then
        sudo mkdir -p "$INVOICE_ARCHIVE_DIR"
        sudo chmod 755 "$INVOICE_ARCHIVE_DIR"
    fi

    local timestamp
    timestamp="$(date +"%Y-%m-%d_%H-%M-%S")"
    local archive_base
    archive_base="$INVOICE_ARCHIVE_DIR/invoices-$timestamp"

    local py_exec
    if [ -x "$PROJECT_DIR/.venv/bin/python" ]; then
        py_exec="$PROJECT_DIR/.venv/bin/python"
    else
        py_exec="python3"
    fi

    local host_invoice_ok=0
    local prefer_docker_invoice=0
    if [ "$BACKUP_MODE" = "auto" ] && [ "$DOCKER_AVAILABLE" -eq 1 ] && [ "$MONGO_URI" = "mongodb://localhost:27017/" ]; then
        prefer_docker_invoice=1
        log_message "Auto mode: preferring Docker invoice archive export"
    fi

    if [ "$BACKUP_MODE" != "docker" ] && [ "$prefer_docker_invoice" -ne 1 ]; then
        if [ "${USE_NULL_OUTPUT:-false}" = true ]; then
            if sudo -E "$py_exec" "$PROJECT_DIR/Backup-Invoices.py" --uri "$MONGO_URI" --db "$DB_NAME" --out "$archive_base" > /dev/null 2>&1; then
                host_invoice_ok=1
            fi
        else
            if sudo -E "$py_exec" "$PROJECT_DIR/Backup-Invoices.py" --uri "$MONGO_URI" --db "$DB_NAME" --out "$archive_base" >> "$PROJECT_DIR/logs/Backup_db.log" 2>&1; then
                host_invoice_ok=1
            fi
        fi
    fi

    if [ "$host_invoice_ok" -ne 1 ]; then
        if [ "$BACKUP_MODE" = "host" ]; then
            log_message "ERROR: Failed to export invoice archive in host mode"
            return 1
        fi
        if ! try_backup_invoices_docker "$archive_base"; then
            log_message "ERROR: Failed to export invoice archive"
            return 1
        fi
    fi

    sudo chmod 640 "$archive_base".jsonl "$archive_base".csv "$archive_base".meta.json 2>/dev/null || true
    log_message "Invoice archive written: $archive_base.(jsonl|csv|meta.json)"

    # Retention cleanup for invoice archive (default: 10 years)
    if [ "$INVOICE_KEEP_DAYS" -gt 0 ]; then
        local deleted_count=0
        while IFS= read -r old_file; do
            [ -z "$old_file" ] && continue
            if sudo rm -f "$old_file"; then
                deleted_count=$((deleted_count + 1))
            fi
        done < <(find "$INVOICE_ARCHIVE_DIR" -maxdepth 1 -type f \
            \( -name 'invoices-*.jsonl' -o -name 'invoices-*.csv' -o -name 'invoices-*.meta.json' \) \
            -mtime +"$INVOICE_KEEP_DAYS" -print 2>/dev/null)

        log_message "Invoice archive cleanup complete (retention: $INVOICE_KEEP_DAYS days, deleted files: $deleted_count)"
    fi

    return 0
}

# Function to create backup
create_backup() {
    log_message "Starting backup process..."
    
    # Create date-formatted directory name
    CURRENT_DATE=$(date +"%Y-%m-%d")
    BACKUP_NAME="Inventarsystem-$CURRENT_DATE"
    BACKUP_DIR="$BACKUP_BASE_DIR/$BACKUP_NAME"
    BACKUP_ARCHIVE="$BACKUP_BASE_DIR/$BACKUP_NAME.tar.gz"
    
    # Create backup directory if it doesn't exist
    if [ ! -d "$BACKUP_BASE_DIR" ]; then
        sudo mkdir -p "$BACKUP_BASE_DIR"
        sudo chmod 755 "$BACKUP_BASE_DIR"
    fi
    
    # Remove existing backup with same date if it exists
    if [ -d "$BACKUP_DIR" ]; then
        log_message "Removing existing backup directory at $BACKUP_DIR"
        sudo rm -rf "$BACKUP_DIR"
    fi
    
    if [ -f "$BACKUP_ARCHIVE" ]; then
        log_message "Removing existing backup archive at $BACKUP_ARCHIVE"
        sudo rm -f "$BACKUP_ARCHIVE"
    fi
    
    # Create a temporary directory for backup
    log_message "Creating backup at $BACKUP_DIR"
    sudo mkdir -p "$BACKUP_DIR"
    # Copy project files excluding the backups directory itself (and optionally the venv)
    if command -v rsync >/dev/null 2>&1; then
        sudo rsync -a \
            --exclude='backups' \
            --exclude='.venv' \
            "$PROJECT_DIR"/ "$BACKUP_DIR"/
    else
        # Fallback to cp while skipping the backups directory
        for entry in "$PROJECT_DIR"/*; do
            name=$(basename "$entry")
            [[ "$name" == "backups" || "$name" == ".venv" ]] && continue
            sudo cp -r "$entry" "$BACKUP_DIR/"
        done
    fi
    
    # Create database backup
    log_message "Running database backup..."
    # Create mongodb_backup directory with appropriate permissions first
    sudo mkdir -p "$BACKUP_DIR/mongodb_backup"
    sudo chmod 755 "$BACKUP_DIR/mongodb_backup"

    # Run database backup with our helper script
    log_message "Executing database backup script..."
    db_backup_ok=0
    use_host_db_backup=1
    if [ "$BACKUP_MODE" = "docker" ]; then
        use_host_db_backup=0
    elif [ "$BACKUP_MODE" = "auto" ] && [ "$DOCKER_AVAILABLE" -eq 1 ] && [ "$MONGO_URI" = "mongodb://localhost:27017/" ]; then
        use_host_db_backup=0
        log_message "Auto mode: preferring Docker DB backup"
    fi

    if [ "$use_host_db_backup" -eq 1 ]; then
        # Create Backup_db.log and ensure it's writable only when host mode is used
        touch "$PROJECT_DIR/logs/Backup_db.log" 2>/dev/null
        chmod 666 "$PROJECT_DIR/logs/Backup_db.log" 2>/dev/null || {
            log_message "WARNING: Failed to set permissions on Backup_db.log. Trying with sudo..."
            sudo touch "$PROJECT_DIR/logs/Backup_db.log" 2>/dev/null
            sudo chmod 666 "$PROJECT_DIR/logs/Backup_db.log" 2>/dev/null || {
                log_message "WARNING: Failed to create writable Backup_db.log. Redirecting output to /dev/null instead."
                USE_NULL_OUTPUT=true
            }
        }

        # Install pymongo only for host backups
        log_message "Checking pymongo installation..."
        if ! python3 -c "import pymongo" &>/dev/null; then
            log_message "Installing pymongo..."
            if [ -f "$PROJECT_DIR/.venv/bin/pip" ]; then
                if [ "$USE_NULL_OUTPUT" = true ]; then
                    "$PROJECT_DIR/.venv/bin/pip" install pymongo==4.6.3 > /dev/null 2>&1 || true
                else
                    "$PROJECT_DIR/.venv/bin/pip" install pymongo==4.6.3 >> "$PROJECT_DIR/logs/Backup_db.log" 2>&1 || true
                fi
            fi
            if ! python3 -c "import pymongo" &>/dev/null; then
                if [ "$USE_NULL_OUTPUT" = true ]; then
                    pip3 install pymongo==4.6.3 > /dev/null 2>&1 || true
                else
                    pip3 install pymongo==4.6.3 >> "$PROJECT_DIR/logs/Backup_db.log" 2>&1 || true
                fi
            fi
        fi

        if [ "${USE_NULL_OUTPUT:-false}" = true ]; then
            sudo -E "$PROJECT_DIR/run-backup.sh" --db "$DB_NAME" --uri "$MONGO_URI" --out "$BACKUP_DIR/mongodb_backup" > /dev/null 2>&1 && db_backup_ok=1 || {
                log_message "ERROR: Failed to backup database with original path"
                
                # Try an alternative approach - use a temporary directory
                log_message "Attempting backup via temporary directory..."
                tmp_backup_dir="/tmp/mongodb_backup_$$"
                mkdir -p "$tmp_backup_dir"
                
                "$PROJECT_DIR/run-backup.sh" --db "$DB_NAME" --uri "$MONGO_URI" --out "$tmp_backup_dir" > /dev/null 2>&1 && {
                    # Copy temporary backup files to the actual backup directory
                    log_message "Copying backup files from temporary directory..."
                    cp -r "$tmp_backup_dir"/* "$BACKUP_DIR/mongodb_backup/"
                    db_backup_ok=1
                } || {
                    log_message "ERROR: All attempts to backup database failed"
                }
            }
        else
            sudo -E "$PROJECT_DIR/run-backup.sh" --db "$DB_NAME" --uri "$MONGO_URI" --out "$BACKUP_DIR/mongodb_backup" >> "$PROJECT_DIR/logs/Backup_db.log" 2>&1 && db_backup_ok=1 || {
                log_message "ERROR: Failed to backup database with original path"
                
                # Try an alternative approach - use a temporary directory
                log_message "Attempting backup via temporary directory..."
                tmp_backup_dir="/tmp/mongodb_backup_$$"
                mkdir -p "$tmp_backup_dir"
                
                "$PROJECT_DIR/run-backup.sh" --db "$DB_NAME" --uri "$MONGO_URI" --out "$tmp_backup_dir" >> "$PROJECT_DIR/logs/Backup_db.log" 2>&1 && {
                    # Copy temporary backup files to the actual backup directory
                    log_message "Copying backup files from temporary directory..."
                    cp -r "$tmp_backup_dir"/* "$BACKUP_DIR/mongodb_backup/"
                    db_backup_ok=1
                } || {
                    log_message "ERROR: All attempts to backup database failed"
                }
            }
        fi
    else
        log_message "Docker mode selected: skipping host DB backup step"
    fi

    # Auto-fallback for docker-first environments
    if [ "$db_backup_ok" -ne 1 ] && [ "$BACKUP_MODE" != "host" ]; then
        if try_backup_db_docker "$BACKUP_DIR/mongodb_backup"; then
            db_backup_ok=1
        fi
    fi
    
    # Check if any CSV files were created during backup
    if ! find "$BACKUP_DIR/mongodb_backup" -name "*.csv" -quit; then
        log_message "WARNING: No CSV files found in backup directory"
        
        # If we used a temporary directory earlier and it still exists, try to use its contents
        if [ -d "$tmp_backup_dir" ]; then
            log_message "Backup created in temporary directory, moving to backup location..."
            sudo cp -r "$tmp_backup_dir"/* "$BACKUP_DIR/mongodb_backup/" 
            rm -rf "$tmp_backup_dir"
        fi
    fi
    
    # Reset to more restrictive permissions after backup completes
    sudo chmod -R 755 "$BACKUP_DIR/mongodb_backup"
    
    # Verify that backup files were created
    csv_count=$(find "$BACKUP_DIR/mongodb_backup" -name "*.csv" 2>/dev/null | wc -l)
    archive_count=$(find "$BACKUP_DIR/mongodb_backup" -name "*.archive.gz" 2>/dev/null | wc -l)
    if [ "$csv_count" -gt 0 ] || [ "$archive_count" -gt 0 ]; then
        log_message "Database backup successful: ${csv_count} CSV collection(s), ${archive_count} archive file(s)"
    else
        log_message "WARNING: No database backup files found in backup directory"
    fi

    # Export legal invoice archive separately with long retention
    backup_invoices_archive || log_message "WARNING: Invoice archive export failed"
    
    # Compress the backup
    if [ "$COMPRESSION_LEVEL" -gt 0 ]; then
        log_message "Compressing backup with level $COMPRESSION_LEVEL..."
        
        # Create compressed archive with pigz when available, otherwise gzip.
        if command -v pigz >/dev/null 2>&1; then
            gzip_cmd="pigz -${COMPRESSION_LEVEL}"
        else
            gzip_cmd="gzip -${COMPRESSION_LEVEL}"
        fi
        if tar --help 2>/dev/null | grep -q -- "--use-compress-program"; then
            sudo tar -cf "$BACKUP_ARCHIVE" -I "$gzip_cmd" -C "$BACKUP_BASE_DIR" "$BACKUP_NAME" || {
                log_message "ERROR: Failed to compress backup (tar -I)"
                return 1
            }
        else
            GZIP="-${COMPRESSION_LEVEL}" sudo -E tar -czf "$BACKUP_ARCHIVE" -C "$BACKUP_BASE_DIR" "$BACKUP_NAME" || {
                log_message "ERROR: Failed to compress backup (tar + GZIP env)"
                return 1
            }
    fi
        
        # Remove uncompressed directory after successful compression
        if [ -f "$BACKUP_ARCHIVE" ]; then
            log_message "Backup compressed successfully to $BACKUP_ARCHIVE"
            log_message "Removing uncompressed backup directory"
            sudo rm -rf "$BACKUP_DIR"
        else
            log_message "ERROR: Compressed backup file not found"
            return 1
        fi
    else
        log_message "Compression disabled, keeping uncompressed backup"
    fi
    
    # Set appropriate permissions
    if [ "$COMPRESSION_LEVEL" -gt 0 ]; then
        sudo chmod 644 "$BACKUP_ARCHIVE"
    else
        sudo chmod -R 755 "$BACKUP_DIR"
    fi
    
    # Clean up old backups: age-based filter plus minimum keep safeguard
    log_message "Cleaning up old backups (keep at least $MIN_KEEP; days>$KEEP_DAYS)..."
    # Build list of all backup artifacts (files and directories) sorted newest first
    mapfile -t ALL_BACKUPS < <(find "$BACKUP_BASE_DIR" -maxdepth 1 \
        \( -type f -name "Inventarsystem-*.tar.gz" -o -type d -name "Inventarsystem-*" \) \
        -printf '%T@\t%p\n' 2>/dev/null | sort -nr | awk -F '\t' '{print $2}')
    TOTAL=${#ALL_BACKUPS[@]}
    if (( TOTAL > MIN_KEEP )); then
        # Determine deletion candidates by age (if KEEP_DAYS>0), otherwise all except the newest MIN_KEEP
        if (( KEEP_DAYS > 0 )); then
            mapfile -t AGE_CANDIDATES < <(find "$BACKUP_BASE_DIR" -maxdepth 1 \
                \( -type f -name "Inventarsystem-*.tar.gz" -o -type d -name "Inventarsystem-*" \) \
                -mtime +"$KEEP_DAYS" -printf '%T@\t%p\n' 2>/dev/null | sort -n | awk -F '\t' '{print $2}')
        else
            AGE_CANDIDATES=()
            # If no age filter, consider everything except the newest MIN_KEEP as candidates (oldest first)
            if (( TOTAL > MIN_KEEP )); then
                # Reverse ALL_BACKUPS to get oldest first
                for ((i=TOTAL-1; i>=MIN_KEEP; i--)); do AGE_CANDIDATES+=("${ALL_BACKUPS[$i]}"); done
            fi
        fi

        # Protect the newest MIN_KEEP backups overall
        ALLOWED_DELETE=$(( TOTAL - MIN_KEEP ))
        DELETED=0
        for path in "${AGE_CANDIDATES[@]:-}"; do
            (( DELETED >= ALLOWED_DELETE )) && break
            if [ -z "$path" ]; then continue; fi
            if [ -f "$path" ]; then
                sudo rm -f "$path" && ((DELETED++))
            elif [ -d "$path" ]; then
                sudo rm -rf "$path" && ((DELETED++))
            fi
        done
        log_message "Deleted $DELETED old backup(s); kept $(( TOTAL - DELETED ))"
    else
        log_message "No cleanup needed (total backups: $TOTAL <= min-keep: $MIN_KEEP)"
    fi
    
    log_message "Backup completed successfully"
    return 0
}

# Main
log_message "Backup destination: $BACKUP_BASE_DIR"
log_message "Database: $DB_NAME | URI: $MONGO_URI | Keep days: $KEEP_DAYS | Min keep: $MIN_KEEP | Compression: ${COMPRESSION_LEVEL}"
log_message "Invoice archive: $INVOICE_ARCHIVE_DIR | Invoice retention days: $INVOICE_KEEP_DAYS"
log_message "Backup mode: $BACKUP_MODE"

if [[ "$BACKUP_MODE" != "auto" && "$BACKUP_MODE" != "host" && "$BACKUP_MODE" != "docker" ]]; then
    log_message "ERROR: Invalid --mode value '$BACKUP_MODE' (allowed: auto, host, docker)"
    exit 2
fi

init_docker_compose || true

if create_backup; then
    ART_DATE="$(date +"%Y-%m-%d")"
    if [[ "$COMPRESSION_LEVEL" -gt 0 ]]; then
        echo "$BACKUP_BASE_DIR/Inventarsystem-$ART_DATE.tar.gz"
    else
        echo "$BACKUP_BASE_DIR/Inventarsystem-$ART_DATE"
    fi
fi