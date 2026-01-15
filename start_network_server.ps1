# Enhanced Network Server Configuration and Launch
# PowerShell script for easy multi-host server deployment

Write-Host "======================================" -ForegroundColor Cyan
Write-Host " Attendance Monitor - Network Setup  " -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Function to get local IP
function Get-LocalIPAddress {
    try {
        $ipAddresses = Get-NetIPAddress -AddressFamily IPv4 | 
            Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*" }
        
        if ($ipAddresses) {
            return $ipAddresses[0].IPAddress
        }
    }
    catch {
        return $null
    }
    return $null
}

# Get local IP
Write-Host "[*] Detecting network configuration..." -ForegroundColor Yellow
$localIP = Get-LocalIPAddress

Write-Host ""
Write-Host "[+] Server Access Points:" -ForegroundColor Green
Write-Host "    Local Access:" -ForegroundColor White
Write-Host "      - http://localhost:8000" -ForegroundColor Gray
Write-Host "      - http://127.0.0.1:8000" -ForegroundColor Gray

if ($localIP) {
    Write-Host ""
    Write-Host "    Network Access (Other Devices):" -ForegroundColor White
    Write-Host "      - http://${localIP}:8000" -ForegroundColor Yellow -BackgroundColor DarkBlue
    Write-Host "        ^ Use this URL on your phone/tablet!" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "    Pre-configured Hosts:" -ForegroundColor White
Write-Host "      - http://attendance-monitor.local:8000" -ForegroundColor Gray
Write-Host "      - http://10.251.88.18:8000" -ForegroundColor Gray

# Check if port is available
Write-Host ""
Write-Host "[*] Checking port 8000..." -ForegroundColor Yellow
$portInUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue

if ($portInUse) {
    Write-Host "[!] ERROR: Port 8000 is already in use!" -ForegroundColor Red
    Write-Host "    Process ID: $($portInUse.OwningProcess)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Options:" -ForegroundColor Cyan
    Write-Host "  1. Stop the process using the port" -ForegroundColor White
    Write-Host "  2. Use a different port: python manage.py runserver 0.0.0.0:3000" -ForegroundColor White
    Write-Host ""
    pause
    exit 1
}

Write-Host "[+] Port 8000 is available" -ForegroundColor Green

# Check firewall
Write-Host ""
Write-Host "[*] Checking Windows Firewall..." -ForegroundColor Yellow

$firewallRule = Get-NetFirewallRule -DisplayName "Django Server" -ErrorAction SilentlyContinue

if (-not $firewallRule) {
    Write-Host "[!] Firewall rule not found!" -ForegroundColor Yellow
    Write-Host ""
    $response = Read-Host "Do you want to add a firewall rule? (Requires Admin) [Y/N]"
    
    if ($response -eq 'Y' -or $response -eq 'y') {
        Write-Host "[*] Adding firewall rule..." -ForegroundColor Yellow
        
        try {
            # Check if running as admin
            $currentPrincipal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
            $isAdmin = $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
            
            if ($isAdmin) {
                New-NetFirewallRule -DisplayName "Django Server" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow | Out-Null
                Write-Host "[+] Firewall rule added successfully!" -ForegroundColor Green
            }
            else {
                Write-Host "[!] Please run PowerShell as Administrator to add firewall rule" -ForegroundColor Red
                Write-Host ""
                Write-Host "Run this command as Administrator:" -ForegroundColor Cyan
                Write-Host 'New-NetFirewallRule -DisplayName "Django Server" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow' -ForegroundColor Yellow
            }
        }
        catch {
            Write-Host "[!] Failed to add firewall rule: $_" -ForegroundColor Red
        }
    }
}
else {
    Write-Host "[+] Firewall rule exists" -ForegroundColor Green
}

# Display connection instructions
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "📱 To access from mobile/tablet:" -ForegroundColor Cyan
Write-Host "   1. Connect to the same WiFi" -ForegroundColor White
Write-Host "   2. Open browser" -ForegroundColor White
if ($localIP) {
    Write-Host "   3. Go to: http://${localIP}:8000" -ForegroundColor Yellow
}
Write-Host ""

# Start server
Write-Host "[*] Starting Django server..." -ForegroundColor Yellow
Write-Host "[*] Press CTRL+C to stop" -ForegroundColor Yellow
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# Run the server
python manage.py runserver 0.0.0.0:8000

# Server stopped
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " Server Stopped " -ForegroundColor Red
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""
pause
