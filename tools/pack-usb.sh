#!/usr/bin/env bash
#
# pack-usb.sh — bundle the workshop kit into a USB-ready staging directory.
#
# Runs on the BUILD machine (Lucasmind's laptop). Produces ./dist/usb-stage/
# containing everything an attendee needs for a fully-offline install:
#
#   START_HERE.md
#   setup.sh / setup.bat            ← bootstrap, written by us
#   source/nodeava-workshop/        ← clean git-archive snapshot
#   docker-images/amd64/*.tar       ← docker save for each service
#   ollama-models/{manifests,blobs} ← qwen3:4b-instruct + smollm2:360m
#   whisper-models/*.bin            ← ggml-base.en.bin
#   installers/                     ← Docker Desktop + Ollama for each platform
#
# Total target size: ~11 GB (fits a 16 GB stick, comfortable on 32 GB).
#
# Usage:  bash tools/pack-usb.sh [--skip-installers] [--skip-docker]
#                                [--include-llamacpp] [--arch amd64|arm64]
#
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
STAGE="$REPO/dist/usb-stage"
# Bootstrap files (setup.sh, setup.bat, START_HERE.md, uninstall-docker-ollama.sh)
# now live at the REPO ROOT so a `git clone` works identically to running from
# a USB stick. They get copied verbatim to the USB stage root.
SCRIPT_DIR="$REPO"

ARCH="amd64"
SKIP_INSTALLERS=0
SKIP_DOCKER=0
INCLUDE_LLAMACPP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --skip-installers) SKIP_INSTALLERS=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    --include-llamacpp) INCLUDE_LLAMACPP=1; shift ;;
    -h|--help)
      sed -n '/^#/,/^$/p' "$0" | sed 's/^#//' | head -30
      exit 0
      ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

# ── Output helpers ──────────────────────────────────────────────────────────
C_R='\033[0;31m' C_G='\033[0;32m' C_Y='\033[0;33m' C_B='\033[0;34m' C_0='\033[0m'
say()  { printf "%b\n" "${C_B}»${C_0} $*"; }
ok()   { printf "%b\n" "  ${C_G}✓${C_0} $*"; }
warn() { printf "%b\n" "  ${C_Y}!${C_0} $*"; }
err()  { printf "%b\n" "  ${C_R}✗${C_0} $*"; }

# Check a binary is present
need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "$1 not found — install it before running pack-usb.sh"
    exit 1
  fi
}

# ── 0. Prereqs ──────────────────────────────────────────────────────────────
say "Checking prerequisites"
need git
need docker
need curl
need python3
[[ $SKIP_DOCKER -eq 0 ]] && need ollama

ok "git, docker, curl, python3$([[ $SKIP_DOCKER -eq 0 ]] && echo ', ollama') present"

# ── 1. Reset stage ──────────────────────────────────────────────────────────
say "Resetting $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"/{source,docker-images/"$ARCH",ollama-models/{manifests,blobs},whisper-models,installers,docs}

# ── 2. Source snapshot ──────────────────────────────────────────────────────
say "Archiving source tree"
cd "$REPO"
git archive --format=tar HEAD | tar -x -C "$STAGE/source/"
# Rename to the expected directory name
mv "$STAGE/source/$(ls "$STAGE/source/")" "$STAGE/source/nodeava-workshop" 2>/dev/null || \
  ( mkdir -p "$STAGE/source/nodeava-workshop" && \
    cd "$STAGE/source" && \
    mv $(ls | grep -v nodeava-workshop) nodeava-workshop/ 2>/dev/null || true )

# Actually, git archive emits files at root — restructure:
if [[ ! -d "$STAGE/source/nodeava-workshop" ]]; then
  mkdir -p "$STAGE/source/nodeava-workshop"
  cd "$STAGE/source"
  shopt -s dotglob
  for f in *; do
    [[ "$f" == "nodeava-workshop" ]] && continue
    mv "$f" nodeava-workshop/
  done
  shopt -u dotglob
fi
cd "$REPO"
SRC_SIZE=$(du -sh "$STAGE/source/nodeava-workshop" | cut -f1)
ok "source archive: $SRC_SIZE"

# ── 3. Docker images ────────────────────────────────────────────────────────
if [[ $SKIP_DOCKER -eq 0 ]]; then
  say "Saving Docker images (arch: $ARCH)"

  # Build / pull our local + external images
  IMAGES=(
    "nodeava-orch:latest"
    "workshop-mvp-spec-frontend:latest"
    "workshop-mvp-spec-stt:latest"
    "ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4"
    "searxng/searxng:latest"
  )
  [[ $INCLUDE_LLAMACPP -eq 1 ]] && IMAGES+=("ghcr.io/ggml-org/llama.cpp:server-cuda")

  # Pick the fastest gzip-compatible compressor we have.
  # pigz = parallel gzip, 4-5x faster on multi-core. Output is plain .gz so
  # attendees can decompress with native gunzip/zcat on any platform.
  if command -v pigz >/dev/null 2>&1; then
    COMPRESSOR=(pigz -6 -p "$(nproc 2>/dev/null || echo 4)")
    say "  using pigz (parallel gzip)"
  else
    COMPRESSOR=(gzip -6)
    say "  using gzip (slower but universal)"
  fi

  for img in "${IMAGES[@]}"; do
    if ! docker image inspect "$img" >/dev/null 2>&1; then
      warn "image not found locally: $img — attempting docker pull"
      if ! docker pull "$img" >/dev/null 2>&1; then
        err "cannot acquire $img — skipping"
        continue
      fi
    fi
    # Sanitize filename: replace : and / with -
    safe="${img//\//-}"
    safe="${safe//:/-}"
    out="$STAGE/docker-images/$ARCH/${safe}.tar.gz"
    say "  saving + compressing $img → ${safe}.tar.gz"
    docker save "$img" | "${COMPRESSOR[@]}" > "$out"
    ok "$(du -h "$out" | cut -f1) ${safe}.tar.gz"
  done
else
  warn "skipping docker images (--skip-docker)"
fi

# ── 4. Ollama models ────────────────────────────────────────────────────────
say "Copying Ollama models"

# Ollama's models dir depends on how it was installed:
#   - user install: ~/.ollama/models/
#   - systemd service install: /usr/share/ollama/.ollama/models/
# Honor OLLAMA_MODELS if set; otherwise probe the standard paths and pick the
# one that actually contains the manifests we need.
OLLAMA_HOME=""
if [[ -n "${OLLAMA_MODELS:-}" ]]; then
  OLLAMA_HOME="$OLLAMA_MODELS"
else
  for cand in "$HOME/.ollama/models" "/usr/share/ollama/.ollama/models" "/var/lib/ollama/.ollama/models"; do
    if [[ -d "$cand/manifests/registry.ollama.ai/library/qwen3" ]] || \
       [[ -d "$cand/manifests/registry.ollama.ai/library/smollm2" ]]; then
      OLLAMA_HOME="$cand"
      break
    fi
  done
fi

if [[ -z "$OLLAMA_HOME" ]] || [[ ! -d "$OLLAMA_HOME" ]]; then
  err "could not locate Ollama models dir — set OLLAMA_MODELS env var"
else
  ok "using Ollama models at $OLLAMA_HOME"
  copy_ollama_model() {
    local name="$1"  # e.g. "qwen3:4b-instruct"
    local family="${name%:*}"
    local tag="${name#*:}"
    local manifest_src="$OLLAMA_HOME/manifests/registry.ollama.ai/library/$family/$tag"

    if [[ ! -f "$manifest_src" ]]; then
      err "manifest not found: $manifest_src — run 'ollama pull $name' first"
      return 1
    fi

    local manifest_dst_dir="$STAGE/ollama-models/manifests/registry.ollama.ai/library/$family"
    mkdir -p "$manifest_dst_dir"
    cp "$manifest_src" "$manifest_dst_dir/$tag"

    # Pull blob digests out of the manifest (config + layers)
    python3 - "$manifest_src" <<'PY' | while IFS= read -r digest; do
import json, sys
with open(sys.argv[1]) as f:
    m = json.load(f)
blobs = set()
cfg = m.get('config', {}).get('digest')
if cfg: blobs.add(cfg)
for layer in m.get('layers', []):
    d = layer.get('digest')
    if d: blobs.add(d)
for b in blobs:
    print(b)
PY
      # digest like "sha256:abcdef..." becomes file "sha256-abcdef..."
      local fname="${digest/:/-}"
      local src="$OLLAMA_HOME/blobs/$fname"
      if [[ -f "$src" ]]; then
        cp "$src" "$STAGE/ollama-models/blobs/$fname"
      else
        warn "blob missing on disk: $fname (model may be partially downloaded)"
      fi
    done
    ok "$name"
  }

  copy_ollama_model "qwen3:4b-instruct"
  copy_ollama_model "smollm2:360m"
fi

# ── 5. Whisper models ──────────────────────────────────────────────────────
say "Copying Whisper models"
# Models live in $REPO/models/ (mounted into the STT container at /models)
# OR in the host's project-relative ./models. Try both.
WHISPER_HOST_DIR=""
for cand in "$REPO/models" "$REPO/.models" /opt/whisper-models; do
  if [[ -d "$cand" ]] && ls "$cand"/ggml-*.bin >/dev/null 2>&1; then
    WHISPER_HOST_DIR="$cand"
    break
  fi
done

if [[ -n "$WHISPER_HOST_DIR" ]]; then
  for f in "$WHISPER_HOST_DIR"/ggml-*.bin; do
    [[ -f "$f" ]] || continue
    cp "$f" "$STAGE/whisper-models/"
    ok "$(basename "$f") ($(du -h "$f" | cut -f1))"
  done
else
  warn "no whisper models found on host — extracting from the running STT container"
  # Extract from the running container as a fallback
  if docker ps --format '{{.Names}}' | grep -q '^workshop-mvp-spec-stt-1$'; then
    docker cp workshop-mvp-spec-stt-1:/models/ggml-base.en.bin "$STAGE/whisper-models/" 2>/dev/null && \
      ok "ggml-base.en.bin (via docker cp)"
  else
    err "STT container not running — cannot get whisper models. Re-run with the stack up."
  fi
fi

# ── 6. Bootstrap scripts ────────────────────────────────────────────────────
say "Copying bootstrap scripts"
cp "$SCRIPT_DIR/setup.sh"   "$STAGE/"
cp "$SCRIPT_DIR/setup.bat"  "$STAGE/"
cp "$SCRIPT_DIR/START_HERE.md" "$STAGE/"
cp "$SCRIPT_DIR/troubleshooting.md" "$STAGE/docs/"
cp "$SCRIPT_DIR/uninstall-docker-ollama.sh" "$STAGE/"
chmod +x "$STAGE/setup.sh" "$STAGE/uninstall-docker-ollama.sh"
chmod +x "$STAGE/setup.sh"
ok "setup.sh, setup.bat, START_HERE.md"

# ── 7. Installers ───────────────────────────────────────────────────────────
if [[ $SKIP_INSTALLERS -eq 0 ]]; then
  say "Downloading installers (this is the slow step)"

  dl() {
    local url="$1" out="$2"
    if [[ -f "$out" ]]; then
      ok "$(basename "$out") already cached"
      return 0
    fi
    say "  fetching $(basename "$out")…"
    if curl -fsSL --connect-timeout 10 -o "$out" "$url"; then
      ok "$(basename "$out") ($(du -h "$out" | cut -f1))"
    else
      warn "failed: $url"
      rm -f "$out"
    fi
  }

  dl "https://desktop.docker.com/mac/main/arm64/Docker.dmg"   "$STAGE/installers/DockerDesktop-Mac-AppleSilicon.dmg"
  dl "https://desktop.docker.com/mac/main/amd64/Docker.dmg"   "$STAGE/installers/DockerDesktop-Mac-Intel.dmg"
  dl "https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe" "$STAGE/installers/DockerDesktop-Win.exe"
  dl "https://github.com/ollama/ollama/releases/latest/download/Ollama-darwin.zip" "$STAGE/installers/Ollama-Mac.zip"
  dl "https://github.com/ollama/ollama/releases/latest/download/OllamaSetup.exe"   "$STAGE/installers/Ollama-Win.exe"

  # Linux Ollama: just save the install.sh
  curl -fsSL https://ollama.com/install.sh -o "$STAGE/installers/ollama-linux-install.sh" && \
    chmod +x "$STAGE/installers/ollama-linux-install.sh" && \
    ok "ollama-linux-install.sh"

  # Linux Docker — offline-friendly install script + static binaries.
  # install-docker.sh tries get.docker.com first, falls back to these tarballs.
  mkdir -p "$STAGE/installers/linux"
  cp "$REPO/installers/linux/install-docker.sh" \
     "$STAGE/installers/linux/install-docker.sh"
  chmod +x "$STAGE/installers/linux/install-docker.sh"
  ok "install-docker.sh"

  DOCKER_STATIC_VER="27.3.1"
  COMPOSE_VER="v2.29.7"
  dl "https://download.docker.com/linux/static/stable/x86_64/docker-${DOCKER_STATIC_VER}.tgz" \
     "$STAGE/installers/linux/docker-static-amd64.tgz"
  dl "https://github.com/docker/compose/releases/download/${COMPOSE_VER}/docker-compose-linux-x86_64" \
     "$STAGE/installers/linux/docker-compose-linux-amd64"
  [[ -f "$STAGE/installers/linux/docker-compose-linux-amd64" ]] && \
    chmod +x "$STAGE/installers/linux/docker-compose-linux-amd64"

  # Linux Ollama tarball — install-docker.sh's sibling install-ollama.sh
  # (also USB-bundled) uses this to install Ollama offline.
  dl "https://github.com/ollama/ollama/releases/latest/download/ollama-linux-amd64.tgz" \
     "$STAGE/installers/linux/ollama-linux-amd64.tgz"
else
  warn "skipping installers (--skip-installers)"
fi

# ── 8. Drift list + docs ────────────────────────────────────────────────────
say "Bundling extra docs"
if [[ -f "$REPO/docs/deck-reconciliation-2026-05-18.md" ]]; then
  cp "$REPO/docs/deck-reconciliation-2026-05-18.md" "$STAGE/docs/"
  ok "deck-reconciliation-2026-05-18.md"
fi
if [[ -f "$REPO/CLAUDE.md" ]]; then
  cp "$REPO/CLAUDE.md" "$STAGE/docs/architecture-notes.md"
  ok "architecture-notes.md (from CLAUDE.md)"
fi

# ── 9. Stamp + summary ──────────────────────────────────────────────────────
say "Writing version stamp"
cat > "$STAGE/VERSION" <<EOF
NodeAva Workshop Kit
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Source commit: $(git rev-parse HEAD)
Branch: $(git rev-parse --abbrev-ref HEAD)
Architecture: $ARCH
Includes llama.cpp: $([[ $INCLUDE_LLAMACPP -eq 1 ]] && echo yes || echo no)
EOF
ok "VERSION written"

echo
say "Pack complete. Summary:"
du -sh "$STAGE"/*
echo
TOTAL=$(du -sh "$STAGE" | cut -f1)
echo
ok "Total stage size: $TOTAL"
echo
say "Next step: rsync to USB"
echo "    rsync -av --progress $STAGE/ /run/media/\$USER/<USB_LABEL>/"
echo
say "Or tar it for upload:"
echo "    cd $(dirname "$STAGE") && tar czf NodeAva-Workshop-Kit-\$(date +%Y%m%d).tar.gz usb-stage/"
