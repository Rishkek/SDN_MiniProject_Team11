#!/usr/bin/env bash
# ============================================================
#   SDN PROJECT: HIGH-PRIORITY DEMO LAUNCHER (LINUX / WSL)
# ============================================================

echo "[*] Setting maximum CPU priority and I/O scheduling..."
# Try to elevate scheduling priority to -10 if sudo is available
sudo renice -n -10 $$ 2>/dev/null || renice -n -5 $$ 2>/dev/null
sudo ionice -c 2 -n 0 -p $$ 2>/dev/null

# Configure Qt environment for smooth rendering over Remote Desktop / WSLg
export QSG_RENDER_LOOP=basic
export QT_AUTO_SCREEN_SCALE_FACTOR=1

if [ -n "$DISPLAY" ]; then
    export QT_QPA_PLATFORM=xcb
fi

echo "[+] Launching SDN GUI Dashboard..."
exec python3 run.py "$@"
