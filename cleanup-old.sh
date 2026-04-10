#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
ADMIN_PROJECT_DIR="${ADMIN_PROJECT_DIR:-$(dirname "$PROJECT_DIR")/admin_Inventarsystem}"

DRY_RUN=0
REMOVE_CRON=0
KEEP_AUTOSTART=0

SERVICES=(
    "inventarsystem-gunicorn.service"
    "admin-inventarsystem-gunicorn.service"
    "admin-inventarsystem-nginx.service"
)

SOCKETS=(
    "/tmp/inventarsystem.sock"
    "/tmp/admin-inventarsystem.sock"
)

PROCESS_PATTERNS=(
    "$PROJECT_DIR/.venv/bin/gunicorn app:app"
    "$ADMIN_PROJECT_DIR/.venv/bin/gunicorn app:app"
)

CRON_FILTER_PATTERNS=(
    "$PROJECT_DIR/update.sh"
    "$PROJECT_DIR/backup-docker.sh"
    "$ADMIN_PROJECT_DIR/update.sh"
    "$ADMIN_PROJECT_DIR/backup-docker.sh"
)

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --remove-cron       Remove matching cron entries for old systems
  --keep-autostart    Stop services but do not disable autostart
  --dry-run           Show actions without executing
  -h, --help          Show this help message
EOF
}

log() {
    echo "[cleanup-old] $*"
}

run_cmd() {
    if [ "$DRY_RUN" -eq 1 ]; then
        echo "[dry-run] $*"
    else
        "$@"
    fi
}

run_cmd_sudo() {
    if [ "$(id -u)" -eq 0 ]; then
        run_cmd "$@"
    else
        run_cmd sudo "$@"
    fi
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --remove-cron)
                REMOVE_CRON=1
                shift
                ;;
            --keep-autostart)
                KEEP_AUTOSTART=1
                shift
                ;;
            --dry-run)
                DRY_RUN=1
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

service_exists() {
    local service="$1"
    systemctl list-unit-files --type=service --no-legend --no-pager 2>/dev/null | awk '{print $1}' | grep -Fxq "$service"
}

stop_services() {
    if ! command -v systemctl >/dev/null 2>&1; then
        log "systemctl not available, skipping service cleanup"
        return 0
    fi

    local service
    for service in "${SERVICES[@]}"; do
        if ! service_exists "$service"; then
            log "Service not found: $service"
            continue
        fi

        log "Stopping $service"
        run_cmd_sudo systemctl stop "$service" || true

        if [ "$KEEP_AUTOSTART" -eq 0 ]; then
            log "Disabling autostart for $service"
            run_cmd_sudo systemctl disable "$service" || true
        fi
    done
}

kill_leftover_processes() {
    local pattern
    for pattern in "${PROCESS_PATTERNS[@]}"; do
        log "Terminating processes matching: $pattern"
        run_cmd_sudo pkill -TERM -f "$pattern" || true
    done

    if [ "$DRY_RUN" -eq 0 ]; then
        sleep 2
    fi

    for pattern in "${PROCESS_PATTERNS[@]}"; do
        run_cmd_sudo pkill -KILL -f "$pattern" || true
    done
}

remove_stale_sockets() {
    local socket_path
    for socket_path in "${SOCKETS[@]}"; do
        if [ -e "$socket_path" ]; then
            log "Removing stale socket/file: $socket_path"
            run_cmd_sudo rm -f "$socket_path"
        else
            log "Socket/file not present: $socket_path"
        fi
    done
}

remove_cron_entries() {
    if ! command -v crontab >/dev/null 2>&1; then
        log "crontab not available, skipping cron cleanup"
        return 0
    fi

    local tmp_file
    tmp_file="$(mktemp)"

    if [ "$(id -u)" -eq 0 ]; then
        (crontab -l 2>/dev/null || true) > "$tmp_file"
    else
        (sudo crontab -l 2>/dev/null || true) > "$tmp_file"
    fi

    local pattern
    for pattern in "${CRON_FILTER_PATTERNS[@]}"; do
        if [ "$DRY_RUN" -eq 1 ]; then
            echo "[dry-run] would remove cron lines containing: $pattern"
        else
            grep -vF "$pattern" "$tmp_file" > "${tmp_file}.new" || true
            mv "${tmp_file}.new" "$tmp_file"
        fi
    done

    if [ "$DRY_RUN" -eq 0 ]; then
        if [ "$(id -u)" -eq 0 ]; then
            crontab "$tmp_file"
        else
            sudo crontab "$tmp_file"
        fi
    fi

    rm -f "$tmp_file"
    log "Cron cleanup finished"
}

status_report() {
    log "Remaining matching processes:"
    ps -eo pid,ppid,cmd --sort=start_time | grep -E "Inventarsystem/.venv/bin/gunicorn|admin_Inventarsystem/.venv/bin/gunicorn" | grep -v grep || echo "none"

    log "Socket status:"
    local socket_path
    for socket_path in "${SOCKETS[@]}"; do
        if [ -e "$socket_path" ]; then
            echo "exists: $socket_path"
        else
            echo "missing: $socket_path"
        fi
    done
}

main() {
    parse_args "$@"

    stop_services
    kill_leftover_processes
    remove_stale_sockets

    if [ "$REMOVE_CRON" -eq 1 ]; then
        remove_cron_entries
    fi

    status_report
    log "Cleanup complete"
}

main "$@"
