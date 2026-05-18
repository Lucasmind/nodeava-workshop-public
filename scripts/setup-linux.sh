#!/bin/bash
# Install Ollama (host-native) and pull NodeAva's default models.
# Works on Linux distros + WSL2.
set -euo pipefail

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
ollama pull qwen3:4b
ollama pull smollm2:360m

# Configure Ollama to listen on all interfaces so the orchestrator Docker
# container can reach it via host.docker.internal.  Skipped silently if
# we cannot write the drop-in directory (e.g., non-root).
OLLAMA_DROPIN="/etc/systemd/system/ollama.service.d"
DROPIN_FILE="$OLLAMA_DROPIN/override.conf"
if command -v systemctl >/dev/null 2>&1 && [ -d /etc/systemd/system ]; then
  if sudo mkdir -p "$OLLAMA_DROPIN" 2>/dev/null && \
     sudo tee "$DROPIN_FILE" >/dev/null 2>&1 <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
  then
    echo "[setup-linux] Configured Ollama to listen on 0.0.0.0:11434 (for Docker access)."
    sudo systemctl daemon-reload
    sudo systemctl restart ollama
    sleep 2
    echo "[setup-linux] Ollama restarted."
  else
    echo "[setup-linux] WARNING: Could not write $DROPIN_FILE (needs sudo)."
    echo "[setup-linux] To allow Docker containers to reach Ollama, run:"
    echo "[setup-linux]   sudo mkdir -p $OLLAMA_DROPIN"
    echo "[setup-linux]   echo '[Service]' | sudo tee $DROPIN_FILE"
    echo "[setup-linux]   echo 'Environment=\"OLLAMA_HOST=0.0.0.0:11434\"' | sudo tee -a $DROPIN_FILE"
    echo "[setup-linux]   sudo systemctl daemon-reload && sudo systemctl restart ollama"
  fi
fi

echo "[setup-linux] Done. Ollama is ready."
