#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SUDO=""
if [ "$(id -u)" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
fi

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Error: .venv python not found at $VENV_PYTHON"
    echo "Create it first, e.g.: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

if [ "$(id -u)" -ne 0 ] && [ ! -w "$SCRIPT_DIR/.venv" ]; then
    echo "Fixing ownership of .venv for current user..."
    if [ -n "$SUDO" ]; then
        $SUDO chown -R "$(id -un):$(id -gn)" "$SCRIPT_DIR/.venv"
    else
        echo "Error: .venv is not writable and sudo is unavailable."
        exit 1
    fi
fi

for path in "$SCRIPT_DIR/dist" "$SCRIPT_DIR/build"; do
    if [ -e "$path" ] && [ "$(id -u)" -ne 0 ]; then
        echo "Ensuring ownership of $(basename "$path") for current user..."
        if [ -n "$SUDO" ]; then
            $SUDO chown -R "$(id -un):$(id -gn)" "$path"
        else
            if [ ! -w "$path" ]; then
                echo "Error: $path is not writable and sudo is unavailable."
                exit 1
            fi
        fi
    fi
done

echo "Installing Nuitka build dependencies in .venv..."
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
"$VENV_PYTHON" -m pip install --upgrade "nuitka==2.8.10" ordered-set zstandard

DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
OUTPUT_NAME="inventarsystem"

mkdir -p "$DIST_DIR" "$BUILD_DIR"

NUITKA_DATA_ARGS=()

if [ -d "$SCRIPT_DIR/Web/templates" ]; then
    NUITKA_DATA_ARGS+=("--include-data-dir=$SCRIPT_DIR/Web/templates=templates")
fi

if [ -d "$SCRIPT_DIR/Web/static" ]; then
    NUITKA_DATA_ARGS+=("--include-data-dir=$SCRIPT_DIR/Web/static=static")
fi

if [ -d "$SCRIPT_DIR/uploads" ]; then
    NUITKA_DATA_ARGS+=("--include-data-dir=$SCRIPT_DIR/uploads=uploads")
fi

ORIGINAL_PERF_PARANOID=""
if [ -r /proc/sys/kernel/perf_event_paranoid ]; then
    ORIGINAL_PERF_PARANOID="$(cat /proc/sys/kernel/perf_event_paranoid)"
    if [ "$ORIGINAL_PERF_PARANOID" -gt 1 ]; then
        echo "Temporarily setting kernel.perf_event_paranoid=1 for Nuitka build compatibility..."
        if ! $SUDO sh -c 'echo 1 > /proc/sys/kernel/perf_event_paranoid'; then
            echo "Warning: Could not adjust kernel.perf_event_paranoid automatically."
            echo "Run: sudo sh -c 'echo 1 > /proc/sys/kernel/perf_event_paranoid' and retry."
            exit 1
        fi
    fi
fi

restore_perf_setting() {
    if [ -n "$ORIGINAL_PERF_PARANOID" ] && [ "$ORIGINAL_PERF_PARANOID" -gt 1 ]; then
        $SUDO sh -c "echo $ORIGINAL_PERF_PARANOID > /proc/sys/kernel/perf_event_paranoid" >/dev/null 2>&1 || true
    fi
}

trap restore_perf_setting EXIT

echo "Building standalone binary with Nuitka..."
"$VENV_PYTHON" -m nuitka \
    --standalone \
    --assume-yes-for-downloads \
    --follow-imports \
    --output-dir="$DIST_DIR" \
    --output-filename="$OUTPUT_NAME" \
    "${NUITKA_DATA_ARGS[@]}" \
    --remove-output \
    "$SCRIPT_DIR/Web/app.py"

APP_DIST_DIR="$DIST_DIR/app.dist"
if [ -d "$APP_DIST_DIR" ]; then
    echo "Nuitka build complete."
    echo "Run with: $APP_DIST_DIR/$OUTPUT_NAME"
else
    echo "Build finished, but expected output directory not found: $APP_DIST_DIR"
    echo "Check Nuitka output above."
    exit 1
fi
