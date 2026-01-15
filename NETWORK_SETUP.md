# Network Configuration Guide

## Multi-Host Server Access

This system is configured to allow easy access from multiple devices on your network.

### Automatic Host Detection

The server automatically detects and configures the following access points:

1. **Localhost Access**
   - http://localhost:8000
   - http://127.0.0.1:8000

2. **Local Network Access**
   - Automatically detects your local IP (e.g., http://192.168.x.x:8000)
   - Use this to access from other devices on the same network

3. **Custom Hostname**
   - http://attendance-monitor.local:8000
   - Configured static IP: http://10.251.88.18:8000

### How to Access from Other Devices

#### On the Same Network (WiFi/LAN)

1. **Find Your Server IP**
   - Run the server and check the console output
   - Or run: `ipconfig` (Windows) or `ifconfig` (Linux/Mac)
   - Look for IPv4 Address (usually starts with 192.168 or 10.x)

2. **Access from Mobile/Tablet/Other PC**
   - Open browser on the device
   - Enter: `http://YOUR-SERVER-IP:8000`
   - Example: `http://192.168.1.100:8000`

3. **Make Sure**
   - Both devices are on the same network
   - Firewall allows port 8000 (see below)
   - Server is running

### Firewall Configuration (Windows)

To allow other devices to connect, configure Windows Firewall:

```powershell
# Run PowerShell as Administrator
netsh advfirewall firewall add rule name="Django Server" dir=in action=allow protocol=TCP localport=8000
```

Or manually:
1. Open Windows Defender Firewall
2. Click "Advanced settings"
3. Click "Inbound Rules" → "New Rule"
4. Select "Port" → Next
5. Enter port 8000 → Next
6. Allow the connection → Next
7. Apply to all profiles → Next
8. Name it "Django Server" → Finish

### Production Deployment Options

#### Option 1: Using a Reverse Proxy (Recommended)

Set up nginx or Apache as a reverse proxy:
- Handles SSL/HTTPS
- Better performance
- Professional setup

#### Option 2: Cloud Hosting

Deploy to:
- Heroku
- PythonAnywhere
- DigitalOcean
- AWS/Azure/GCP

#### Option 3: Local Server with Dynamic DNS

Use services like:
- No-IP
- DuckDNS
- Dynu

### Environment Variables for Additional Hosts

Add more allowed hosts without editing code:

**Windows:**
```powershell
$env:ADDITIONAL_HOSTS="mydomain.com,subdomain.example.com"
python manage.py runserver 0.0.0.0:8000
```

**Linux/Mac:**
```bash
export ADDITIONAL_HOSTS="mydomain.com,subdomain.example.com"
python manage.py runserver 0.0.0.0:8000
```

### Performance Optimizations Enabled

✅ **Connection Pooling** - Reuses database connections for 10 minutes
✅ **Keep-Alive** - Persistent HTTP connections
✅ **GZip Compression** - Reduces data transfer by ~70%
✅ **Static File Caching** - Faster page loads
✅ **WAL Mode Database** - Better concurrent access
✅ **Response Compression** - Optimized for mobile networks

### Testing Network Access

1. **Start the server:**
   ```bash
   python manage.py runserver 0.0.0.0:8000
   ```

2. **Check local IP:**
   ```bash
   # Windows PowerShell
   Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*"}
   
   # Or simple command
   ipconfig
   ```

3. **Test from another device:**
   - Connect to same WiFi
   - Open browser
   - Go to `http://YOUR-IP:8000`

### Troubleshooting

**Can't connect from other devices?**
- ✓ Check firewall settings
- ✓ Verify both devices on same network
- ✓ Use `0.0.0.0:8000` when starting server
- ✓ Check if antivirus is blocking connections

**Slow performance?**
- ✓ Enable GZip compression (already configured)
- ✓ Use static file caching (already configured)
- ✓ Consider upgrading to production server (Gunicorn)

**Connection timeout?**
- ✓ Increase timeout in settings (already set to 30s)
- ✓ Check network stability
- ✓ Reduce concurrent requests

### Quick Start Commands

**Run server accessible to all network devices:**
```bash
python manage.py runserver 0.0.0.0:8000
```

**Run with custom port:**
```bash
python manage.py runserver 0.0.0.0:3000
```

**Run optimized server (production-like):**
```bash
.\run_server_optimized.bat
```

### Security Notes

⚠️ **For Production:**
- Set `DEBUG = False` in settings
- Remove `'*'` from `ALLOWED_HOSTS`
- Use environment variables for secrets
- Enable HTTPS/SSL
- Use a production WSGI server (Gunicorn, uWSGI)
- Configure proper firewall rules
