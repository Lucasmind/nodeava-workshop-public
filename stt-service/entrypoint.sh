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

# GPU mode selection.
# whisper-server in the upstream :main-vulkan image auto-detects Vulkan
# devices and uses them — regardless of what this script prints. The old
# `vulkaninfo` check was informational only and didn't actually disable GPU.
#
# Blackwell GPUs (sm_120 / RTX 50-series / RTX PRO Blackwell) crash
# whisper.cpp's Vulkan compute shaders during inference (exit 132). Set
# USE_GPU=0 in the environment (via docker-compose) to pass --no-gpu to
# whisper-server and force CPU. install.sh's 08-up-stack.sh auto-sets this
# in docker-compose.blackwell-tts.yml when a Blackwell GPU is detected.
echo "--- GPU mode ---"
WHISPER_GPU_ARGS=""
if [[ "${USE_GPU:-1}" = "0" ]]; then
  # On CPU, also disable flash attention. As of mid-May 2026 the upstream
  # ghcr.io/ggml-org/whisper.cpp:main-vulkan image's whisper-server crashes
  # within 0.2 s of startup with exit 132 (SIGILL) when flash-attn is on but
  # no usable GPU is present. Was fine on earlier builds — the :main tag is
  # moving. `--no-flash-attn` keeps it on the safe path.
  echo "USE_GPU=0 — forcing CPU (--no-gpu --no-flash-attn)"
  WHISPER_GPU_ARGS="--no-gpu --no-flash-attn"
elif command -v vulkaninfo &>/dev/null; then
  GPU_NAME=$(vulkaninfo --summary 2>/dev/null | grep "deviceName" | head -1 | sed 's/.*= //' || echo "unknown")
  echo "Vulkan GPU: ${GPU_NAME}"
else
  echo "vulkaninfo not in image (this is normal); whisper-server will auto-detect Vulkan at runtime"
fi

# Download model if not present
if [ ! -f "$MODEL_PATH" ]; then
  echo "Model not found, downloading..."
  /app/download-model.sh
fi

echo "Starting whisper-server on port ${PORT}..."

# shellcheck disable=SC2086
exec whisper-server $WHISPER_GPU_ARGS \
  --model "$MODEL_PATH" \
  --host 0.0.0.0 \
  --port "$PORT" \
  --inference-path /v1/audio/transcriptions \
  --convert
