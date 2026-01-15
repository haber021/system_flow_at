@echo off
REM Enhanced Multi-Host Server Startup Script
REM Configures and starts the Django server with network access

echo ========================================
echo  Attendance Monitor - Multi-Host Server
echo ========================================
echo.

REM Get local IP address
echo [*] Detecting network configuration...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4 Address"') do (
    set LOCAL_IP=%%a
    goto :found_ip
)
:found_ip
set LOCAL_IP=%LOCAL_IP: =%

echo.
echo [+] Server will be accessible at:
echo     - http://localhost:8000
echo     - http://127.0.0.1:8000
if defined LOCAL_IP (
    echo     - http://%LOCAL_IP%:8000 [Network Access]
)
echo     - http://attendance-monitor.local:8000 [Custom Domain]
echo     - http://10.251.88.18:8000 [Static IP]
echo.

REM Check if port is already in use
echo [*] Checking if port 8000 is available...
netstat -ano | findstr :8000 >nul
if %errorlevel% equ 0 (
    echo [!] WARNING: Port 8000 is already in use!
    echo [!] Please close other applications using this port or use a different port.
    pause
    exit /b 1
)

echo [+] Port 8000 is available
echo.

REM Check firewall configuration
echo [*] Checking Windows Firewall...
netsh advfirewall firewall show rule name="Django Server" >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Firewall rule not found!
    echo [?] Do you want to add a firewall rule to allow network access?
    echo     (Requires Administrator privileges)
    choice /C YN /M "Add firewall rule"
    if errorlevel 2 goto skip_firewall
    if errorlevel 1 (
        echo [*] Adding firewall rule...
        powershell -Command "Start-Process netsh -ArgumentList 'advfirewall firewall add rule name=\"Django Server\" dir=in action=allow protocol=TCP localport=8000' -Verb RunAs"
        echo [+] Firewall rule added!
    )
) else (
    echo [+] Firewall rule exists
)
:skip_firewall

echo.
echo [*] Starting Django development server...
echo [*] Press CTRL+C to stop the server
echo.
echo ========================================
echo.

REM Start the server on all interfaces
python manage.py runserver 0.0.0.0:8000

REM If server stopped
echo.
echo ========================================
echo Server stopped.
echo ========================================
pause
