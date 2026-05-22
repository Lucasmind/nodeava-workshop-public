#!/usr/bin/env bash
# Full reset for end-to-end testing of the workshop kit.
#
# Reverses everything setup.sh and install.sh do:
#   - brings down the docker-compose stack (orchestrator, frontend, stt, tts, searxng)
#   - removes nodeava-orch / nodeava-kokoro-rocm images
#   - removes the base images loaded from docker-images/$ARCH/*.tar*
#   - removes the staged source tree at ~/nodeava-workshop/
#   - removes ~/.ollama (models + manifests)
#   - removes the Ollama systemd unit + drop-in (0.0.0.0 bind)
#   - purges Docker Engine + Compose plugin packages
#   - drops the invoking user from the 'docker' group
#
# Run with: sudo ./uninstall-docker-ollama.sh

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-}"
TARGET_HOME=""
if [[ -n "$TARGET_USER" ]]; then
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
fi
NODEAVA_DIR="${TARGET_HOME:+$TARGET_HOME/nodeava-workshop}"
USB_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Workshop stack teardown ────────────────────────────────────────────────
# This must run BEFORE Docker is purged below.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "==> Bringing down NodeAva docker-compose stack"
  if [[ -n "$NODEAVA_DIR" && -d "$NODEAVA_DIR" ]]; then
    for overlay in "" "-f docker-compose.gpu-nvidia.yml" "-f docker-compose.gpu-amd.yml"; do
      # shellcheck disable=SC2086
      (cd "$NODEAVA_DIR" && docker compose -f docker-compose.yml $overlay down -v --remove-orphans 2>/dev/null) || true
    done
  fi

  # Belt-and-braces: kill anything left from this compose project, by label
  # (catches the case where source tree was already deleted but containers linger).
  leftover="$(docker ps -aq --filter 'label=com.docker.compose.project=nodeava-workshop' 2>/dev/null || true)"
  if [[ -n "$leftover" ]]; then
    # shellcheck disable=SC2086
    docker rm -f $leftover 2>/dev/null || true
  fi
  # And by name, for anything started outside compose (older install scripts did this)
  for name in nodeava-orch searxng; do
    docker rm -f "$name" 2>/dev/null || true
  done

  echo "==> Removing workshop images by name"
  # Includes:
  #   nodeava-orch              — built by step 7
  #   nodeava-kokoro-rocm       — built by step 7 (AMD path)
  #   kokoro-fastapi-cpu        — pulled at runtime when install.sh detects
  #                               Blackwell (NOT bundled on USB, so the
  #                               tarball-peek block below won't catch it)
  #   kokoro-fastapi-gpu        — bundled, but also catch it by name in case
  #                               the tarball-peek block misses (e.g., zstd
  #                               variant + no zstd installed)
  for repo in nodeava-orch nodeava-kokoro-rocm \
              ghcr.io/remsky/kokoro-fastapi-cpu \
              ghcr.io/remsky/kokoro-fastapi-gpu; do
    ids="$(docker images --format '{{.Repository}}:{{.Tag}} {{.ID}}' 2>/dev/null \
            | awk -v r="$repo" '$1 ~ "^"r":" {print $2}' | sort -u)"
    if [[ -n "$ids" ]]; then
      # shellcheck disable=SC2086
      docker rmi -f $ids 2>/dev/null || true
    fi
  done

  echo "==> Removing base images loaded from USB tarballs"
  peek_repotags() {
    local tar="$1" extract
    case "$tar" in
      *.tar.gz)  extract="gunzip -c \"$tar\"" ;;
      *.tar.zst) command -v zstd >/dev/null 2>&1 || return 1; extract="zstd -dc \"$tar\"" ;;
      *.tar)     extract="cat \"$tar\"" ;;
      *) return 1 ;;
    esac
    eval "$extract" 2>/dev/null \
      | tar -xO manifest.json 2>/dev/null \
      | tr -d '\n' \
      | sed -n 's/.*"RepoTags":\[\([^]]*\)\].*/\1/p' \
      | tr ',' '\n' | tr -d '"'
  }
  for IMG_DIR in "$USB_ROOT/docker-images/amd64" "$USB_ROOT/docker-images/arm64"; do
    [[ -d "$IMG_DIR" ]] || continue
    for tar in "$IMG_DIR"/*.tar.gz "$IMG_DIR"/*.tar.zst "$IMG_DIR"/*.tar; do
      [[ -f "$tar" ]] || continue
      tags="$(peek_repotags "$tar" || true)"
      [[ -z "$tags" ]] && continue
      while IFS= read -r tag; do
        [[ -z "$tag" ]] && continue
        docker rmi -f "$tag" 2>/dev/null || true
      done <<< "$tags"
    done
  done

  # Stray volumes + the compose network
  vols="$(docker volume ls --filter 'label=com.docker.compose.project=nodeava-workshop' -q 2>/dev/null || true)"
  if [[ -n "$vols" ]]; then
    # shellcheck disable=SC2086
    docker volume rm $vols 2>/dev/null || true
  fi
  docker network rm nodeava-workshop_default 2>/dev/null || true
else
  echo "==> Docker not running — skipping stack teardown"
fi

# ── Staged source tree ─────────────────────────────────────────────────────
if [[ -n "$NODEAVA_DIR" && -d "$NODEAVA_DIR" ]]; then
  echo "==> Removing staged source tree at $NODEAVA_DIR"
  rm -rf "$NODEAVA_DIR"
fi

echo "==> Stopping Ollama service (if running)"
systemctl stop ollama 2>/dev/null || true
systemctl disable ollama 2>/dev/null || true

echo "==> Removing Ollama binaries, units, drop-ins, and models"
rm -f /usr/local/bin/ollama
rm -f /etc/systemd/system/ollama.service
rm -rf /etc/systemd/system/ollama.service.d
rm -rf /usr/share/ollama
rm -rf /var/lib/ollama
if [[ -n "$TARGET_HOME" && -d "$TARGET_HOME/.ollama" ]]; then
  rm -rf "$TARGET_HOME/.ollama"
fi
if id ollama >/dev/null 2>&1; then
  userdel ollama 2>/dev/null || true
fi
if getent group ollama >/dev/null 2>&1; then
  groupdel ollama 2>/dev/null || true
fi
systemctl daemon-reload

echo "==> Stopping Docker daemon (if running)"
systemctl stop docker docker.socket containerd 2>/dev/null || true
systemctl disable docker docker.socket containerd 2>/dev/null || true

echo "==> Purging Docker packages"
DEBIAN_FRONTEND=noninteractive apt-get purge -y \
  docker-ce docker-ce-cli containerd.io \
  docker-buildx-plugin docker-compose-plugin \
  docker-ce-rootless-extras 2>/dev/null || true
DEBIAN_FRONTEND=noninteractive apt-get autoremove -y 2>/dev/null || true

echo "==> Purging NVIDIA Container Toolkit"
DEBIAN_FRONTEND=noninteractive apt-get purge -y \
  nvidia-container-toolkit nvidia-container-toolkit-base \
  libnvidia-container-tools libnvidia-container1 2>/dev/null || true
rm -f /etc/apt/sources.list.d/nvidia-container-toolkit.list \
      /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

echo "==> Removing Docker data, config, apt source, and keyring"
rm -rf /var/lib/docker /var/lib/containerd /etc/docker
rm -f /etc/apt/sources.list.d/docker.list /etc/apt/keyrings/docker.gpg

if [[ -n "$TARGET_USER" ]] && id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
  echo "==> Removing $TARGET_USER from the docker group"
  gpasswd -d "$TARGET_USER" docker || true
fi
if getent group docker >/dev/null 2>&1; then
  groupdel docker 2>/dev/null || true
fi

apt-get update -qq 2>/dev/null || true

echo
echo "==> Verifying"
command -v docker >/dev/null 2>&1 \
  && echo "  ! docker still on PATH at $(command -v docker)" \
  || echo "  ✓ docker removed"
command -v ollama >/dev/null 2>&1 \
  && echo "  ! ollama still on PATH at $(command -v ollama)" \
  || echo "  ✓ ollama removed"
systemctl status ollama --no-pager >/dev/null 2>&1 \
  && echo "  ! ollama.service still present" \
  || echo "  ✓ ollama.service gone"
ss -ltn 'sport = :11434' 2>/dev/null | grep -q LISTEN \
  && echo "  ! something still listening on :11434" \
  || echo "  ✓ port 11434 free"
[[ -n "$NODEAVA_DIR" && -d "$NODEAVA_DIR" ]] \
  && echo "  ! $NODEAVA_DIR still present" \
  || echo "  ✓ workshop source tree gone"
[[ -n "$TARGET_HOME" && -d "$TARGET_HOME/.ollama" ]] \
  && echo "  ! $TARGET_HOME/.ollama still present" \
  || echo "  ✓ ~/.ollama gone"

echo
echo "Done. You may want to log out and back in so the dropped 'docker' group"
echo "membership clears from existing shells."
