#!/bin/bash

# Nur die App neu bauen und starten, ohne den Tunnel oder die DB zu killen
docker compose up -d --build app

# Optional: Alles aufräumen, was nicht mehr gebraucht wird
docker image prune -f

set -euo pipefail

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

"$SCRIPT_DIR/stop.sh" "$@"
"$SCRIPT_DIR/start.sh" "$@"