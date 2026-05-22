#!/bin/bash
# NodeAva macOS (Apple Silicon) setup script
# Installs native services for Metal/MPS GPU acceleration
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
KOKORO_DIR="$HOME/.nodeava/kokoro-fastapi"
KOKORO_VERSION="v0.2.4"

echo "=== NodeAva macOS Setup ==="
echo ""

# 1. Verify macOS + Apple Silicon
if [ "$(uname)" != "Darwin" ]; then
  echo "ERROR: This script is for macOS only."
  echo "On Linux, use: ./scripts/setup.sh"
  exit 1
fi

ARCH=$(uname -m)
if [ "$ARCH" != "arm64" ]; then
  echo "ERROR: Apple Silicon (arm64) required. Detected: $ARCH"
  echo "Intel Macs are not supported — Metal compute is needed for ML inference."
  exit 1
fi

echo "Platform: macOS $(sw_vers -productVersion) on Apple Silicon"

# Check memory
MEM_GB=$(( $(sysctl -n hw.memsize) / 1024 / 1024 / 1024 ))
echo "Unified memory: ${MEM_GB} GB"
if [ "$MEM_GB" -lt 12 ]; then
  echo ""
  echo "WARNING: 16 GB unified memory recommended."
  echo "NodeAva needs ~4.8 GB for GPU inference. With ${MEM_GB} GB total, headroom is tight."
  echo ""
fi

# 2. Xcode Command Line Tools
echo ""
echo "--- Xcode Command Line Tools ---"
if xcode-select -p &>/dev/null; then
  echo "Xcode CLT: OK"
else
  echo "Installing Xcode Command Line Tools..."
  xcode-select --install
  echo "Please complete the installation dialog, then re-run this script."
  exit 0
fi

# 3. Homebrew
echo ""
echo "--- Homebrew ---"
if command -v brew &>/dev/null; then
  echo "Homebrew: OK"
else
  echo "Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Add to PATH for this session
  eval "$(/opt/homebrew/bin/brew shellenv)"
  echo "Homebrew: installed"
fi

# 4. Ollama (replaces llama.cpp as of Plan #7)
echo ""
echo "--- Ollama ---"
if command -v ollama >/dev/null 2>&1; then
  echo "Ollama: OK ($(ollama --version))"
else
  echo "Installing Ollama via Homebrew..."
  brew install ollama
  echo "Ollama: installed"
fi

# 5. whisper.cpp (provides whisper-server with Metal)
echo ""
echo "--- whisper.cpp ---"
if command -v whisper-server &>/dev/null; then
  echo "whisper-server: OK"
else
  echo "Installing whisper-cpp..."
  brew install whisper-cpp
  echo "whisper-server: installed"
fi

# 6. Python and uv
echo ""
echo "--- Python + uv ---"
if command -v python3 &>/dev/null; then
  PY_VER=$(python3 --version 2>&1 | awk '{print $2}')
  PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
  PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
  if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
    echo "Python: OK ($PY_VER)"
  else
    echo "ERROR: Python 3.10+ required. Found: $PY_VER"
    echo "Install with: brew install python@3.12"
    exit 1
  fi
else
  echo "ERROR: Python 3 not found."
  echo "Install with: brew install python@3.12"
  exit 1
fi

if command -v uv &>/dev/null; then
  echo "uv: OK"
else
  echo "Installing uv..."
  brew install uv
  echo "uv: installed"
fi

# 7. Node.js
echo ""
echo "--- Node.js ---"
if command -v node &>/dev/null; then
  NODE_VER=$(node --version)
  echo "Node.js: OK ($NODE_VER)"
else
  echo "ERROR: Node.js not found."
  echo "Install with: brew install node"
  exit 1
fi

# 8. Kokoro-FastAPI (TTS)
echo ""
echo "--- Kokoro-FastAPI (TTS) ---"
if [ -d "$KOKORO_DIR" ] && [ -f "$KOKORO_DIR/pyproject.toml" ]; then
  echo "Kokoro-FastAPI: OK ($KOKORO_DIR)"
else
  echo "Cloning Kokoro-FastAPI ${KOKORO_VERSION}..."
  mkdir -p "$(dirname "$KOKORO_DIR")"
  git clone --branch "$KOKORO_VERSION" --depth 1 \
    https://github.com/remsky/Kokoro-FastAPI.git "$KOKORO_DIR"
  echo "Kokoro-FastAPI: cloned"
fi

echo "Installing Kokoro-FastAPI dependencies (this may take a few minutes)..."
cd "$KOKORO_DIR"
uv sync
cd "$PROJECT_DIR"
echo "Kokoro-FastAPI: dependencies installed"

# 9. Ollama startup check and model pull
echo ""
echo "--- Ollama Models ---"
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama..."
  (ollama serve >/tmp/ollama.log 2>&1 &)
  sleep 2
fi

if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "ERROR: Ollama did not start. Try 'ollama serve' in a separate terminal."
  exit 1
fi

echo "Pulling default models..."
# Tag must match install.sh step 6 (06-pull-models.sh) and the USB-staged
# manifests. Mismatching here causes a redundant network pull when running
# from the kit's wizard.
ollama pull qwen3:4b-instruct
ollama pull smollm2:360m
echo "Ollama: models ready"

# 10. Download Whisper model
echo ""
echo "--- Whisper Model ---"
MODEL_DIR="$PROJECT_DIR/models"
WHISPER_FILE="ggml-base.en.bin"
WHISPER_PATH="$MODEL_DIR/$WHISPER_FILE"

if [ -f "$WHISPER_PATH" ]; then
  echo "Whisper model already exists: $WHISPER_PATH"
else
  echo "Downloading Whisper base.en model (~142 MB)..."
  mkdir -p "$MODEL_DIR"
  WHISPER_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/$WHISPER_FILE"
  if command -v wget &>/dev/null; then
    wget -q --show-progress -O "$WHISPER_PATH" "$WHISPER_URL"
  else
    curl -L --progress-bar -o "$WHISPER_PATH" "$WHISPER_URL"
  fi
  echo "Whisper model downloaded: $WHISPER_PATH"
fi

# 11. Frontend dependencies
echo ""
echo "--- Frontend ---"
cd "$PROJECT_DIR/frontend"
if [ -d "node_modules" ]; then
  echo "Frontend dependencies: OK"
else
  echo "Installing frontend dependencies..."
  npm ci
  echo "Frontend dependencies: installed"
fi
cd "$PROJECT_DIR"

# 12. Check for avatar
echo ""
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

echo "=== Setup Complete ==="
echo ""
echo "To start NodeAva:"
echo "  ./scripts/start-mac.sh"
echo ""
echo "Then open http://localhost:3000 in your browser."
