#!/bin/bash

# Standalone version manager for this repo
# Supports pinning to a commit/tag/branch, one-time use, clearing the lock,
# applying the lock, listing refs, and showing status. Optional restart.

set -euo pipefail

PROJECT_DIR="$(dirname "$(readlink -f "$0")")"
cd "$PROJECT_DIR"

LOCK_FILE="$PROJECT_DIR/.version-lock"
RESTART=false
FORCE=false
BACKUP_BASE_DIR="/var/backups"
LOG_DIR="$PROJECT_DIR/logs"
VM_LOG="$LOG_DIR/version_manager.log"

# Directories/files to preserve across version switches
# Data paths we want to restore from backup after a version switch
DATA_PATHS=(
  "certs"
  "Images"
  "logs"
  "Web/uploads"
  "Web/thumbnails"
  "Web/QRCodes"
  "Web/previews"
)

# Ensure log directory exists
mkdir -p "$LOG_DIR" >/dev/null 2>&1 || true
chmod 777 "$LOG_DIR" >/dev/null 2>&1 || true

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$VM_LOG"; }
err() { echo "ERROR: $*" | tee -a "$VM_LOG" >&2; }

usage() {
  cat <<USAGE
Usage:
  $0 pin <ref> [--restart] [--force]     Persistently lock to a commit/tag/branch and deploy it
  $0 use <ref> [--restart] [--force]     Use ref once (no persistence) and deploy it
  $0 clear [--restart] [--force]         Remove lock, switch back to main, pull latest
  $0 apply [--restart] [--force]         Re-apply the current lock (if any)
  $0 status                               Show current commit and lock state
  $0 list [--tags|--commits]              List tags or recent commits (default: tags)

Notes:
  - <ref> can be a tag name, branch name, or full/short commit hash
  - --restart calls ./restart.sh after switching
  - --force discards local changes (git reset --hard) if needed
USAGE
}

ensure_git_ready() {
  # Avoid "dubious ownership" errors
  git config --global --add safe.directory "$PROJECT_DIR" >/dev/null 2>&1 || true
  # Fetch refs and tags
  git fetch --all --tags --prune
}

ensure_clean_or_force() {
  if ! git diff --quiet || ! git diff --cached --quiet; then
    if [ "$FORCE" = true ]; then
      log "Discarding local changes (force)"
      git reset --hard
      git clean -fdx >/dev/null 2>&1 || true
    else
      err "Working tree has local changes. Re-run with --force to discard."
      exit 2
    fi
  fi
}

restart_if_requested() {
  if [ "$RESTART" = true ]; then
    if [ -x "$PROJECT_DIR/restart.sh" ]; then
      log "Restarting services..."
      "$PROJECT_DIR/restart.sh"
    else
      log "restart.sh not found or not executable; skipping restart"
    fi
  fi
}

# Create a full backup before switching versions (files + DB CSVs)
LAST_BACKUP_ARCHIVE=""
LAST_BACKUP_DIRNAME=""
create_pre_switch_backup() {
  local ts backup_name backup_dir backup_archive
  ts=$(date +"%Y-%m-%d_%H-%M-%S")
  backup_name="Inventarsystem-pre-switch-$ts"
  backup_dir="$BACKUP_BASE_DIR/$backup_name"
  backup_archive="$BACKUP_BASE_DIR/$backup_name.tar.gz"

  log "Creating pre-switch backup at $backup_archive"
  sudo mkdir -p "$backup_dir" || { err "Failed to create backup directory"; return 1; }

  # Copy project files (exclude .venv to reduce size, keep .git for reference)
  log "Copying project files to backup directory..."
  sudo rsync -a --delete \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$PROJECT_DIR/" "$backup_dir/" || log "Warning: rsync file copy encountered issues"

  # Database CSV backup using existing helper
  log "Backing up MongoDB to CSVs..."
  sudo mkdir -p "$backup_dir/mongodb_backup" || true
  if [ -x "$PROJECT_DIR/run-backup.sh" ]; then
    if sudo -E "$PROJECT_DIR/run-backup.sh" --db Inventarsystem --uri mongodb://localhost:27017/ --out "$backup_dir/mongodb_backup" >> "$VM_LOG" 2>&1; then
      log "Database backup completed"
    else
      err "Database backup failed; continuing with file backup only"
    fi
  else
    log "run-backup.sh not found; skipping DB backup"
  fi

  # Compress backup
  log "Compressing backup archive..."
  if sudo tar -czf "$backup_archive" -C "$BACKUP_BASE_DIR" "$backup_name"; then
    log "Backup archived to $backup_archive"
    sudo rm -rf "$backup_dir" || true
    # Set readable permissions
    sudo chmod 644 "$backup_archive" || true
    # Export for subsequent restore step
    LAST_BACKUP_ARCHIVE="$backup_archive"
    LAST_BACKUP_DIRNAME="$backup_name"
  else
    err "Failed to create compressed backup archive"
    return 1
  fi
}

# Restore key data from the backup archive into current working tree
restore_from_backup_archive() {
  if [ -z "$LAST_BACKUP_ARCHIVE" ] || [ ! -f "$LAST_BACKUP_ARCHIVE" ]; then
    log "No backup archive available to restore data from; skipping data restore"
    return 0
  fi
  local tmpdir
  tmpdir=$(mktemp -d /tmp/inventarsystem_restore_XXXXXX)
  log "Extracting backup archive $LAST_BACKUP_ARCHIVE to $tmpdir"
  if ! sudo tar -xzf "$LAST_BACKUP_ARCHIVE" -C "$tmpdir"; then
    err "Failed to extract backup archive; skipping data restore"
    rm -rf "$tmpdir" || true
    return 1
  fi
  local src_root="$tmpdir/$LAST_BACKUP_DIRNAME"
  # Some backups might extract without top-level dir; fallback
  if [ ! -d "$src_root" ]; then
    src_root="$tmpdir"
  fi
  log "Restoring data directories from backup..."
  for rel in "${DATA_PATHS[@]}"; do
    if [ -e "$src_root/$rel" ]; then
      mkdir -p "$PROJECT_DIR/$(dirname "$rel")" 2>/dev/null || true
      rsync -a "$src_root/$rel" "$PROJECT_DIR/$(dirname "$rel")/" >> "$VM_LOG" 2>&1 || log "Warning: failed to restore $rel"
      log "Restored: $rel"
    else
      log "Not in backup (skipped): $rel"
    fi
  done
  rm -rf "$tmpdir" || true
}

# Ensure permissions on critical data directories
ensure_permissions() {
  # Logs should be writable
  mkdir -p "$PROJECT_DIR/logs" && chmod 777 "$PROJECT_DIR/logs" 2>/dev/null || true
  # Web data directories readable/executable by server
  for d in "$PROJECT_DIR/Web/uploads" "$PROJECT_DIR/Web/thumbnails" "$PROJECT_DIR/Web/QRCodes" "$PROJECT_DIR/Web/previews" "$PROJECT_DIR/Images"; do
    [ -d "$d" ] && chmod -R 755 "$d" 2>/dev/null || true
  done
  # SSL cert perms (key must be 600)
  if [ -f "$PROJECT_DIR/certs/inventarsystem.key" ]; then
    chmod 600 "$PROJECT_DIR/certs/inventarsystem.key" 2>/dev/null || true
  fi
}

checkout_ref() {
  local ref="$1"

  # Try tag
  if git show-ref --verify --quiet "refs/tags/$ref"; then
    git checkout -B locked-tag-"$ref" "tags/$ref"
    return 0
  fi
  # Try remote branch
  if git show-ref --verify --quiet "refs/remotes/origin/$ref"; then
    git checkout -B locked-branch-"$ref" "origin/$ref"
    return 0
  fi
  # Try local branch
  if git show-ref --verify --quiet "refs/heads/$ref"; then
    git checkout "$ref"
    return 0
  fi
  # Try commit-ish
  if git rev-parse --verify --quiet "$ref^{commit}" >/dev/null; then
    git checkout -B locked-commit "$ref"
    return 0
  fi

  err "Could not resolve ref '$ref' to tag/branch/commit"
  exit 3
}

deploy_main_latest() {
  ensure_clean_or_force
  if git show-ref --verify --quiet refs/heads/main; then
    git checkout main
  else
    git checkout -B main origin/main
  fi
  git pull --ff-only
}

cmd_status() {
  local head_commit
  head_commit=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
  echo "Current commit: $head_commit"
  if [ -f "$LOCK_FILE" ]; then
    echo "Version lock: $(cat "$LOCK_FILE")"
  else
    echo "Version lock: none (tracking main)"
  fi
}

cmd_list() {
  local mode="tags"
  for a in "$@"; do
    case "$a" in
      --tags) mode="tags" ;;
      --commits) mode="commits" ;;
    esac
  done
  ensure_git_ready
  if [ "$mode" = "tags" ]; then
    git tag --list | sort -V
  else
    git --no-pager log --oneline -n 30
  fi
}

cmd_pin() {
  local ref="$1"
  ensure_git_ready
  # Always produce a backup before switching
  create_pre_switch_backup || log "Backup step had issues; proceeding with caution"
  ensure_clean_or_force
  echo "$ref" > "$LOCK_FILE"
  checkout_ref "$ref"
  # Restore data from the backup archive
  restore_from_backup_archive
  ensure_permissions
  log "Pinned to: $ref (commit $(git rev-parse --short HEAD))"
  restart_if_requested
}

cmd_use() {
  local ref="$1"
  ensure_git_ready
  create_pre_switch_backup || log "Backup step had issues; proceeding with caution"
  ensure_clean_or_force
  checkout_ref "$ref"
  restore_from_backup_archive
  ensure_permissions
  log "Using (one-time): $ref (commit $(git rev-parse --short HEAD))"
  restart_if_requested
}

cmd_clear() {
  ensure_git_ready
  create_pre_switch_backup || log "Backup step had issues; proceeding with caution"
  [ -f "$LOCK_FILE" ] && rm -f "$LOCK_FILE"
  deploy_main_latest
  restore_from_backup_archive
  ensure_permissions
  log "Cleared version lock; now on main @ $(git rev-parse --short HEAD)"
  restart_if_requested
}

cmd_apply() {
  ensure_git_ready
  create_pre_switch_backup || log "Backup step had issues; proceeding with caution"
  if [ -f "$LOCK_FILE" ]; then
    ensure_clean_or_force
    local ref
    ref=$(cat "$LOCK_FILE")
    checkout_ref "$ref"
    log "Applied lock: $ref (commit $(git rev-parse --short HEAD))"
  else
    log "No lock present; keeping main"
    deploy_main_latest
  fi
  restore_from_backup_archive
  ensure_permissions
  restart_if_requested
}

# Parse global flags that can appear after subcommand too
parse_tail_flags() {
  for a in "$@"; do
    case "$a" in
      --restart) RESTART=true ;;
      --force)   FORCE=true ;;
    esac
  done
}

main() {
  local cmd="${1:-}"; shift || true
  case "$cmd" in
    pin)
      [ $# -ge 1 ] || { usage; exit 1; }
      local ref="$1"; shift; parse_tail_flags "$@"; cmd_pin "$ref" ;;
    use)
      [ $# -ge 1 ] || { usage; exit 1; }
      local ref="$1"; shift; parse_tail_flags "$@"; cmd_use "$ref" ;;
    clear)
      parse_tail_flags "$@"; cmd_clear ;;
    apply)
      parse_tail_flags "$@"; cmd_apply ;;
    status)
      cmd_status ;;
    list)
      cmd_list "$@" ;;
    --help|-h|help|"")
      usage ;;
    *)
      err "Unknown command: $cmd"; usage; exit 1 ;;
  esac
}

main "$@"
