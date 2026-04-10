#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! command -v docker >/dev/null 2>&1; then
    echo "Error: docker command not found. Install Docker first."
    exit 1
fi

echo "Stopping Inventarsystem Docker stack..."
docker compose down

echo "Stack stopped."
