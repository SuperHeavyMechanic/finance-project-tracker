#!/bin/bash
# Double-click entry point: starts the Flask server if it isn't already
# running, then opens the browser. Safe to run repeatedly.
cd "$(dirname "$0")"
export PATH="$HOME/Library/Python/3.9/bin:$PATH"

if ! lsof -i :8080 -sTCP:LISTEN >/dev/null 2>&1; then
  nohup python3 app.py > /tmp/finance-tracker.log 2>&1 &
  disown
  sleep 1.5
fi

open http://localhost:8080
