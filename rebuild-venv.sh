#!/bin/bash

# This script completely rebuilds the virtual environment
# It should be run as root/sudo

# Get the script directory
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_DIR="$SCRIPT_DIR/.venv"
BACKUP_DIR="$SCRIPT_DIR/.venv_backup_$(date +%Y%m%d%H%M%S)"

# Function to log messages
log_message() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

log_message "Starting virtual environment rebuild"

# Backup existing virtual environment if it exists
if [ -d "$VENV_DIR" ]; then
    log_message "Backing up existing virtual environment to $BACKUP_DIR"
    mv "$VENV_DIR" "$BACKUP_DIR" || {
        log_message "ERROR: Failed to backup existing virtual environment. Proceeding without backup."
        rm -rf "$VENV_DIR"
    }
fi

# Create logs directory with proper permissions
log_message "Ensuring logs directory exists with proper permissions"
mkdir -p "$SCRIPT_DIR/logs"
chmod 777 "$SCRIPT_DIR/logs" || log_message "WARNING: Could not set permissions on logs directory"

# Create a new virtual environment
log_message "Creating new virtual environment"
python3 -m venv "$VENV_DIR" || {
    log_message "ERROR: Failed to create virtual environment. Trying with system packages..."
    python3 -m venv "$VENV_DIR" --system-site-packages || {
        log_message "ERROR: Failed to create virtual environment even with system packages. Exiting."
        exit 1
    }
}

# Set proper permissions
log_message "Setting permissions for new virtual environment"
chmod -R 755 "$VENV_DIR" || log_message "WARNING: Could not set permissions on virtual environment"
find "$VENV_DIR" -type d -exec chmod 755 {} \; 2>/dev/null
find "$VENV_DIR/bin" -type f -exec chmod +x {} \; 2>/dev/null

# Activate the virtual environment
log_message "Activating virtual environment"
source "$VENV_DIR/bin/activate" || {
    log_message "ERROR: Failed to activate virtual environment"
    exit 1
}

# Install packages
log_message "Upgrading pip"
pip install --upgrade pip || log_message "WARNING: Failed to upgrade pip"

log_message "Installing pymongo"
# First ensure bson is removed to avoid conflicts
pip uninstall -y bson || log_message "WARNING: Failed to uninstall bson (may not exist)"
# Check if bson directory exists after uninstall and remove it if necessary
if [ -d "$VENV_DIR/lib/python3.12/site-packages/bson" ]; then
    log_message "Force removing bson directory"
    rm -rf "$VENV_DIR/lib/python3.12/site-packages/bson"
fi
# Now install pymongo
pip install pymongo==4.6.3 || log_message "WARNING: Failed to install pymongo"
# Verify pymongo installation
python -c "import pymongo; print(f'PyMongo version: {pymongo.__version__}')" && log_message "✓ PyMongo installed correctly" || log_message "WARNING: PyMongo verification failed"

# Install other requirements if they exist
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    log_message "Installing packages from requirements.txt (excluding bson)"
    # Create a modified requirements file without bson
    grep -v "^bson" "$SCRIPT_DIR/requirements.txt" > "$SCRIPT_DIR/requirements_filtered.txt"
    # Also remove pymongo since we already installed it
    grep -v "^pymongo" "$SCRIPT_DIR/requirements_filtered.txt" > "$SCRIPT_DIR/requirements_no_conflicts.txt"
    pip install -r "$SCRIPT_DIR/requirements_no_conflicts.txt" || log_message "WARNING: Failed to install some packages from requirements.txt"
    rm -f "$SCRIPT_DIR/requirements_filtered.txt" "$SCRIPT_DIR/requirements_no_conflicts.txt"
    
    log_message "Verifying pymongo installation after package installation..."
    # Check if the bson directory from the standalone package still exists and remove it
    if [ -d "$VENV_DIR/lib/python3.12/site-packages/bson" ]; then
        log_message "Found standalone bson package, removing it..."
        rm -rf "$VENV_DIR/lib/python3.12/site-packages/bson"
        # Reinstall pymongo to ensure it's correctly configured
        pip install --force-reinstall pymongo==4.6.3
    fi
else
    log_message "No requirements.txt found, installing essential packages manually"
    pip install flask werkzeug gunicorn pillow qrcode apscheduler python-dateutil pytz requests || {
        log_message "WARNING: Failed to install some essential packages"
    }
fi

# Deactivate virtual environment
deactivate

# Verify the virtual environment works correctly
log_message "Verifying virtual environment..."
if "$VENV_DIR/bin/python" -c "import pymongo, flask, gunicorn, requests, PIL, apscheduler; exit(0)" 2>/dev/null; then
    log_message "✓ Virtual environment verification successful"
    
    # Clean up backup if everything works
    if [ -d "$BACKUP_DIR" ]; then
        log_message "Removing backup virtual environment since verification was successful"
        rm -rf "$BACKUP_DIR"
        log_message "✓ Backup environment removed"
    fi
else
    log_message "WARNING: Virtual environment verification failed"
    log_message "Keeping backup at $BACKUP_DIR in case it's needed for recovery"
fi

log_message "Virtual environment rebuild complete"
log_message "You can now run the restart.sh script"

exit 0
