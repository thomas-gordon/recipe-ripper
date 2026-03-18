#!/bin/bash
# ============================================================
#  Recipe PDF Server — macOS Launch Agent installer
#  Run this once to make the server start automatically
#  every time you log in to your Mac.
#
#  Usage:
#    chmod +x install_service.sh
#    ./install_service.sh
# ============================================================

set -e

PLIST_LABEL="com.recipe.pdfserver"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"

# ── 1. Find this script's own directory (where server.py lives) ──────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="$SCRIPT_DIR/server.py"

if [ ! -f "$SERVER_PY" ]; then
  echo "Error: server.py not found in $SCRIPT_DIR"
  echo "Make sure you run this script from the same folder as server.py."
  exit 1
fi

# ── 2. Find Python 3 ─────────────────────────────────────────────────────────
PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
if [ -z "$PYTHON" ]; then
  echo "Error: Python 3 not found. Install it from https://brew.sh or python.org"
  exit 1
fi

PYTHON_VERSION=$("$PYTHON" --version 2>&1)
echo "Using Python: $PYTHON ($PYTHON_VERSION)"
echo "Server path:  $SERVER_PY"

# ── 3. Install dependencies from requirements.txt ────────────────────────────
REQUIREMENTS="$SCRIPT_DIR/requirements.txt"
if [ -f "$REQUIREMENTS" ]; then
  echo "Installing dependencies from requirements.txt..."
  "$PYTHON" -m pip install -r "$REQUIREMENTS" --quiet
else
  echo "Warning: requirements.txt not found, installing Flask only..."
  "$PYTHON" -m pip install flask flask-cors --quiet
fi

# ── 4. Create log directory ───────────────────────────────────────────────────
LOG_DIR="$HOME/Library/Logs/RecipePDFServer"
mkdir -p "$LOG_DIR"

# ── 5. Write the launchd plist ────────────────────────────────────────────────
cat > "$PLIST_PATH" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>${PYTHON}</string>
    <string>${SERVER_PY}</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${SCRIPT_DIR}</string>

  <!-- Start automatically when you log in -->
  <key>RunAtLoad</key>
  <true/>

  <!-- Restart automatically if it crashes -->
  <key>KeepAlive</key>
  <true/>

  <!-- Logs (viewable in Console.app or with: tail -f ~/Library/Logs/RecipePDFServer/server.log) -->
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/server.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/server.error.log</string>

  <!-- Throttle rapid restarts -->
  <key>ThrottleInterval</key>
  <integer>10</integer>
</dict>
</plist>
EOF

echo "Plist written to: $PLIST_PATH"

# ── 6. Load the agent (starts it immediately without needing a reboot) ────────
# Unload first in case an old version is already registered
launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"

echo ""
echo "  ✓ Recipe PDF server installed as a login item."
echo "  ✓ Server is running now on http://localhost:5050"
echo ""
echo "  Useful commands:"
echo "    Stop:    launchctl unload ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo "    Start:   launchctl load   ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo "    Logs:    tail -f ~/Library/Logs/RecipePDFServer/server.log"
echo "    Remove:  launchctl unload ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo "             rm ~/Library/LaunchAgents/${PLIST_LABEL}.plist"
echo ""
