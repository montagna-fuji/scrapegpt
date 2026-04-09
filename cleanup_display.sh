#!/bin/bash
# Simple cleanup script for lingering VNC/WebSocket/browser processes

echo "Cleaning up previous VNC/WebSocket sessions..."

# Kill x11vnc instances
pkill -f x11vnc && echo "Killed x11vnc"

# Kill leftover Xvfb processes
pkill -f Xvfb 2>/dev/null

# Kill websockify instances
pkill -f websockify && echo "Killed websockify"

# Optionally, kill browsers launched by the script
# Comment out if you want to keep your normal browser
pkill -f "firefox.*127.0.0.1:6080" && echo "Killed Firefox kiosk/browser instances"
pkill -f "chromium.*127.0.0.1:6080" && echo "Killed Chromium kiosk/browser instances"

# Release VNC ports (5900-5905) and WebSocket port 6080
# This finds any process still holding the port and kills it
for PORT in 5900 5901 5902 5903 5904 5905 6080; do
    PID=$(lsof -t -i:$PORT)
    if [ ! -z "$PID" ]; then
        kill -9 $PID
        echo "Killed process $PID on port $PORT"
    fi
done

echo "Cleanup complete."