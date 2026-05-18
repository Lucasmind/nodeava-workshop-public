#!/bin/bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
MODEL_NAME="${WHISPER_MODEL:-base.en}"
MODEL_FILE="ggml-${MODEL_NAME}.bin"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE}"
PORT="${STT_PORT:-8080}"

echo "=== Digital Avatar STT Service ==="
echo "Model: ${MODEL_NAME}"
echo "Port: ${PORT}"

# GPU detection
echo "--- GPU Detection ---"
if command -v vulkaninfo &>/dev/null; then
  GPU_NAME=$(vulkaninfo --summary 2>/dev/null | grep "deviceName" | head -1 | sed 's/.*= //' || echo "unknown")
  echo "Vulkan GPU: ${GPU_NAME}"
else
  echo "No Vulkan detected, using CPU"
fi

# Download model if not present
if [ ! -f "$MODEL_PATH" ]; then
  echo "Model not found, downloading..."
  /app/download-model.sh
fi

echo "Starting whisper-server on port ${PORT}..."

exec whisper-server \
  --model "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --inference-path /v1/audio/transcriptions \
  --convert
