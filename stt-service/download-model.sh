#!/bin/bash
set -euo pipefail

MODEL_DIR="${MODEL_DIR:-/models}"
MODEL_NAME="${WHISPER_MODEL:-base.en}"
MODEL_FILE="ggml-${MODEL_NAME}.bin"
MODEL_PATH="${MODEL_DIR}/${MODEL_FILE}"

if [ -f "$MODEL_PATH" ]; then
  echo "Model already exists: $MODEL_PATH"
  exit 0
fi

echo "Downloading Whisper model: ${MODEL_NAME}..."
mkdir -p "$MODEL_DIR"

BASE_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
wget -q --show-progress -O "$MODEL_PATH" "${BASE_URL}/${MODEL_FILE}"

echo "Model downloaded: $MODEL_PATH"
