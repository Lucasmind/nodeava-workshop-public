#!/bin/bash
# Download the Qwen3-4B LLM model (GGUF format) from HuggingFace
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MODEL_DIR="$PROJECT_DIR/models"
MODEL_FILE="Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf"
MODEL_PATH="$MODEL_DIR/$MODEL_FILE"
HF_REPO="bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF"
HF_URL="https://huggingface.co/${HF_REPO}/resolve/main/${MODEL_FILE}"

if [ -f "$MODEL_PATH" ]; then
  echo "Model already exists: $MODEL_PATH"
  exit 0
fi

mkdir -p "$MODEL_DIR"
echo "Downloading $MODEL_FILE (~2.5 GB)..."
echo "Source: $HF_REPO"

# Prefer huggingface-cli (supports resume), fall back to wget
if command -v huggingface-cli &>/dev/null; then
  echo "Using huggingface-cli..."
  huggingface-cli download "$HF_REPO" "$MODEL_FILE" --local-dir "$MODEL_DIR" --local-dir-use-symlinks False
elif command -v wget &>/dev/null; then
  echo "Using wget..."
  wget -c --show-progress -O "$MODEL_PATH" "$HF_URL"
elif command -v curl &>/dev/null; then
  echo "Using curl..."
  curl -L -C - -o "$MODEL_PATH" "$HF_URL"
else
  echo "ERROR: No download tool available. Install wget, curl, or huggingface-cli."
  exit 1
fi

echo "Model downloaded: $MODEL_PATH"
