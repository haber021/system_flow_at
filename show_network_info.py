#!/usr/bin/env python3
"""
Network Connection Information Utility
Displays all available URLs to access the attendance monitoring system
"""

import socket
import sys
import os

def get_local_ips():
    """Get all local IP addresses"""
    ips = []
    
    # Get hostname IPs
    try:
        hostname = socket.gethostname()
        host_ips = socket.gethostbyname_ex(hostname)[2]
        ips.extend([ip for ip in host_ips if not ip.startswith("127.")])
    except Exception:
        pass
    
    # Try to get the primary IP
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        primary_ip = s.getsockname()[0]
        s.close()
        if primary_ip not in ips:
            ips.insert(0, primary_ip)
    except Exception:
        pass
    
    return ips

def get_network_interfaces():
    """Get network interface information (Windows)"""
    if sys.platform != 'win32':
        return []
    
    try:
        import subprocess
        result = subprocess.run(['ipconfig'], capture_output=True, text=True)
        output = result.stdout
        
        interfaces = []
        current_interface = None
        
        for line in output.split('\n'):
            line = line.strip()
            if line and not line.startswith(' '):
                current_interface = line.rstrip(':')
            elif 'IPv4 Address' in line and current_interface:
                ip = line.split(':')[1].strip()
                if not ip.startswith('127.'):
                    interfaces.append({
                        'name': current_interface,
                        'ip': ip
                    })
        
        return interfaces
    except Exception:
        return []

def print_banner():
    """Print application banner"""
    print("=" * 70)
    print(" " * 15 + "ATTENDANCE MONITOR - Network Access")
    print("=" * 70)
    print()

def print_connection_info(port=8000):
    """Print all available connection URLs"""
    print_banner()
    
    print("📡 SERVER ACCESS POINTS")
    print("-" * 70)
    print()
    
    # Local access
    print("🏠 Local Access (This Computer):")
    print(f"   • http://localhost:{port}")
    print(f"   • http://127.0.0.1:{port}")
    print()
    
    # Network access
    local_ips = get_local_ips()
    if local_ips:
        print("🌐 Network Access (Other Devices on Same Network):")
        for ip in local_ips:
            print(f"   • http://{ip}:{port}")
        print()
    
    # Configured hosts
    print("🔧 Pre-configured Hosts:")
    print(f"   • http://attendance-monitor.local:{port}")
    print(f"   • http://10.251.88.18:{port}")
    print()
    
    # Network interfaces (Windows)
    if sys.platform == 'win32':
        interfaces = get_network_interfaces()
        if interfaces:
            print("🔌 Network Interfaces:")
            for interface in interfaces:
                print(f"   • {interface['name']}: http://{interface['ip']}:{port}")
            print()
    
    print("-" * 70)
    print()
    print("📱 To access from mobile/tablet:")
    print("   1. Connect to the same WiFi network")
    print("   2. Open browser and enter one of the network URLs above")
    print("   3. Make sure Windows Firewall allows port", port)
    print()
    print("🔥 Firewall Configuration:")
    print("   Run as Administrator:")
    print(f'   netsh advfirewall firewall add rule name="Django Server" dir=in action=allow protocol=TCP localport={port}')
    print()
    print("=" * 70)

def check_port_available(port=8000):
    """Check if port is available"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('localhost', port))
        sock.close()
        return result != 0
    except Exception:
        return True

def main():
    """Main function"""
    port = 8000
    
    # Check for custom port argument
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print("Error: Invalid port number")
            sys.exit(1)
    
    print_connection_info(port)
    
    # Check if port is in use
    if not check_port_available(port):
        print(f"⚠️  WARNING: Port {port} appears to be in use!")
        print(f"   The server might already be running, or another application is using port {port}")
        print()
    else:
        print(f"✅ Port {port} is available")
        print()
        print("💡 To start the server:")
        print(f"   python manage.py runserver 0.0.0.0:{port}")
        print("   or use: run_server_multi_host.bat")
        print()

if __name__ == "__main__":
    main()
