#!/bin/bash
# Install Ollama (host-native) and pull NodeAva's default models.
# Works on Linux distros + WSL2.
set -euo pipefail

# Source the install lib so we can reuse ensure_ollama_host_bind. The lib
# lives at scripts/install/_lib.sh, a sibling of this script.
# shellcheck source=./install/_lib.sh
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/install/_lib.sh"

echo "[setup-linux] Checking for Ollama..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "[setup-linux] Installing Ollama via official installer..."
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "[setup-linux] Ollama already installed: $(ollama --version 2>/dev/null || echo unknown)"
fi

# Ollama installs as a systemd service on most distros; on WSL2 / minimal
# installs it may need to be started manually. Probe and start if needed.
if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-linux] Ollama not responding. Attempting to start..."
  if command -v systemctl >/dev/null 2>&1 && systemctl --user is-enabled ollama >/dev/null 2>&1; then
    systemctl --user start ollama
  else
    # WSL2 or no systemd — start a detached process
    nohup ollama serve >/tmp/ollama.log 2>&1 &
    sleep 2
  fi
fi

if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "[setup-linux] ERROR: Ollama is not reachable at http://localhost:11434"
  echo "[setup-linux] Start it manually with 'ollama serve' and rerun this script."
  exit 1
fi

echo "[setup-linux] Pulling default models..."
# Tag must match install.sh step 6 (06-pull-models.sh) and the USB-staged
# manifests under ollama-models/manifests/registry.ollama.ai/library/qwen3/.
# Mismatching here causes a redundant network pull when running offline.
ollama pull qwen3:4b-instruct
ollama pull smollm2:360m

ensure_ollama_host_bind

echo "[setup-linux] Done. Ollama is ready."
