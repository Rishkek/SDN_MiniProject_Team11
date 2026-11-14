@echo off
title SDN High-Priority Demo Launcher
echo ============================================================
echo   SDN PROJECT: HIGH-PRIORITY DEMO LAUNCHER (WINDOWS / WSL)
echo ============================================================
echo [*] Setting Remote Desktop client framerate to 60 FPS...
reg add "HKCU\Software\Microsoft\Terminal Server Client" /v RemoteDesktopFrameRate /t REG_DWORD /d 60 /f >nul 2>&1

echo [*] Elevating msrdc (Remote Desktop) priority to High...
powershell -Command "Get-Process -Name msrdc -ErrorAction SilentlyContinue | ForEach-Object { $_.PriorityClass = 'High' }" >nul 2>&1

echo [*] Launching Python with High Priority Class...
start /high py -3 run.py %*
echo [+] Done!
