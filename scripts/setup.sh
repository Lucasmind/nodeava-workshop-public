#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== NodeAva Setup ==="
echo ""

# 1. Validate Docker
if ! command -v docker &>/dev/null; then
  echo "ERROR: Docker is not installed."
  echo "Install Docker: https://docs.docker.com/get-docker/"
  exit 1
fi

if ! docker compose version &>/dev/null; then
  echo "ERROR: Docker Compose V2 is not available."
  echo "Update Docker or install the compose plugin."
  exit 1
fi
echo "Docker: OK"

# 2. Detect GPU and VRAM
echo ""
echo "--- GPU Detection ---"
GPU_INFO=$("$SCRIPT_DIR/detect-gpu.sh" --vram)
GPU_TYPE=$(echo "$GPU_INFO" | awk '{print $1}')
VRAM_MB=$(echo "$GPU_INFO" | awk '{print $2}')

if [ "$GPU_TYPE" = "none" ]; then
  echo "ERROR: No supported GPU detected."
  echo "NodeAva requires an NVIDIA or AMD GPU with at least 8 GB VRAM."
  exit 1
fi

echo "Detected GPU: $GPU_TYPE"
if [ "$VRAM_MB" -gt 0 ] 2>/dev/null; then
  VRAM_GB=$(( VRAM_MB / 1024 ))
  echo "VRAM: ${VRAM_MB} MB (~${VRAM_GB} GB)"
  if [ "$VRAM_MB" -lt 7500 ]; then
    echo ""
    echo "WARNING: Less than 8 GB VRAM detected."
    echo "NodeAva needs ~4.8 GB VRAM. You may experience issues."
    echo ""
  fi
else
  echo "VRAM: could not detect (will check at runtime)"
fi
echo ""

# 3. Download LLM model
echo "--- Model Download ---"
"$SCRIPT_DIR/download-model.sh"
echo ""

# 4. Create .env
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "Creating .env from .env.example..."
  cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
  sed -i "s/^GPU_TYPE=.*/GPU_TYPE=$GPU_TYPE/" "$ENV_FILE"
  echo ".env created with GPU_TYPE=$GPU_TYPE"
else
  echo ".env already exists (GPU_TYPE not modified)"
fi
echo ""

# 5. Create models directory
mkdir -p "$PROJECT_DIR/models"

# 6. Check for avatar model
AVATAR_PATH="$PROJECT_DIR/frontend/public/avatars/default-avatar.glb"
if [ ! -f "$AVATAR_PATH" ]; then
  echo "--- Avatar Required ---"
  echo "No avatar model found at: frontend/public/avatars/default-avatar.glb"
  echo ""
  echo "You need a GLB avatar with ARKit blend shapes and Oculus Visemes."
  echo "The easiest way:"
  echo "  1. Download VRoid Studio from https://vroid.com/en/studio (free)"
  echo "  2. Create a character"
  echo "  3. Export as VRM (TalkingHead supports VRM natively)"
  echo "  4. Save as frontend/public/avatars/default-avatar.glb"
  echo ""
  echo "See frontend/public/avatars/README.md for more options."
  echo ""
fi

# 7. Determine compose command
COMPOSE_CMD="docker compose -f docker-compose.yml"
case "$GPU_TYPE" in
  nvidia)
    COMPOSE_CMD="$COMPOSE_CMD -f docker-compose.gpu-nvidia.yml"
    echo "GPU profile: NVIDIA (CUDA)"
    ;;
  amd)
    COMPOSE_CMD="$COMPOSE_CMD -f docker-compose.gpu-amd.yml"
    echo "GPU profile: AMD (Vulkan + ROCm)"
    echo ""
    echo "NOTE: First build will take ~20-30 minutes to compile the ROCm TTS image."
    echo "Subsequent builds use the Docker cache and are fast."
    ;;
esac
echo ""

echo "=== Setup Complete ==="
echo ""
echo "To start NodeAva:"
echo "  cd $PROJECT_DIR"
echo "  $COMPOSE_CMD up --build"
echo ""
echo "Then open http://localhost:3000 in your browser."
