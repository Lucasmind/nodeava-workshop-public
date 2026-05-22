#!/bin/bash
# Start all NodeAva services natively on macOS (Apple Silicon)
# Uses Metal for llama.cpp/whisper.cpp, MPS for Kokoro-FastAPI
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KOKORO_DIR="$HOME/.nodeava/kokoro-fastapi"
PID_DIR="$PROJECT_DIR/.pids"

# Ports (match Docker setup)
LLM_PORT=8081
STT_PORT=8080
TTS_PORT=8880
FRONTEND_PORT=3000

# Model paths (Whisper only; LLM now via Ollama on port 11434)
WHISPER_MODEL="$PROJECT_DIR/models/ggml-base.en.bin"
OLLAMA_PORT=11434

echo "=== NodeAva macOS Start ==="
echo ""

# Verify Whisper model exists
if [ ! -f "$WHISPER_MODEL" ]; then
  echo "ERROR: Whisper model not found: $WHISPER_MODEL"
  echo "Run ./scripts/setup-mac.sh first."
  exit 1
fi
if [ ! -d "$KOKORO_DIR" ]; then
  echo "ERROR: Kokoro-FastAPI not found: $KOKORO_DIR"
  echo "Run ./scripts/setup-mac.sh first."
  exit 1
fi

# Check for existing processes
if [ -d "$PID_DIR" ] && ls "$PID_DIR"/*.pid &>/dev/null; then
  echo "WARNING: NodeAva may already be running."
  echo "Run ./scripts/stop-mac.sh first, or check the processes."
  echo ""
fi

# Create PID and log directories
mkdir -p "$PID_DIR"
mkdir -p "$PROJECT_DIR/logs"

# Cleanup function — kill all child processes on exit
cleanup() {
  echo ""
  echo "Stopping NodeAva..."
  for pidfile in "$PID_DIR"/*.pid; do
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile")
      name=$(basename "$pidfile" .pid)
      if kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
        echo "  Stopped $name (PID $pid)"
      fi
      rm -f "$pidfile"
    fi
  done
  # Kill any remaining children
  wait 2>/dev/null || true
  echo "All services stopped."
}
trap cleanup EXIT INT TERM

# --- Ollama (Plan #7) ---
echo "Checking Ollama on port $OLLAMA_PORT..."
if ! curl -fsS http://localhost:$OLLAMA_PORT/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama..."
  (ollama serve >/tmp/ollama.log 2>&1 &)
  for i in $(seq 1 10); do
    if curl -fsS http://localhost:$OLLAMA_PORT/api/tags >/dev/null 2>&1; then break; fi
    sleep 1
  done
fi
if curl -fsS http://localhost:$OLLAMA_PORT/api/tags >/dev/null 2>&1; then
  echo "  Ollama is up (port $OLLAMA_PORT)"
else
  echo "ERROR: Ollama is not reachable at http://localhost:$OLLAMA_PORT"
  echo "Start it manually: ollama serve"
  exit 1
fi

# --- Start STT (whisper-server with Metal) ---
echo "Starting STT (whisper-server, port $STT_PORT)..."
whisper-server \
  --model "$WHISPER_MODEL" \
  --host 0.0.0.0 --port "$STT_PORT" \
  --inference-path /v1/audio/transcriptions \
  --convert \
  > "$PROJECT_DIR/logs/stt.log" 2>&1 &
STT_PID=$!
echo "$STT_PID" > "$PID_DIR/stt.pid"
echo "  STT started (PID $STT_PID)"

# --- Start TTS (Kokoro-FastAPI with MPS) ---
echo "Starting TTS (Kokoro-FastAPI, port $TTS_PORT)..."
cd "$KOKORO_DIR"
USE_GPU=true DEVICE_TYPE=mps PYTORCH_ENABLE_MPS_FALLBACK=1 \
  MODEL_DIR="$KOKORO_DIR/api/src/models" \
  VOICES_DIR="$KOKORO_DIR/api/src/voices/v1_0" \
  uv run python -m api.src.main \
  --host 0.0.0.0 --port "$TTS_PORT" \
  > "$PROJECT_DIR/logs/tts.log" 2>&1 &
TTS_PID=$!
echo "$TTS_PID" > "$PID_DIR/tts.pid"
echo "  TTS started (PID $TTS_PID)"
cd "$PROJECT_DIR"

# --- Start Frontend (Vite dev server) ---
echo "Starting Frontend (Vite dev, port $FRONTEND_PORT)..."
cd "$PROJECT_DIR/frontend"
npm run dev > "$PROJECT_DIR/logs/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$PID_DIR/frontend.pid"
echo "  Frontend started (PID $FRONTEND_PID)"
cd "$PROJECT_DIR"

echo ""
echo "=== NodeAva Running ==="
echo ""
echo "  Frontend:  http://localhost:$FRONTEND_PORT"
echo "  LLM API:   http://localhost:$OLLAMA_PORT (Ollama)"
echo "  TTS API:   http://localhost:$TTS_PORT"
echo "  STT API:   http://localhost:$STT_PORT"
echo ""
echo "  Logs:      $PROJECT_DIR/logs/"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Wait for any child to exit — if one dies, report it
while true; do
  for service in stt tts frontend; do
    pidfile="$PID_DIR/$service.pid"
    if [ -f "$pidfile" ]; then
      pid=$(cat "$pidfile")
      if ! kill -0 "$pid" 2>/dev/null; then
        echo "WARNING: $service (PID $pid) exited unexpectedly. Check logs/$service.log"
        rm -f "$pidfile"
      fi
    fi
  done
  sleep 5
done
