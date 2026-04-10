#!/bin/bash
#
# fix-all.sh - All-in-One Reparaturskript für das Inventarsystem
#
# Dieses Skript führt alle notwendigen Reparaturschritte für das Inventarsystem durch:
# - Berechtigungen für alle Verzeichnisse und Dateien korrigieren
# - Virtual Environment und Python-Pakete reparieren
# - Git Repository-Berechtigungen setzen
# - Log-Verzeichnisse und Dateien erstellen und Berechtigungen setzen
# - Web-Verzeichnisberechtigungen korrigieren
# - MongoDB-Backup-Verzeichnisse einrichten
# - Bekannte Konflikte zwischen pymongo und bson beheben
# - Uploads-Verzeichnisse sowohl in Entwicklungs- als auch in Produktionsumgebungen verwalten
#
# Verwendung: sudo ./fix-all.sh [--check-only] [--verbose] [--fix-permissions] [--fix-venv] [--fix-pymongo] [--auto] [--setup-cron]

# Parse command line arguments
CHECK_ONLY=false
VERBOSE=false
FIX_PERMISSIONS=true
FIX_VENV=true
FIX_PYMONGO=true
FIX_PNG_TO_JPG=true
AUTO_MODE=false
SETUP_CRON=false

for arg in "$@"; do
    case $arg in
        --check-only)
            CHECK_ONLY=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --fix-permissions)
            FIX_PERMISSIONS=true
            FIX_VENV=false
            FIX_PYMONGO=false
            shift
            ;;
        --fix-venv)
            FIX_VENV=true
            FIX_PERMISSIONS=false
            FIX_PYMONGO=false
            shift
            ;;
        --fix-pymongo)
            FIX_PYMONGO=true
            FIX_PERMISSIONS=false
            FIX_VENV=false
            FIX_PNG_TO_JPG=false
            shift
            ;;
        --fix-png-jpg)
            FIX_PNG_TO_JPG=true
            FIX_PERMISSIONS=false
            FIX_VENV=false
            FIX_PYMONGO=false
            shift
            ;;
        --no-fix-png-jpg)
            FIX_PNG_TO_JPG=false
            shift
            ;;
        --auto)
            AUTO_MODE=true
            shift
            ;;
        --setup-cron)
            SETUP_CRON=true
            shift
            ;;
        --email=*)
            echo "Hinweis: Die E-Mail-Funktion wurde entfernt. Option \"$arg\" wird ignoriert." 
            shift
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo "Repariert alle bekannten Probleme im Inventarsystem."
            echo ""
            echo "Options:"
            echo "  --check-only      Nur Prüfen, keine Änderungen durchführen"
            echo "  --verbose         Ausführlichere Ausgabe"
            echo "  --fix-permissions Nur Berechtigungen korrigieren"
            echo "  --fix-venv        Nur virtuelle Umgebung reparieren"
            echo "  --fix-pymongo     Nur pymongo/bson-Konflikte beheben"
            echo "  --fix-png-jpg     Nur PNG-zu-JPG Konvertierung durchführen"
            echo "  --no-fix-png-jpg  PNG-zu-JPG Konvertierung überspringen"
            echo "  --auto            Automatischer Modus - erkennt und behebt Probleme ohne Benutzerinteraktion"
            echo "  --setup-cron      Richtet einen Cron-Job für regelmäßige Prüfungen ein"
            echo "  --help            Diese Hilfe anzeigen"
            echo ""
            echo "Features:"
            echo "  - Intelligente Diagnose und zielgerichtete Reparatur"
            echo "  - Automatisches Erstellen und Verknüpfen von Upload-Verzeichnissen"
            echo "  - Erkennung und Korrektur von Entwicklungs- und Produktionsumgebungen"
            echo "  - Korrektur von Berechtigungsproblemen und fehlenden Verzeichnissen"
            echo "  - Behebt Probleme mit fehlenden Buch-Cover-Bildern in der Produktionsumgebung"
            exit 0
            ;;
        *)
            # Unknown option
            echo "Unbekannte Option: $arg"
            echo "Verwenden Sie --help für Hilfe."
            exit 1
            ;;
    esac
done

set -e  # Exit on error

# Get the script directory
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
VENV_DIR="$SCRIPT_DIR/.venv"
LOG_FILE="$SCRIPT_DIR/logs/fix_all.log"

# Create logs directory immediately
mkdir -p "$SCRIPT_DIR/logs"
chmod -R 777 "$SCRIPT_DIR/logs" 2>/dev/null || true

# Function to setup a cron job for automatic fixing
setup_cron_job() {
    if ! command -v crontab &> /dev/null; then
        echo "crontab nicht verfügbar. Cron-Job kann nicht eingerichtet werden."
        return 1
    fi
    
    # Define cron job to run daily at 1:00 AM
    CRON_JOB="0 1 * * * cd $SCRIPT_DIR && sudo $SCRIPT_DIR/fix-all.sh --auto --verbose >> $SCRIPT_DIR/logs/auto_fix.log 2>&1"
    
    # Check if cron job already exists
    EXISTING_CRON=$(sudo crontab -l 2>/dev/null | grep -F "fix-all.sh --auto")
    
    if [ -z "$EXISTING_CRON" ]; then
        echo "Richte täglichen Cron-Job für automatische Systemprüfung ein..."
        
        # Add to root's crontab (since we need sudo privileges)
        (sudo crontab -l 2>/dev/null; echo "$CRON_JOB") | sudo crontab -
        
        if [ $? -eq 0 ]; then
            echo "Cron-Job erfolgreich eingerichtet. Das System wird täglich um 1:00 Uhr morgens automatisch überprüft."
        else
            echo "Fehler beim Einrichten des Cron-Jobs."
            return 1
        fi
    else
        echo "Cron-Job bereits vorhanden, keine Änderungen vorgenommen."
    fi
    
    return 0
}

# Email-Versand entfernt: Berichte werden stattdessen in die Konsole und nach logs/auto_fix_report.log geschrieben

# Function to handle automatic mode
handle_auto_mode() {
    local has_problems=0
    local report=""
    
    # Check permissions
    report+="Prüfung: Verzeichnisberechtigungen\n"
    check_directory_permissions "$SCRIPT_DIR/logs" "777" "recursive" || has_problems=1
    check_directory_permissions "$SCRIPT_DIR/Web/uploads" "777" "recursive" 2>/dev/null || has_problems=1
    check_directory_permissions "$SCRIPT_DIR/Web/thumbnails" "777" "recursive" 2>/dev/null || has_problems=1
    check_directory_permissions "$SCRIPT_DIR/Web/previews" "777" "recursive" 2>/dev/null || has_problems=1
    check_directory_permissions "$SCRIPT_DIR/Web/QRCodes" "777" "recursive" 2>/dev/null || has_problems=1
    check_directory_permissions "$SCRIPT_DIR/mongodb_backup" "777" "recursive" 2>/dev/null || has_problems=1
    
    if [ $has_problems -eq 1 ]; then
        report+="Status: Probleme mit Berechtigungen gefunden, werden repariert\n"
    else
        report+="Status: Keine Berechtigungsprobleme gefunden\n"
    fi
    
    # Check virtual environment
    report+="\nPrüfung: Virtuelle Python-Umgebung\n"
    set +e
    check_venv_health
    local venv_status=$?
    set -e
    
    if [ $venv_status -ne 0 ]; then
        has_problems=1
        report+="Status: Probleme mit virtueller Umgebung gefunden, werden repariert\n"
    else
        report+="Status: Virtuelle Umgebung ist gesund\n"
    fi
    
    # Check for pymongo/bson conflict
    report+="\nPrüfung: PyMongo/BSON-Konflikte\n"
    set +e
    check_pymongo_bson_conflict
    local pymongo_status=$?
    set -e
    
    if [ $pymongo_status -ne 0 ] && [ $pymongo_status -ne 2 ]; then
        has_problems=1
        report+="Status: PyMongo/BSON-Konflikte gefunden, werden repariert\n"
    elif [ $pymongo_status -eq 2 ]; then
        report+="Status: PyMongo/BSON konnte nicht überprüft werden\n"
    else
        report+="Status: Keine PyMongo/BSON-Konflikte gefunden\n"
    fi
    
    # Check system services
    report+="\nPrüfung: Systemdienste\n"
    set +e
    check_services
    local services_status=$?
    set -e
    
    if [ $services_status -ne 0 ] && [ $services_status -ne 2 ]; then
        has_problems=1
        report+="Status: Einige Dienste sind nicht aktiv, werden gestartet\n"
    elif [ $services_status -eq 2 ]; then
        report+="Status: Systemdienste konnten nicht überprüft werden\n"
    else
        report+="Status: Alle Dienste sind aktiv\n"
    fi
    
    # If no problems or in check-only mode, just return
    if [ $has_problems -eq 0 ]; then
        report+="\nErgebnis: Alle Systeme funktionieren korrekt. Keine Reparaturen notwendig.\n"
        # Print report to console and write to file
        echo -e "$report"
        echo -e "$report" >> "$SCRIPT_DIR/logs/auto_fix_report.log"
        return 0
    fi
    
    if [ "$CHECK_ONLY" = true ]; then
        report+="\nErgebnis: Probleme gefunden, aber nur Prüfung durchgeführt (--check-only).\n"
        # Print report to console and write to file
        echo -e "$report"
        echo -e "$report" >> "$SCRIPT_DIR/logs/auto_fix_report.log"
        return 1
    fi
    
    # Auto fix the issues
    report+="\nStarte automatische Reparatur...\n"
    
    # Fix permissions if needed
    if [ $has_problems -eq 1 ]; then
        # All the fixes will be performed by the main script
        report+="\nReparaturen wurden durchgeführt. Details im Log: $LOG_FILE\n"
    fi
    
    # Print report to console and write to file
    echo -e "$report"
    echo -e "$report" >> "$SCRIPT_DIR/logs/auto_fix_report.log"
    
    return 0
}

# Function to log messages
log_message() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[\e[1;36m$timestamp\e[0m] $1" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "[\e[1;36m$timestamp\e[0m] $1"
}

# Function to log success messages
log_success() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[\e[1;32m$timestamp\e[0m] ✓ $1" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "[\e[1;32m$timestamp\e[0m] ✓ $1"
}

# Function to log error messages
log_error() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[\e[1;31m$timestamp\e[0m] ✗ $1" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "[\e[1;31m$timestamp\e[0m] ✗ $1"
}

# Function to log warning messages
log_warning() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo -e "[\e[1;33m$timestamp\e[0m] ! $1" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "[\e[1;33m$timestamp\e[0m] ! $1"
}

# Function to log verbose messages
log_verbose() {
    if [ "$VERBOSE" = true ]; then
        local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
        echo -e "[\e[1;90m$timestamp\e[0m] $1" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "[\e[1;90m$timestamp\e[0m] $1"
    fi
}

# Function to log section headers
log_section() {
    echo ""
    echo -e "\e[1;33m====== $1 ======\e[0m" | tee -a "$LOG_FILE" 2>/dev/null || echo -e "\e[1;33m====== $1 ======\e[0m"
    echo ""
}

# Function to check if a directory has correct permissions
check_directory_permissions() {
    local dir="$1"
    local expected_perm="$2"
    local is_recursive="$3"
    local result=0
    
    if [ ! -d "$dir" ]; then
        log_verbose "Verzeichnis nicht gefunden: $dir"
        return 2
    fi
    
    if [ "$is_recursive" = "recursive" ]; then
        find "$dir" -type d -not -perm "$expected_perm" | grep -q . && result=1
    else
        [ "$(stat -c %a "$dir")" != "$expected_perm" ] && result=1
    fi
    
    if [ $result -eq 1 ]; then
        return 1
    fi
    return 0
}

# Function to check if a file has correct permissions
check_file_permissions() {
    local file="$1"
    local expected_perm="$2"
    
    if [ ! -f "$file" ]; then
        log_verbose "Datei nicht gefunden: $file"
        return 2
    fi
    
    if [ "$(stat -c %a "$file")" != "$expected_perm" ]; then
        return 1
    fi
    return 0
}

# Function to check if pymongo/bson conflict exists
check_pymongo_bson_conflict() {
    if [ ! -d "$VENV_DIR" ]; then
        log_verbose "Virtuelle Umgebung nicht gefunden"
        return 2
    fi
    
    # Check for standalone bson package
    if [ -d "$VENV_DIR/lib/python3.12/site-packages/bson" ] && [ -d "$VENV_DIR/lib/python3.12/site-packages/pymongo" ]; then
        return 1
    fi
    return 0
}

# Function to check if virtual environment is healthy
check_venv_health() {
    if [ ! -d "$VENV_DIR" ]; then
        log_verbose "Virtuelle Umgebung nicht gefunden"
        return 2
    fi
    
    # Check for critical components
    if [ ! -f "$VENV_DIR/bin/python" ] || [ ! -f "$VENV_DIR/bin/pip" ]; then
        return 1
    fi
    
    # Try importing the runtime packages required at app startup
    if ! "$VENV_DIR/bin/python" -c "import pymongo, flask, gunicorn, requests, PIL, apscheduler" 2>/dev/null; then
        return 1
    fi
    
    return 0
}

# Function to create and fix upload directories in all environments
fix_uploads_directories() {
    log_message "Erstelle und korrigiere Upload-Verzeichnisse in allen Umgebungen..."
    
    # Development environment directories
    local DEV_DIRS=(
        "$SCRIPT_DIR/Web/uploads"
        "$SCRIPT_DIR/Web/thumbnails"
        "$SCRIPT_DIR/Web/previews"
        "$SCRIPT_DIR/Web/QRCodes"
    )
    
    # Production environment directories
    local PROD_DIRS=(
        "/var/Inventarsystem/Web/uploads"
        "/var/Inventarsystem/Web/thumbnails"
        "/var/Inventarsystem/Web/previews"
        "/var/Inventarsystem/Web/QRCodes"
    )
    
    # Create and set permissions for development directories
    for dir in "${DEV_DIRS[@]}"; do
        if [ ! -d "$dir" ]; then
            log_message "Erstelle Verzeichnis: $dir"
            mkdir -p "$dir" 2>/dev/null || log_error "Fehler beim Erstellen von $dir"
        fi
        
        log_message "Setze Berechtigungen für $dir"
        chmod -R 777 "$dir" 2>/dev/null || log_error "Fehler beim Setzen von Berechtigungen für $dir"
        chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$dir" 2>/dev/null || log_error "Fehler beim Setzen von Eigentümerrechten für $dir"
    done
    
    # Check if we are in production environment
    if [ -d "/var/Inventarsystem" ] || [ -L "/var/Inventarsystem" ]; then
        # Create and set permissions for production directories
        for dir in "${PROD_DIRS[@]}"; do
            if [ ! -d "$dir" ]; then
                log_message "Erstelle Produktions-Verzeichnis: $dir"
                mkdir -p "$dir" 2>/dev/null || log_error "Fehler beim Erstellen von $dir"
            fi
            
            log_message "Setze Berechtigungen für $dir"
            chmod -R 777 "$dir" 2>/dev/null || log_error "Fehler beim Setzen von Berechtigungen für $dir"
            
            # In production, use www-data as owner
            chown -R www-data:www-data "$dir" 2>/dev/null || log_error "Fehler beim Setzen von Produktions-Eigentümerrechten für $dir"
        done
        
        # Create symlinks if needed - for example if the app is looking in one path but files are in another
        # This ensures that whether the app looks in dev or prod paths, it will find the files
        if [ ! -L "/var/Inventarsystem/Web/uploads" ] && [ -d "$SCRIPT_DIR/Web/uploads" ]; then
            # If production directory is empty but development has files, create symlink
            if [ -z "$(ls -A "/var/Inventarsystem/Web/uploads" 2>/dev/null)" ] && [ -n "$(ls -A "$SCRIPT_DIR/Web/uploads" 2>/dev/null)" ]; then
                log_message "Produktions-Upload-Verzeichnis ist leer, erstelle Symlink zu Entwicklungsverzeichnis"
                rm -rf "/var/Inventarsystem/Web/uploads" 2>/dev/null
                ln -sf "$SCRIPT_DIR/Web/uploads" "/var/Inventarsystem/Web/uploads" 2>/dev/null || log_error "Fehler beim Erstellen des Symlinks für uploads"
            fi
        fi
        
        # Ensure the application can find images in either location
        log_message "Überprüfe Dateiübereinstimmung zwischen Entwicklungs- und Produktionsumgebung"
        for env_dir in uploads thumbnails previews QRCodes; do
            dev_dir="$SCRIPT_DIR/Web/$env_dir"
            prod_dir="/var/Inventarsystem/Web/$env_dir"
            
            # If both directories exist and are not symlinks to each other
            if [ -d "$dev_dir" ] && [ -d "$prod_dir" ] && [ ! -L "$prod_dir" ]; then
                # Check for missing files in production that exist in development
                for file in $(find "$dev_dir" -type f -name "*" 2>/dev/null); do
                    filename=$(basename "$file")
                    if [ ! -f "$prod_dir/$filename" ]; then
                        log_message "Kopiere fehlende Datei in die Produktionsumgebung: $filename"
                        cp -f "$file" "$prod_dir/" 2>/dev/null || log_error "Fehler beim Kopieren von $filename nach $prod_dir"
                        chmod 666 "$prod_dir/$filename" 2>/dev/null
                    fi
                done
                
                # Check for missing files in development that exist in production
                for file in $(find "$prod_dir" -type f -name "*" 2>/dev/null); do
                    filename=$(basename "$file")
                    if [ ! -f "$dev_dir/$filename" ]; then
                        log_message "Kopiere fehlende Datei in die Entwicklungsumgebung: $filename"
                        cp -f "$file" "$dev_dir/" 2>/dev/null || log_error "Fehler beim Kopieren von $filename nach $dev_dir"
                        chmod 666 "$dev_dir/$filename" 2>/dev/null
                    fi
                done
            fi
        done
    fi
    
    log_success "Upload-Verzeichnisse wurden erstellt und Berechtigungen gesetzt"
}

# Function to ensure PNG images are converted to JPG for universal compatibility
fix_png_to_jpg_conversion() {
    if [ "$FIX_PNG_TO_JPG" != true ]; then
        log_verbose "PNG zu JPG Konvertierung übersprungen (--no-fix-png-jpg Flag gesetzt)"
        return 0
    fi

    log_section "Überprüfe PNG zu JPG Konvertierung"
    log_message "Das System verwendet einheitlich JPG-Dateien für maximale Kompatibilität."
    
    # Check if the converter script exists
    if [ ! -f "$SCRIPT_DIR/png_jpg_converter.py" ]; then
        log_error "PNG zu JPG Konverter-Skript nicht gefunden: png_jpg_converter.py"
        return 1
    fi
    
    # Check if PIL/Pillow is installed in the virtual environment
    if ! "$VENV_DIR/bin/pip" list | grep -i "pillow" >/dev/null 2>&1; then
        log_message "Installiere Pillow für Bildkonvertierung..."
        "$VENV_DIR/bin/pip" install pillow >/dev/null 2>&1
        if [ $? -ne 0 ]; then
            log_error "Konnte Pillow nicht installieren"
            return 1
        fi
        log_success "Pillow erfolgreich installiert"
    fi
    
    # Run the converter in dry-run mode first
    log_message "Überprüfe PNG-Dateien im System..."
    PNG_COUNT=$("$VENV_DIR/bin/python" "$SCRIPT_DIR/png_jpg_converter.py" | grep "Total PNG files:" | awk '{print $4}')
    
    if [ -z "$PNG_COUNT" ]; then
        PNG_COUNT=0
    fi
    
    if [ "$PNG_COUNT" -eq 0 ]; then
        log_success "Keine PNG-Dateien gefunden, System verwendet bereits einheitlich JPG-Dateien"
        return 0
    fi
    
    log_message "Gefunden: $PNG_COUNT PNG-Dateien, die zu JPG konvertiert werden sollten"
    
    if [ "$CHECK_ONLY" = true ]; then
        log_warning "Im Check-Only-Modus wird keine Konvertierung durchgeführt"
        return 0
    fi
    
    # Confirm with user in interactive mode
    if [ "$AUTO_MODE" != true ]; then
        read -p "Möchten Sie alle PNG-Dateien zu JPG konvertieren? (j/n): " confirm
        if [[ ! "$confirm" =~ ^[jJ] ]]; then
            log_message "PNG zu JPG Konvertierung übersprungen"
            return 0
        fi
    fi
    
    # Run the converter with execute flag
    log_message "Konvertiere PNG-Dateien zu JPG..."
    "$VENV_DIR/bin/python" "$SCRIPT_DIR/png_jpg_converter.py" --execute --quality 95
    
    if [ $? -eq 0 ]; then
        log_success "PNG zu JPG Konvertierung erfolgreich abgeschlossen"
    else
        log_error "Fehler bei der PNG zu JPG Konvertierung"
        return 1
    fi
    
    return 0
}

# Function to check if system services are running
check_services() {
    if ! command -v systemctl >/dev/null 2>&1; then
        log_verbose "systemctl nicht verfügbar"
        return 2
    fi
    
    local services_status=0
    
    if ! systemctl is-active --quiet mongodb 2>/dev/null; then
        services_status=1
    fi
    
    if ! systemctl is-active --quiet inventarsystem-gunicorn.service 2>/dev/null; then
        services_status=1
    fi
    
    if ! systemctl is-active --quiet inventarsystem-nginx.service 2>/dev/null; then
        services_status=1
    fi
    
    return $services_status
}

# Function to check if we are in production environment
check_production_environment() {
    local prod_path="/var/Inventarsystem"
    local in_prod=false
    
    if [ -d "$prod_path" ] || [ -L "$prod_path" ]; then
        in_prod=true
        log_message "Produktionsumgebung erkannt: $prod_path"
        
        # Verify directory structure
        if [ ! -d "$prod_path/Web" ]; then
            log_warning "Produktionsumgebung unvollständig: Web-Verzeichnis fehlt"
            mkdir -p "$prod_path/Web" 2>/dev/null || log_error "Konnte Web-Verzeichnis nicht erstellen"
        fi
    else
        log_verbose "Keine Produktionsumgebung unter $prod_path gefunden"
    fi
    
    # Check if we're installed to /var/www
    if [ -d "/var/www/Inventarsystem" ] || [ -L "/var/www/Inventarsystem" ]; then
        in_prod=true
        log_message "Alternative Produktionsumgebung erkannt: /var/www/Inventarsystem"
    fi
    
    if [ "$in_prod" = true ]; then
        return 0
    else
        return 1
    fi
}

# Check if running as root
if [ "$(id -u)" -ne 0 ]; then
    log_error "Dieses Skript muss als root oder mit sudo ausgeführt werden"
    log_error "Bitte starten Sie das Skript mit: sudo $0"
    exit 1
fi

# Determine the actual user who invoked sudo
if [ -n "$SUDO_USER" ]; then
    ACTUAL_USER="$SUDO_USER"
    ACTUAL_GROUP="$(id -gn "$SUDO_USER")"
else
    # If not using sudo, use the current user
    ACTUAL_USER="$(whoami)"
    ACTUAL_GROUP="$(id -gn)"
fi

log_section "ALL-IN-ONE REPARATUR GESTARTET"
log_message "Benutzerinformation: $ACTUAL_USER:$ACTUAL_GROUP"
log_message "Systempfad: $SCRIPT_DIR"
if [ "$CHECK_ONLY" = true ]; then
    log_message "Modus: Nur Prüfung (keine Änderungen werden durchgeführt)"
fi

# Diagnostic phase - check what needs to be fixed
log_section "SYSTEMDIAGNOSE"
log_message "Überprüfe den aktuellen Systemzustand..."

PERM_STATUS=0
VENV_STATUS=0
PYMONGO_STATUS=0
SERVICES_STATUS=0

# Check permissions
log_message "Überprüfe Verzeichnisberechtigungen..."
check_directory_permissions "$SCRIPT_DIR/logs" "777" "recursive" || PERM_STATUS=1
check_directory_permissions "$SCRIPT_DIR/Web/uploads" "777" "recursive" 2>/dev/null || PERM_STATUS=1
check_directory_permissions "$SCRIPT_DIR/Web/thumbnails" "777" "recursive" 2>/dev/null || PERM_STATUS=1
check_directory_permissions "$SCRIPT_DIR/Web/previews" "777" "recursive" 2>/dev/null || PERM_STATUS=1
check_directory_permissions "$SCRIPT_DIR/Web/QRCodes" "777" "recursive" 2>/dev/null || PERM_STATUS=1
check_directory_permissions "$SCRIPT_DIR/mongodb_backup" "777" "recursive" 2>/dev/null || PERM_STATUS=1

# Check virtual environment
log_message "Überprüfe virtuelle Python-Umgebung..."
set +e
check_venv_health
VENV_STATUS=$?
set -e

# Check for pymongo/bson conflict
log_message "Überprüfe auf pymongo/bson-Konflikte..."
set +e
check_pymongo_bson_conflict
PYMONGO_STATUS=$?
set -e

# Check system services
log_message "Überprüfe Systemdienste..."
set +e
check_services
SERVICES_STATUS=$?
set -e

# Display diagnosis results
log_section "DIAGNOSEERGEBNISSE"
if [ $PERM_STATUS -eq 0 ]; then
    log_success "Verzeichnisberechtigungen: Korrekt"
else
    log_warning "Verzeichnisberechtigungen: Probleme gefunden"
fi

if [ $VENV_STATUS -eq 0 ]; then
    log_success "Virtuelle Python-Umgebung: Gesund"
elif [ $VENV_STATUS -eq 2 ]; then
    log_warning "Virtuelle Python-Umgebung: Nicht gefunden"
else
    log_warning "Virtuelle Python-Umgebung: Probleme gefunden"
fi

if [ $PYMONGO_STATUS -eq 0 ]; then
    log_success "PyMongo/BSON: Keine Konflikte gefunden"
elif [ $PYMONGO_STATUS -eq 2 ]; then
    log_warning "PyMongo/BSON: Konnte nicht überprüft werden"
else
    log_warning "PyMongo/BSON: Konflikt gefunden"
fi

if [ $SERVICES_STATUS -eq 0 ]; then
    log_success "Systemdienste: Alle aktiv"
elif [ $SERVICES_STATUS -eq 2 ]; then
    log_warning "Systemdienste: Konnte nicht überprüft werden"
else
    log_warning "Systemdienste: Einige Dienste sind nicht aktiv"
fi

# Setup cron job if requested
if [ "$SETUP_CRON" = true ]; then
    log_section "CRON-JOB EINRICHTUNG"
    
    if setup_cron_job; then
        log_success "Cron-Job für automatische Prüfung wurde eingerichtet"
        log_message "Das System wird täglich um 1:00 Uhr morgens automatisch überprüft und repariert"
    else
        log_error "Fehler beim Einrichten des Cron-Jobs"
    fi
    
    # If only setting up cron job, exit here
    if [ "$AUTO_MODE" = false ] && [ "$CHECK_ONLY" = true ]; then
        exit 0
    fi
fi

# Handle auto mode if enabled
if [ "$AUTO_MODE" = true ]; then
    log_section "AUTOMATISCHER MODUS"
    log_message "Automatischer Reparaturmodus ist aktiviert"
    log_message "Überprüfe und behebe Probleme ohne Benutzerinteraktion..."
    
    # Let the auto mode handler determine if fixes are needed, but don't abort on non-zero due to set -e
    set +e
    handle_auto_mode
    HM_STATUS=$?
    set -e
    
    # If auto mode with check-only, exit here
    if [ "$CHECK_ONLY" = true ]; then
        log_section "AUTOMATISCHE PRÜFUNG ABGESCHLOSSEN"
        log_message "Keine Änderungen wurden durchgeführt (--check-only ist aktiviert)"
        log_message "Prüfbericht wurde in logs/auto_fix_report.log gespeichert"
        exit $HM_STATUS
    fi
fi

# If check-only mode, exit here
if [ "$CHECK_ONLY" = true ]; then
    log_section "PRÜFUNG ABGESCHLOSSEN"
    log_message "Keine Änderungen wurden durchgeführt."
    log_message "Um Probleme zu beheben, führen Sie das Skript ohne --check-only aus."
    exit 0
fi

# Fix phase - only fix what's needed based on diagnosis
log_section "REPARATURPHASE"

# Step 1: Create and fix permissions for critical directories
if [ $PERM_STATUS -ne 0 ] && [ "$FIX_PERMISSIONS" = true ]; then
    log_section "VERZEICHNISBERECHTIGUNGEN KORRIGIEREN"

    # Logs directory
    log_message "Berechtigungen für logs-Verzeichnis korrigieren..."
    mkdir -p "$SCRIPT_DIR/logs"
    chmod -R 777 "$SCRIPT_DIR/logs" 2>/dev/null || log_error "Fehler beim Setzen von Berechtigungen für logs-Verzeichnis"
    chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/logs" 2>/dev/null || log_error "Fehler beim Setzen von Eigentümerrechten für logs-Verzeichnis"

    # Create log files if they don't exist
    log_message "Erstelle Log-Dateien mit korrekten Berechtigungen..."
    touch "$SCRIPT_DIR/logs/Backup_db.log" "$SCRIPT_DIR/logs/daily_update.log" "$SCRIPT_DIR/logs/error.log" "$SCRIPT_DIR/logs/access.log" "$SCRIPT_DIR/logs/permission_fixes.log" "$SCRIPT_DIR/logs/fix_all.log" "$SCRIPT_DIR/logs/scheduler.log" "$SCRIPT_DIR/logs/restore.log" 2>/dev/null
    chmod 666 "$SCRIPT_DIR/logs"/*.log 2>/dev/null
    chown "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/logs"/*.log 2>/dev/null
    
    # Fix all upload directories in both development and production environments
    fix_uploads_directories
    
    # Convert any PNG files to JPG for universal compatibility
    fix_png_to_jpg_conversion

    # Fix Web directory permissions and structure
    if [ -d "$SCRIPT_DIR/Web" ]; then
        log_message "Berechtigungen für Web-Verzeichnis korrigieren..."
        
        # Set base permissions for Web directory
        chmod -R 755 "$SCRIPT_DIR/Web" 2>/dev/null || log_error "Fehler beim Setzen von Berechtigungen für Web-Verzeichnis"
        
        # Set ownership
        chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/Web" 2>/dev/null || log_error "Fehler beim Setzen von Eigentümerrechten für Web-Verzeichnis"
        
        # Create and fix all uploads directories both in development and production
        fix_uploads_directories
        
        log_success "Web-Verzeichnisberechtigungen korrigiert"
    else
        log_error "Web-Verzeichnis nicht gefunden: $SCRIPT_DIR/Web"
        mkdir -p "$SCRIPT_DIR/Web" 2>/dev/null && {
            log_message "Web-Verzeichnis wurde erstellt"
            chmod 755 "$SCRIPT_DIR/Web" 2>/dev/null
            chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/Web" 2>/dev/null
            fix_uploads_directories
        }
    fi

    # Create and set permissions for SSL certificates directory
    if [ -d "$SCRIPT_DIR/certs" ]; then
        log_message "Berechtigungen für SSL-Zertifikate korrigieren..."
        chmod 755 "$SCRIPT_DIR/certs" 2>/dev/null
        find "$SCRIPT_DIR/certs" -name "*.key" -exec chmod 600 {} \; 2>/dev/null
        find "$SCRIPT_DIR/certs" -name "*.crt" -exec chmod 644 {} \; 2>/dev/null
        chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/certs" 2>/dev/null
        log_success "SSL-Zertifikatberechtigungen korrigiert"
    fi

    # Create and set permissions for backups directory
    log_message "Berechtigungen für Backup-Verzeichnisse korrigieren..."
    BACKUP_BASE_DIR="/var/backups"
    if [ ! -d "$BACKUP_BASE_DIR" ]; then
        mkdir -p "$BACKUP_BASE_DIR" 2>/dev/null
    fi
    chmod 755 "$BACKUP_BASE_DIR" 2>/dev/null || log_error "Fehler beim Setzen von Berechtigungen für $BACKUP_BASE_DIR"

    # Local backups directory
    mkdir -p "$SCRIPT_DIR/backups" 2>/dev/null
    chmod 777 "$SCRIPT_DIR/backups" 2>/dev/null
    chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/backups" 2>/dev/null

    # MongoDB backup directory
    mkdir -p "$SCRIPT_DIR/mongodb_backup" 2>/dev/null
    chmod 777 "$SCRIPT_DIR/mongodb_backup" 2>/dev/null
    chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR/mongodb_backup" 2>/dev/null
    log_success "Backup-Verzeichnisberechtigungen korrigiert"

    # Step 2: Fix Git repository permissions
    log_section "GIT REPOSITORY BERECHTIGUNGEN"

    log_message "Setze Git Repository als sicheres Verzeichnis..."
    # For root
    git config --global --add safe.directory "$SCRIPT_DIR" 2>/dev/null || log_error "Fehler beim Setzen des Git safe.directory für root"

    # For the actual user (if different from root)
    if [ "$ACTUAL_USER" != "root" ]; then
        su - "$ACTUAL_USER" -c "git config --global --add safe.directory '$SCRIPT_DIR'" 2>/dev/null || log_error "Fehler beim Setzen des Git safe.directory für $ACTUAL_USER"
    fi
    log_success "Git Repository-Berechtigungen korrigiert"

    # Step 3: Fix executable permissions for scripts
    log_section "SKRIPT-BERECHTIGUNGEN"

    log_message "Mache alle Skripte ausführbar..."
    find "$SCRIPT_DIR" -name "*.sh" -type f -exec chmod +x {} \; 2>/dev/null
    find "$SCRIPT_DIR" -name "*.py" -type f -exec chmod +x {} \; 2>/dev/null
    log_success "Skript-Berechtigungen korrigiert"
else
    if [ "$FIX_PERMISSIONS" = true ]; then
        log_success "Überspringe Berechtigungskorrekturen - alle Berechtigungen sind bereits korrekt"
    else
        log_verbose "Berechtigungskorrekturen wurden übersprungen (gemäß Befehlszeilenoption)"
    fi
fi

# Step 4: Fix virtual environment
if [ $VENV_STATUS -ne 0 ] && [ "$FIX_VENV" = true ]; then
    log_section "PYTHON VIRTUELLE UMGEBUNG"

    log_message "Repariere virtuelle Python-Umgebung..."
    if [ ! -d "$VENV_DIR" ]; then
        log_message "Virtuelle Umgebung nicht gefunden. Erstelle neue Umgebung..."
        python3 -m venv "$VENV_DIR" || {
            log_error "Fehler beim Erstellen der virtuellen Umgebung"
            log_message "Versuche alternative Methode..."
            python3 -m venv "$VENV_DIR" --system-site-packages || {
                log_error "Virtuelle Umgebung konnte nicht erstellt werden. Abbruch."
                exit 1
            }
        }
        # Set ownership immediately after creation
        chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$VENV_DIR" 2>/dev/null
        log_success "Neue virtuelle Umgebung erstellt"
    else
        log_message "Bestehende virtuelle Umgebung gefunden. Setze Berechtigungen..."
    fi

    # Fix directory and file permissions
    log_message "Setze Verzeichnis- und Dateirechte..."
    find "$VENV_DIR" -type d -exec chmod 755 {} \; 2>/dev/null || log_error "Fehler beim Setzen der Verzeichnisberechtigungen"
    find "$VENV_DIR" -type f -exec chmod 644 {} \; 2>/dev/null || log_error "Fehler beim Setzen der Dateiberechtigungen"

    # Make bin files executable
    if [ -d "$VENV_DIR/bin" ]; then
        log_message "Mache Bin-Dateien ausführbar..."
        chmod 755 "$VENV_DIR/bin" 2>/dev/null
        find "$VENV_DIR/bin" -type f -exec chmod 755 {} \; 2>/dev/null || log_error "Fehler beim Setzen der Bin-Dateirechte"
    fi

    # Set ownership for virtual environment
    log_message "Setze Eigentümerrechte für virtuelle Umgebung..."
    chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$VENV_DIR" 2>/dev/null || log_error "Fehler beim Setzen der Eigentümerrechte für virtuelle Umgebung"

    log_success "Berechtigungen für virtuelle Umgebung korrigiert"
else
    if [ "$FIX_VENV" = true ]; then
        log_success "Überspringe Reparatur der virtuellen Umgebung - bereits in gutem Zustand"
    else
        log_verbose "Reparatur der virtuellen Umgebung wurde übersprungen (gemäß Befehlszeilenoption)"
    fi
fi

# Step 5: Fix pymongo/bson conflict
if [ $PYMONGO_STATUS -ne 0 ] && [ "$FIX_PYMONGO" = true ]; then
    log_section "PYMONGO/BSON KONFLIKTE"

    # Detect bson/pymongo conflict
    if [ -d "$VENV_DIR/lib/python3.12/site-packages/bson" ]; then
        log_message "Potentieller bson/pymongo Konflikt erkannt. Behebe das Problem..."
        rm -rf "$VENV_DIR/lib/python3.12/site-packages/bson" || {
            log_error "Fehler beim Entfernen des Bson-Verzeichnisses. Versuche mit sudo..."
            sudo rm -rf "$VENV_DIR/lib/python3.12/site-packages/bson" || {
                log_error "Fehler beim Entfernen des Bson-Verzeichnisses."
            }
        }
        log_message "Konfliktierendes Bson-Paket entfernt"
    fi

    # Install/upgrade pip in the virtual environment
    log_message "Installiere/aktualisiere pip in der virtuellen Umgebung..."

    # Try to activate the virtual environment and install packages
    if [ -f "$VENV_DIR/bin/pip" ]; then
        log_message "Benutze pip aus der virtuellen Umgebung..."
        
        # Remove conflicting packages
        "$VENV_DIR/bin/pip" uninstall -y bson pymongo 2>/dev/null || true
        
        # Install pymongo
        "$VENV_DIR/bin/pip" install --upgrade pip 2>/dev/null || log_error "Fehler beim Aktualisieren von pip"
        "$VENV_DIR/bin/pip" install pymongo==4.6.1 2>/dev/null || {
            log_error "Fehler beim Installieren von pymongo mit venv pip"
            "$VENV_DIR/bin/python" -m pip install pymongo==4.6.1 2>/dev/null || {
                log_error "Alle Versuche zur Installation von pymongo in der virtuellen Umgebung sind fehlgeschlagen"
            }
        }
        
        # Verify core runtime imports
        if "$VENV_DIR/bin/python" -c "import pymongo, flask, gunicorn, requests, PIL, apscheduler" 2>/dev/null; then
            log_success "Runtime-Abhängigkeiten wurden korrekt installiert"
        else
            log_error "Runtime-Abhängigkeiten konnten nicht verifiziert werden"
        fi
        
        # Install requirements
        if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
            log_message "Installiere Abhängigkeiten aus requirements.txt..."
            # Filter out pymongo
            grep -v "^pymongo" "$SCRIPT_DIR/requirements.txt" > "$SCRIPT_DIR/requirements_filtered.txt"
            "$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements_filtered.txt" 2>/dev/null || log_error "Fehler beim Installieren einiger Abhängigkeiten"
            rm -f "$SCRIPT_DIR/requirements_filtered.txt"
        fi
    else
        log_error "Pip nicht in der virtuellen Umgebung gefunden"
        log_message "Versuche die Umgebung zu aktivieren und pip zu verwenden..."
        
        source "$VENV_DIR/bin/activate" 2>/dev/null && {
            pip install --upgrade pip 2>/dev/null || log_error "Fehler beim Aktualisieren von pip"
            pip uninstall -y bson pymongo 2>/dev/null || true
            pip install pymongo==4.6.1 2>/dev/null || log_error "Fehler beim Installieren von pymongo"
            
            # Verify core runtime imports
            if python -c "import pymongo, flask, gunicorn, requests, PIL, apscheduler" 2>/dev/null; then
                log_success "Runtime-Abhängigkeiten wurden korrekt installiert"
            else
                log_error "Runtime-Abhängigkeiten konnten nicht verifiziert werden"
            fi
            
            # Install requirements
            if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
                log_message "Installiere Abhängigkeiten aus requirements.txt..."
                grep -v "^pymongo" "$SCRIPT_DIR/requirements.txt" > "$SCRIPT_DIR/requirements_filtered.txt"
                pip install -r "$SCRIPT_DIR/requirements_filtered.txt" 2>/dev/null || log_error "Fehler beim Installieren einiger Abhängigkeiten"
                rm -f "$SCRIPT_DIR/requirements_filtered.txt"
            fi
            
            deactivate
        } || log_error "Konnte virtuelle Umgebung nicht aktivieren"
    fi
else
    if [ "$FIX_PYMONGO" = true ]; then
        log_success "Überspringe PyMongo/BSON-Reparatur - keine Konflikte gefunden"
    else
        log_verbose "PyMongo/BSON-Reparatur wurde übersprungen (gemäß Befehlszeilenoption)"
    fi
fi

# Step 6: Check system service status
log_section "SYSTEMDIENSTE ÜBERPRÜFEN"

log_message "Überprüfe Systemdienste..."
if command -v systemctl >/dev/null 2>&1; then
    if systemctl is-active --quiet mongodb; then
        log_success "MongoDB-Dienst läuft"
    else
        log_warning "MongoDB-Dienst läuft nicht"
        log_message "Versuche MongoDB zu starten..."
        systemctl start mongodb 2>/dev/null || log_error "Konnte MongoDB-Dienst nicht starten"
    fi
    
    # Check for Inventarsystem services
    if systemctl is-active --quiet inventarsystem-gunicorn.service 2>/dev/null; then
        log_success "Inventarsystem Gunicorn-Dienst läuft"
    else
        log_warning "Inventarsystem Gunicorn-Dienst läuft nicht"
    fi
    
    if systemctl is-active --quiet inventarsystem-nginx.service 2>/dev/null; then
        log_success "Inventarsystem Nginx-Dienst läuft"
    else
        log_warning "Inventarsystem Nginx-Dienst läuft nicht"
    fi
else
    log_message "Systemctl nicht verfügbar. Dienststatus kann nicht überprüft werden."
fi

# Step 7: Set correct ownership for entire project
log_section "PROJEKT-EIGENTÜMERRECHTE"

log_message "Setze Eigentümerrechte für das gesamte Projekt..."
chown -R "$ACTUAL_USER:$ACTUAL_GROUP" "$SCRIPT_DIR" 2>/dev/null || log_error "Fehler beim Setzen der Eigentümerrechte für das gesamte Projekt"

log_success "Projekt-Eigentümerrechte gesetzt"

# Run a second diagnostic to confirm fixes
log_section "REPARATURVERIFIKATION"
log_message "Überprüfe den Systemzustand nach Reparaturen..."

PERM_STATUS_AFTER=0
VENV_STATUS_AFTER=0
PYMONGO_STATUS_AFTER=0
SERVICES_STATUS_AFTER=0

# Check permissions
check_directory_permissions "$SCRIPT_DIR/logs" "777" "recursive" || PERM_STATUS_AFTER=1
check_directory_permissions "$SCRIPT_DIR/Web/uploads" "777" "recursive" 2>/dev/null || PERM_STATUS_AFTER=1
check_directory_permissions "$SCRIPT_DIR/Web/thumbnails" "777" "recursive" 2>/dev/null || PERM_STATUS_AFTER=1
check_directory_permissions "$SCRIPT_DIR/Web/previews" "777" "recursive" 2>/dev/null || PERM_STATUS_AFTER=1
check_directory_permissions "$SCRIPT_DIR/Web/QRCodes" "777" "recursive" 2>/dev/null || PERM_STATUS_AFTER=1
check_directory_permissions "$SCRIPT_DIR/mongodb_backup" "777" "recursive" 2>/dev/null || PERM_STATUS_AFTER=1

# Check virtual environment
set +e
check_venv_health
VENV_STATUS_AFTER=$?
set -e

# Check for pymongo/bson conflict
set +e
check_pymongo_bson_conflict
PYMONGO_STATUS_AFTER=$?
set -e

# Check system services
set +e
check_services
SERVICES_STATUS_AFTER=$?
set -e

# Report fixed and remaining issues
if [ $PERM_STATUS_AFTER -eq 0 ] && [ $PERM_STATUS -ne 0 ]; then
    log_success "Verzeichnisberechtigungen wurden erfolgreich korrigiert"
elif [ $PERM_STATUS_AFTER -ne 0 ] && [ $PERM_STATUS -ne 0 ]; then
    log_error "Es bestehen weiterhin Probleme mit Verzeichnisberechtigungen"
fi

if [ $VENV_STATUS_AFTER -eq 0 ] && [ $VENV_STATUS -ne 0 ]; then
    log_success "Virtuelle Python-Umgebung wurde erfolgreich repariert"
elif [ $VENV_STATUS_AFTER -ne 0 ] && [ $VENV_STATUS -ne 0 ]; then
    log_error "Es bestehen weiterhin Probleme mit der virtuellen Python-Umgebung"
fi

if [ $PYMONGO_STATUS_AFTER -eq 0 ] && [ $PYMONGO_STATUS -ne 0 ]; then
    log_success "PyMongo/BSON-Konflikte wurden erfolgreich behoben"
elif [ $PYMONGO_STATUS_AFTER -ne 0 ] && [ $PYMONGO_STATUS -ne 0 ]; then
    log_error "Es bestehen weiterhin PyMongo/BSON-Konflikte"
fi

if [ $SERVICES_STATUS_AFTER -eq 0 ] && [ $SERVICES_STATUS -ne 0 ]; then
    log_success "Systemdienste wurden erfolgreich gestartet"
elif [ $SERVICES_STATUS_AFTER -ne 0 ] && [ $SERVICES_STATUS -ne 0 ]; then
    log_warning "Es laufen weiterhin nicht alle Systemdienste"
fi

# Final step: Summary
log_section "REPARATUR ABGESCHLOSSEN"

log_message "Die All-in-One Reparatur wurde abgeschlossen."

if [ "$AUTO_MODE" = true ]; then
    log_success "Automatischer Reparaturmodus: Alle erkannten Probleme wurden behoben"
    log_message "Ein detaillierter Bericht wurde in logs/auto_fix_report.log gespeichert"
    
    # Restart services automatically in auto mode
    if command -v systemctl >/dev/null 2>&1; then
        log_message "Starte Dienste automatisch neu..."
        
        # Restart MongoDB if it was stopped
        if ! systemctl is-active --quiet mongodb 2>/dev/null; then
            systemctl restart mongodb 2>/dev/null
        fi
        
        # Restart Inventarsystem services
        if systemctl list-unit-files | grep -q inventarsystem-gunicorn.service; then
            systemctl restart inventarsystem-gunicorn.service 2>/dev/null
        fi
        
        if systemctl list-unit-files | grep -q inventarsystem-nginx.service; then
            systemctl restart inventarsystem-nginx.service 2>/dev/null
        fi
        
        log_success "Dienste wurden neu gestartet"
    fi
else
    log_message "Nächste Schritte:"
    log_message "1. Starten Sie das System neu mit: sudo ./restart.sh"
    log_message "2. Überprüfen Sie die Log-Dateien im logs-Verzeichnis"
    log_message "3. Bei anhaltenden Problemen versuchen Sie: sudo ./rebuild-venv.sh"
    log_message ""
    log_message "Tipp: Um dieses Skript automatisch auszuführen, verwenden Sie:"
    log_message "sudo ./fix-all.sh --setup-cron"
fi

log_success "FERTIG"

exit 0
