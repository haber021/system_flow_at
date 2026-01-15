#!/bin/bash
# Enhanced Multi-Host Server Startup Script for Linux/Mac
# Configures and starts the Django server with network access

echo "========================================"
echo " Attendance Monitor - Multi-Host Server"
echo "========================================"
echo ""

# Get local IP address
echo "[*] Detecting network configuration..."
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    LOCAL_IP=$(hostname -I | awk '{print $1}')
elif [[ "$OSTYPE" == "darwin"* ]]; then
    LOCAL_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print $2}' | head -n1)
else
    LOCAL_IP="Unknown"
fi

echo ""
echo "[+] Server will be accessible at:"
echo "    - http://localhost:8000"
echo "    - http://127.0.0.1:8000"
if [ "$LOCAL_IP" != "Unknown" ] && [ ! -z "$LOCAL_IP" ]; then
    echo "    - http://$LOCAL_IP:8000 [Network Access]"
fi
echo "    - http://attendance-monitor.local:8000 [Custom Domain]"
echo "    - http://10.251.88.18:8000 [Static IP]"
echo ""

# Check if port is already in use
echo "[*] Checking if port 8000 is available..."
if lsof -Pi :8000 -sTCP:LISTEN -t >/dev/null 2>&1 ; then
    echo "[!] WARNING: Port 8000 is already in use!"
    echo "[!] Please close other applications using this port or use a different port."
    exit 1
fi

echo "[+] Port 8000 is available"
echo ""

# Check firewall (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "[*] Checking firewall configuration..."
    if command -v ufw &> /dev/null; then
        if sudo ufw status | grep -q "8000.*ALLOW" ; then
            echo "[+] Firewall rule exists"
        else
            echo "[!] Firewall rule not found!"
            read -p "[?] Add firewall rule to allow network access? (y/n) " -n 1 -r
            echo ""
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                echo "[*] Adding firewall rule..."
                sudo ufw allow 8000/tcp
                echo "[+] Firewall rule added!"
            fi
        fi
    fi
fi

echo ""
echo "[*] Starting Django development server..."
echo "[*] Press CTRL+C to stop the server"
echo ""
echo "========================================"
echo ""

# Start the server on all interfaces
python manage.py runserver 0.0.0.0:8000

# If server stopped
echo ""
echo "========================================"
echo "Server stopped."
echo "========================================"
