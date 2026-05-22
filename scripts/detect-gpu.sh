#!/bin/bash
# Detect GPU vendor and optionally report VRAM for container configuration
set -euo pipefail

show_vram=false
if [ "${1:-}" = "--vram" ]; then
  show_vram=true
fi

detect_gpu() {
  # Check NVIDIA
  if command -v nvidia-smi &>/dev/null; then
    if nvidia-smi &>/dev/null; then
      echo "nvidia"
      return
    fi
  fi

  # Check via lspci
  if command -v lspci &>/dev/null; then
    local gpu_info
    gpu_info=$(lspci | grep -iE 'vga|3d|display' 2>/dev/null || true)

    if echo "$gpu_info" | grep -qi nvidia; then
      echo "nvidia"
      return
    fi

    if echo "$gpu_info" | grep -qi 'amd\|radeon'; then
      echo "amd"
      return
    fi
  fi

  # Check /dev/dri for any GPU
  if [ -d /dev/dri ]; then
    if [ -e /dev/kfd ]; then
      echo "amd"
      return
    fi
  fi

  echo "none"
}

detect_vram_mb() {
  local gpu_type="$1"

  case "$gpu_type" in
    nvidia)
      if command -v nvidia-smi &>/dev/null; then
        nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' '
        return
      fi
      ;;
    amd)
      # Read VRAM from sysfs (reported in bytes)
      for card in /sys/class/drm/card*/device/mem_info_vram_total; do
        if [ -f "$card" ]; then
          local bytes
          bytes=$(cat "$card" 2>/dev/null || echo "0")
          if [ "$bytes" -gt 0 ] 2>/dev/null; then
            echo $(( bytes / 1024 / 1024 ))
            return
          fi
        fi
      done
      ;;
  esac

  echo "0"
}

GPU=$(detect_gpu)

if [ "$show_vram" = true ]; then
  VRAM=$(detect_vram_mb "$GPU")
  echo "$GPU $VRAM"
else
  echo "$GPU"
fi
