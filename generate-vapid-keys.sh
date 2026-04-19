#!/bin/bash

# VAPID Key Generation Script for Web Push Notifications
# Generates VAPID (Voluntary Application Server Identification) keys required for push notifications

echo "==========================================="
echo "VAPID Key Generation for Inventarsystem"
echo "==========================================="
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is required but not installed."
    exit 1
fi

# Check if pywebpush is installed
echo "Checking for pywebpush..."
python3 -c "import pywebpush" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "Installing pywebpush..."
    pip3 install pywebpush
    if [ $? -ne 0 ]; then
        echo "❌ Error: Failed to install pywebpush"
        echo "Please install manually: pip3 install pywebpush"
        exit 1
    fi
fi

echo "✓ pywebpush is installed"
echo ""

# Generate VAPID keys
echo "Generating VAPID keys..."
python3 << 'EOF'
from pywebpush import generate_keys

try:
    keys = generate_keys()
    print("✓ VAPID Keys generated successfully!")
    print("")
    print("PUBLIC KEY (share with browsers):")
    print(keys['public_key'])
    print("")
    print("PRIVATE KEY (keep secret!):")
    print(keys['private_key'])
    print("")
    print("==========================================="
    print("Add these to your environment variables:")
    print("==========================================="
    print("")
    print("export VAPID_PUBLIC_KEY='" + keys['public_key'] + "'")
    print("export VAPID_PRIVATE_KEY='" + keys['private_key'] + "'")
    print("export VAPID_SUBJECT='mailto:admin@yourdomain.com'")
    print("")
    print("Or add to your .env file:")
    print("")
    print("VAPID_PUBLIC_KEY=" + keys['public_key'])
    print("VAPID_PRIVATE_KEY=" + keys['private_key'])
    print("VAPID_SUBJECT=mailto:admin@yourdomain.com")
    print("")
    print("⚠️  IMPORTANT: Keep the PRIVATE KEY secret!")
    print("==========================================="
    
except Exception as e:
    print(f"❌ Error generating VAPID keys: {e}")
    exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Next steps:"
    echo "1. Copy the PUBLIC KEY to your browser-side code"
    echo "2. Set the PRIVATE KEY in your server environment"
    echo "3. Update config.json with your email address"
    echo "4. Test with: curl http://localhost:5000/api/push/vapid-key"
else
    echo "❌ Error generating keys"
    exit 1
fi
