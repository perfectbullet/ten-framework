#!/bin/bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$PROJECT_ROOT/logs"
PID_FILE="$LOG_DIR/app.pid"

echo "========================================="
echo "Stopping RAG Retrieval Demo"
echo "========================================="

if [ -f "$PID_FILE" ]; then
    APP_PID=$(cat "$PID_FILE")
    if ps -p $APP_PID > /dev/null; then
        echo "Stopping application (PID: $APP_PID)..."
        kill $APP_PID
        sleep 2
        
        if ps -p $APP_PID > /dev/null; then
            echo "Force killing application..."
            kill -9 $APP_PID
        fi
        
        rm -f "$PID_FILE"
        echo "Application stopped successfully!"
    else
        echo "Application is not running (stale PID file)"
        rm -f "$PID_FILE"
    fi
else
    echo "PID file not found. Application may not be running."
fi

echo "========================================="