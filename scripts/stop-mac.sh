#!/bin/bash
# Stop all NodeAva services on macOS
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_DIR="$PROJECT_DIR/.pids"

echo "=== Stopping NodeAva ==="
echo ""

stopped=0

# Stop by PID file
if [ -d "$PID_DIR" ]; then
  for pidfile in "$PID_DIR"/*.pid; do
    [ -f "$pidfile" ] || continue
    pid=$(cat "$pidfile")
    name=$(basename "$pidfile" .pid)
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "Stopped $name (PID $pid)"
      stopped=$((stopped + 1))
    else
      echo "Already stopped: $name (PID $pid)"
    fi
    rm -f "$pidfile"
  done
fi

if [ "$stopped" -eq 0 ]; then
  echo "No running NodeAva services found via PID files."
  echo ""
  echo "If processes are still running, you can stop them manually:"
  echo "  pkill -f whisper-server"
  echo "  pkill -f 'api.src.main'"
  echo "  pkill -f 'vite'"
  echo ""
  echo "Note: Ollama (LLM service) is left running — it's a host service"
  echo "that may be used by other applications."
else
  echo ""
  echo "Stopped $stopped service(s)."
  echo ""
  echo "Note: Ollama (LLM service) is left running — it's a host service"
  echo "that may be used by other applications."
fi
