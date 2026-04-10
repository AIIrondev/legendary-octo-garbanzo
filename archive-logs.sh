#!/usr/bin/env bash
set -euo pipefail

# Monthly log archival script for Inventarsystem
# Runs on first day of month during automatic update
# Compresses logs to tar.gz, stores for up to 1 year, removes uncompressed originals

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$PROJECT_DIR/logs"
ARCHIVE_BASE_DIR="$PROJECT_DIR/backups/logs_archive"
LOG_ARCHIVE_FILE="$LOG_DIR/archive-logs.log"
GUARD_FILE="$PROJECT_DIR/.last-log-archive"
COMPRESSION_LEVEL="${COMPRESSION_LEVEL:-9}"

# Ensure archive base directory exists
mkdir -p "$ARCHIVE_BASE_DIR"
chmod 755 "$ARCHIVE_BASE_DIR" 2>/dev/null || true

log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_ARCHIVE_FILE"
}

should_archive_logs() {
    local today month_day guard_date
    
    today="$(date +%Y-%m-%d)"
    month_day="$(date +%d)"
    
    # Only run on first day of month
    if [ "$month_day" != "01" ]; then
        return 1
    fi
    
    # Check if we already ran today
    if [ -f "$GUARD_FILE" ]; then
        guard_date="$(cat "$GUARD_FILE" 2>/dev/null || echo '')"
        if [ "$guard_date" = "$today" ]; then
            log_message "Log archive already executed today ($today). Skipping."
            return 1
        fi
    fi
    
    return 0
}

archive_application_logs() {
    local archive_name archive_path retention_days cleanup_count deleted_count
    
    if [ ! -d "$LOG_DIR" ] || [ -z "$(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' 2>/dev/null)" ]; then
        log_message "No log files found in $LOG_DIR. Nothing to archive."
        return 0
    fi
    
    archive_name="inventar_logs_$(date +%Y-%m-01_%H%M%S)"
    archive_path="$ARCHIVE_BASE_DIR/${archive_name}.tar.gz"
    
    log_message "Starting monthly log archival..."
    log_message "Archive destination: $archive_path"
    
    # Create temporary directory for prepping files
    local tmp_prep_dir
    tmp_prep_dir="$(mktemp -d)"
    trap 'rm -rf "${tmp_prep_dir:-}"' RETURN
    
    # Copy log files to temp directory (excluding archive log itself during copy)
    if ! find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' ! -name 'archive-logs.log' -exec cp {} "$tmp_prep_dir/" \; 2>/dev/null; then
        log_message "WARNING: Could not copy all log files to temp directory"
    fi
    
    # Create tar.gz archive
    if tar -czf "$archive_path" -C "$tmp_prep_dir" . 2>/dev/null; then
        log_message "Log archive created successfully: $archive_path"
        log_message "Archive size: $(du -h "$archive_path" | cut -f1)"
    else
        log_message "ERROR: Failed to create log archive"
        return 1
    fi
    
    # Remove uncompressed log files (keep archive-logs.log for continuity)
    log_message "Removing uncompressed log files..."
    local files_removed=0
    while IFS= read -r log_file; do
        if [ "$log_file" != "$LOG_ARCHIVE_FILE" ]; then
            rm -f "$log_file" && ((++files_removed)) || true
        fi
    done < <(find "$LOG_DIR" -maxdepth 1 -type f -name '*.log')
    log_message "Removed $files_removed uncompressed log file(s)"
    
    trap - RETURN
}

cleanup_old_archives() {
    local retention_days cleanup_count deleted_count total_archives
    
    retention_days="365"
    
    # Find and remove archives older than 1 year
    log_message "Cleaning up archives older than $retention_days days..."
    
    total_archives="$(find "$ARCHIVE_BASE_DIR" -maxdepth 1 -type f -name '*.tar.gz' 2>/dev/null | wc -l)"
    deleted_count="0"
    
    find "$ARCHIVE_BASE_DIR" -maxdepth 1 -type f -name '*.tar.gz' -mtime +$retention_days | while read -r old_archive; do
        log_message "Removing old archive: $old_archive"
        rm -f "$old_archive"
        ((++deleted_count)) || true
    done 2>/dev/null || true
    
    # Count deleted (safer approach)
    local current_archives
    current_archives="$(find "$ARCHIVE_BASE_DIR" -maxdepth 1 -type f -name '*.tar.gz' 2>/dev/null | wc -l)"
    deleted_count="$((total_archives - current_archives))"
    
    if [ "$deleted_count" -gt 0 ]; then
        log_message "Deleted $deleted_count old archive(s); kept $current_archives"
    else
        log_message "No old archives to delete (total: $total_archives)"
    fi
}

main() {
    if ! should_archive_logs; then
        return 0
    fi
    
    log_message "=== Monthly log archival started ==="
    
    archive_application_logs || {
        log_message "ERROR: Log archival failed"
        return 1
    }
    
    cleanup_old_archives || {
        log_message "WARNING: Archive cleanup encountered issues"
    }
    
    # Update guard file with today's date
    date +%Y-%m-%d > "$GUARD_FILE"
    
    log_message "=== Monthly log archival completed successfully ==="
    return 0
}

main "$@"
