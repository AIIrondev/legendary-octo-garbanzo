#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="docker-compose-multitenant.yml"
INVOICE_ARCHIVE_DIR="${INVOICE_ARCHIVE_DIR:-/var/backups/invoice-archive}"
KEEP_DAYS="${INVOICE_KEEP_DAYS:-3650}"
MODE="auto"
BASE_NAME=""

usage() {
    cat <<EOF
Usage: $0 [options]

Options:
  --invoice-archive-dir DIR   Directory for invoice archive files
                              (default: $INVOICE_ARCHIVE_DIR)
  --invoice-keep-days N       Remove archived invoice files older than N days
                              (default: $KEEP_DAYS)
  --mode auto|docker|host     Backup mode (default: auto)
  --base-name NAME            Base filename prefix for archive files
  -h, --help                  Show this help message
EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --invoice-archive-dir)
                INVOICE_ARCHIVE_DIR="$2"
                shift 2
                ;;
            --invoice-keep-days)
                KEEP_DAYS="$2"
                shift 2
                ;;
            --mode)
                MODE="$2"
                shift 2
                ;;
            --base-name)
                BASE_NAME="$2"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                echo "Error: unknown option '$1'" >&2
                usage
                exit 2
                ;;
        esac
    done
}

ensure_directory() {
    mkdir -p "$INVOICE_ARCHIVE_DIR"
}

cleanup_old_archives() {
    if [[ -n "$KEEP_DAYS" ]]; then
        find "$INVOICE_ARCHIVE_DIR" -maxdepth 1 -type f \( -name 'invoices-*.jsonl' -o -name 'invoices-*.csv' -o -name 'invoices-*.meta.json' \) -mtime +"$KEEP_DAYS" -print -delete || true
    fi
}

host_backup() {
    if ! command -v python3 >/dev/null 2>&1; then
        return 1
    fi
    if ! python3 -c 'import pymongo' >/dev/null 2>&1; then
        return 1
    fi

    python3 "$SCRIPT_DIR/Web/backup_invoices.py" \
        --archive-dir "$INVOICE_ARCHIVE_DIR" \
        --base-name "$BASE_NAME"
}

docker_backup() {
    if ! command -v docker >/dev/null 2>&1; then
        return 1
    fi
    if ! docker compose -f "$COMPOSE_FILE" ps -q app >/dev/null 2>&1; then
        return 1
    fi

    local app_container
    app_container="$(docker compose -f "$COMPOSE_FILE" ps -q app | tr -d '[:space:]')"
    if [[ -z "$app_container" ]]; then
        return 1
    fi

    local timestamp
    timestamp="$(date +'%Y-%m-%d_%H-%M-%S')"
    local output_dir
    local remote_base

    output_dir="/tmp/invoice_archive_${timestamp}"
    remote_base="${output_dir}/${BASE_NAME}"

    docker compose -f "$COMPOSE_FILE" exec -T app mkdir -p "$output_dir"
    docker compose -f "$COMPOSE_FILE" exec -T app python3 /app/Web/backup_invoices.py \
        --archive-dir "$output_dir" \
        --base-name "$BASE_NAME"

    mkdir -p "$INVOICE_ARCHIVE_DIR"
    docker cp "$app_container":"${remote_base}.jsonl" "$INVOICE_ARCHIVE_DIR/"
    docker cp "$app_container":"${remote_base}.csv" "$INVOICE_ARCHIVE_DIR/"
    docker cp "$app_container":"${remote_base}.meta.json" "$INVOICE_ARCHIVE_DIR/"

    docker compose -f "$COMPOSE_FILE" exec -T app rm -rf "$output_dir"
}

main() {
    if [[ -z "$BASE_NAME" ]]; then
        BASE_NAME="invoices-$(date +'%Y-%m-%d_%H-%M-%S')"
    fi

    ensure_directory

    case "$MODE" in
        auto)
            if docker_backup; then
                cleanup_old_archives
                return 0
            fi
            if host_backup; then
                cleanup_old_archives
                return 0
            fi
            echo "Error: could not perform invoice backup in auto mode. Docker or host Python with pymongo is required." >&2
            return 1
            ;;
        docker)
            if docker_backup; then
                cleanup_old_archives
                return 0
            fi
            echo "Error: docker backup failed or app container is unavailable." >&2
            return 1
            ;;
        host)
            if host_backup; then
                cleanup_old_archives
                return 0
            fi
            echo "Error: host backup failed. Ensure python3 and pymongo are installed." >&2
            return 1
            ;;
        *)
            echo "Error: unsupported mode '$MODE'" >&2
            usage
            return 2
            ;;
    esac
}

parse_args "$@"
main
