#!/usr/bin/env bash
#
# NodeAva Workshop Kit — attendee bootstrap.
#
# Runs on the attendee's machine to install everything from the USB stick.
# Works on macOS (Apple Silicon + Intel), Linux, and WSL2.
#
# Usage:  cd <usb-mount-point> && ./setup.sh
#
set -euo pipefail

USB_ROOT="$(cd "$(dirname "$0")" && pwd)"

# ── Arg parsing ────────────────────────────────────────────────────────────
# --offline  Force the bundled installers (install-docker.sh / install-ollama.sh)
#            to skip their network probes and use only USB-bundled binaries.
# --online   Force network-only (fail if no network; never use USB bundles).
# (default)  Auto: each installer tries the network with a 3 s probe and falls
#            back to USB bundles if unreachable.
INSTALL_MODE_FLAG=""
usage() {
  cat <<EOF
Usage: $(basename "$0") [--offline | --online] [--help]

  --offline   Force installers to use only the USB-bundled binaries.
  --online    Force installers to use only the network.
  (default)   Auto: try network with a 3s probe, fall back to USB bundles.
EOF
}
for arg in "$@"; do
  case "$arg" in
    --offline)  INSTALL_MODE_FLAG="--offline" ;;
    --online)   INSTALL_MODE_FLAG="--online" ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; usage >&2; exit 2 ;;
  esac
done

# ── Colours / banners ──────────────────────────────────────────────────────
C_R='\033[0;31m' C_G='\033[0;32m' C_Y='\033[0;33m' C_B='\033[0;34m' C_C='\033[0;36m' C_0='\033[0m'
say()   { printf "%b\n" "${C_B}»${C_0} $*"; }
ok()    { printf "%b\n" "  ${C_G}✓${C_0} $*"; }
warn()  { printf "%b\n" "  ${C_Y}!${C_0} $*"; }
fail()  { printf "%b\n" "  ${C_R}✗${C_0} $*"; exit 1; }
step()  { printf "\n%b\n" "${C_C}── $* ──${C_0}"; }

# ── 0. Welcome ─────────────────────────────────────────────────────────────
clear
cat <<'EOF'
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   NodeAva Workshop Kit — offline installer                      │
│   Built locally on your machine. No internet needed.            │
│                                                                 │
│   This will:                                                    │
│     1. Detect your platform                                     │
│     2. Install Docker if missing (native on Linux/WSL2;         │
│        Docker Desktop on macOS)                                 │
│     3. Install Ollama if missing                                │
│     4. Load pre-built Docker images                             │
│     5. Stage Ollama models to ~/.ollama/                        │
│     6. Copy the source tree to ~/nodeava-workshop/              │
│     7. Run the install wizard (preflight + smoke verify)        │
│                                                                 │
│   Time: 5–10 min. Press Ctrl-C any time to abort.               │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
EOF
echo
read -r -p "Press <Enter> to continue, or Ctrl-C to abort … "

# ── 1. Detect platform ─────────────────────────────────────────────────────
step "Step 1 of 7 · Detect platform"
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Darwin)  PLATFORM="mac" ;;
  Linux)
    if grep -qi microsoft /proc/version 2>/dev/null; then
      PLATFORM="wsl2"
    else
      PLATFORM="linux"
    fi
    ;;
  *) fail "Unsupported OS: $OS (this kit supports macOS, Linux, WSL2)"
esac

case "$ARCH" in
  arm64|aarch64) PLATFORM_ARCH="arm64" ;;
  x86_64|amd64)  PLATFORM_ARCH="amd64" ;;
  *) fail "Unsupported architecture: $ARCH"
esac

ok "Platform: $PLATFORM ($PLATFORM_ARCH)"
case "$INSTALL_MODE_FLAG" in
  --offline) warn "Install mode: OFFLINE (USB bundles only, no network)" ;;
  --online)  warn "Install mode: ONLINE (network only, no USB fallback)" ;;
esac

# Disk space — the kokoro CUDA image alone is ~27 GB once loaded, plus
# ~3 GB of Ollama models, ~5 GB of other images, and the staged source tree.
# We need real headroom on whichever partition holds /var/lib/docker
# (Linux/WSL2) or the Docker Desktop VM image (macOS, ~/Library).
#   - hard fail below 20 GB: not enough room for kokoro alone
#   - warn between 20–40 GB: tight, may fail mid-load
#   - ok at 40+ GB
case "$PLATFORM" in
  linux|wsl2) DISK_CHECK_PATH="/var" ;;
  mac)        DISK_CHECK_PATH="$HOME" ;;
esac
probe="$DISK_CHECK_PATH"
while [[ -n "$probe" && ! -d "$probe" ]]; do probe="$(dirname "$probe")"; done
free_gb=$(df -BG "$probe" 2>/dev/null | awk 'NR==2{gsub("G","",$4); print $4+0}')
if [[ -z "$free_gb" || "$free_gb" -eq 0 ]]; then
  warn "Disk: could not determine free space on $probe — skipping check"
elif [[ "$free_gb" -lt 20 ]]; then
  warn "Disk: only ${free_gb} GB free on $probe's partition."
  warn "  The kokoro container image is ~27 GB by itself. Step 4 will run"
  warn "  out of space and corrupt your daemon state."
  fail "Need at least 20 GB free; ideally 40 GB."
elif [[ "$free_gb" -lt 40 ]]; then
  warn "Disk: ${free_gb} GB free on $probe — tight. 40 GB is the comfortable floor."
else
  ok "Disk: ${free_gb} GB free on $probe's partition"
fi

# Blackwell GPU detection — Kokoro GPU image bundles PyTorch <2.6 which has
# no precompiled CUDA kernels for sm_120 (RTX 50-series, RTX PRO Blackwell).
# When detected, step 4 will skip loading the kokoro-fastapi-gpu tarball
# (it would just waste ~14 GB of disk for an image that can't run on this
# GPU), and install.sh step 8 will auto-write a docker-compose.override.yml
# that pins the CPU TTS image.
SETUP_GPU_BLACKWELL=0
if command -v nvidia-smi >/dev/null 2>&1; then
  cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' \r' || true)"
  case "$cap" in
    12.*|13.*|14.*|15.*)
      SETUP_GPU_BLACKWELL=1
      warn "Blackwell GPU detected (compute cap ${cap}) — step 4 will skip the kokoro-fastapi-gpu tarball"
      warn "  (the GPU image's PyTorch <2.6 has no sm_120 kernels; install.sh step 8"
      warn "  will auto-pin the CPU TTS image instead)"
      ;;
  esac
fi
export SETUP_GPU_BLACKWELL

# ── 2. Docker ──────────────────────────────────────────────────────────────
# macOS: Docker Desktop (no native Linux containers on Mac).
# Linux/WSL2: native Docker via the USB-bundled install-docker.sh.
step "Step 2 of 7 · Docker"

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  ok "Docker present and running ($(docker --version))"
else
  warn "Docker not found or not running"
  case "$PLATFORM" in
    mac)
      if [[ "$PLATFORM_ARCH" == "arm64" ]]; then
        DMG="$USB_ROOT/installers/DockerDesktop-Mac-AppleSilicon.dmg"
      else
        DMG="$USB_ROOT/installers/DockerDesktop-Mac-Intel.dmg"
      fi
      if [[ -f "$DMG" ]]; then
        say "Opening Docker Desktop installer (drag to Applications, then re-run setup.sh)"
        open "$DMG"
        fail "After installing Docker Desktop and launching it once, re-run ./setup.sh"
      else
        fail "Docker Desktop installer not found at $DMG"
      fi
      ;;
    linux|wsl2)
      INSTALLER="$USB_ROOT/installers/linux/install-docker.sh"
      if [[ -x "$INSTALLER" ]]; then
        say "Running bundled Docker installer from USB ..."
        say "  (tries get.docker.com first; falls back to bundled static binaries"
        say "   + systemd units if no network reaches download.docker.com in 3s)"
        if [[ "$PLATFORM" = "wsl2" ]]; then
          echo
          echo "    NOTE for WSL2: Docker runs natively inside this distro (NOT via"
          echo "    Docker Desktop). systemd must be enabled in WSL2 — if it isn't,"
          echo "    add to /etc/wsl.conf:  [boot]   systemd=true"
          echo "    then 'wsl --shutdown' from PowerShell and reopen this terminal."
        fi
        echo
        # Re-exec under sudo so password prompt is visible; preserve SUDO_USER
        # so install-docker.sh can add the right account to the docker group.
        if sudo -E "$INSTALLER" $INSTALL_MODE_FLAG; then
          if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
            ok "Docker installed and running ($(docker --version))"
          elif command -v docker >/dev/null 2>&1; then
            warn "Docker installed but the daemon isn't talking to the CLI yet."
            warn "  This usually means your group membership needs a fresh login."
            warn "  Try: newgrp docker   then re-run ./setup.sh"
            fail "Re-run setup.sh after a fresh login"
          else
            fail "install-docker.sh ran but 'docker' is still not on PATH"
          fi
        else
          fail "install-docker.sh failed — see output above"
        fi
      else
        warn "Docker isn't installed and the offline installer isn't on this USB."
        echo "    Manual install options:"
        echo "      sudo apt-get install -y docker.io docker-compose-plugin"
        echo "      curl -fsSL https://get.docker.com | sh"
        echo "      sudo usermod -aG docker \$USER && newgrp docker"
        fail "Install Docker, then re-run ./setup.sh"
      fi
      ;;
  esac
fi

# ── 3. Ollama (LLM serving on host) ────────────────────────────────────────
step "Step 3 of 7 · Ollama"

if command -v ollama >/dev/null 2>&1; then
  ok "Ollama present ($(ollama --version 2>&1 | head -1))"
else
  warn "Ollama not found — installing from USB"
  case "$PLATFORM" in
    mac)
      ZIP="$USB_ROOT/installers/Ollama-Mac.zip"
      if [[ -f "$ZIP" ]]; then
        say "Unzipping Ollama.app to /Applications/"
        TMPDIR=$(mktemp -d)
        unzip -q "$ZIP" -d "$TMPDIR"
        cp -R "$TMPDIR/Ollama.app" /Applications/
        rm -rf "$TMPDIR"
        ok "Ollama.app installed — launch it once from Applications to set up the menubar agent"
        warn "After launching Ollama once, re-run ./setup.sh"
        exit 0
      else
        fail "Ollama installer not found at $ZIP"
      fi
      ;;
    linux|wsl2)
      INSTALLER="$USB_ROOT/installers/linux/install-ollama.sh"
      if [[ -x "$INSTALLER" ]]; then
        say "Running bundled Ollama installer (may prompt for sudo)…"
        say "  (tries ollama.com first; falls back to the USB-bundled tarball if offline)"
        sudo bash "$INSTALLER" $INSTALL_MODE_FLAG || warn "Ollama install reported errors — see output above"
      else
        SH="$USB_ROOT/installers/ollama-linux-install.sh"
        if [[ -f "$SH" ]]; then
          warn "Bundled hybrid installer missing; falling back to upstream installer (needs internet)"
          bash "$SH" || warn "Ollama install reported errors — try again or install manually"
        else
          fail "No Ollama installer found at $INSTALLER or $SH"
        fi
      fi
      ;;
  esac
fi

# Configure Ollama to bind 0.0.0.0:11434 (Linux/WSL2). Default is 127.0.0.1
# which works for direct curl tests but blocks Docker containers reaching it
# via host.docker.internal later in step 8 (orchestrator → Ollama). Apply
# the systemd drop-in NOW so the daemon comes up correctly bound, instead
# of fixing it later in the wizard and having to restart.
if [[ "$PLATFORM" =~ ^(linux|wsl2)$ ]] && command -v systemctl >/dev/null 2>&1 \
   && [[ -d /etc/systemd/system ]]; then
  bind="$(ss -tlnH 2>/dev/null | awk '$4 ~ /:11434$/ {print $4; exit}')"
  if [[ -z "$bind" || "$bind" = "127.0.0.1:11434" || "$bind" = "[::1]:11434" ]]; then
    DROPIN_DIR=/etc/systemd/system/ollama.service.d
    DROPIN_FILE="$DROPIN_DIR/override.conf"
    say "Binding Ollama to 0.0.0.0:11434 (so containers can reach it via host.docker.internal)…"
    if sudo mkdir -p "$DROPIN_DIR" 2>/dev/null && \
       sudo tee "$DROPIN_FILE" >/dev/null 2>&1 <<'OLLAMA_DROPIN_EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
OLLAMA_DROPIN_EOF
    then
      sudo systemctl daemon-reload
      sudo systemctl enable --now ollama 2>/dev/null || sudo systemctl restart ollama
      ok "Ollama bound to 0.0.0.0:11434"
    else
      warn "Could not write $DROPIN_FILE — Ollama may stay on 127.0.0.1 (orchestrator container will fail)"
    fi
  fi
fi

# Verify Ollama is reachable. The daemon takes a few seconds to start
# serving after a fresh install / restart — retry for up to 30 seconds
# before giving up.
say "Waiting for Ollama to start serving on :11434 (up to 30s)…"
ollama_ready=0
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
  if curl -s --max-time 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    ollama_ready=1
    break
  fi
  sleep 2
done

if [[ "$ollama_ready" -eq 1 ]]; then
  ok "Ollama daemon reachable on :11434"
else
  warn "Ollama daemon not responding on :11434 after 30s"
  case "$PLATFORM" in
    mac) say "Launch Ollama.app from /Applications/ (it lives in the menubar), then re-run ./setup.sh" ;;
    linux|wsl2)
      say "Diagnose:  sudo systemctl status ollama"
      say "Restart:   sudo systemctl restart ollama"
      say "Logs:      sudo journalctl -u ollama -n 50 --no-pager"
      ;;
  esac
  fail "Ollama daemon must be running before continuing"
fi

# ── 4. Load Docker images ──────────────────────────────────────────────────
step "Step 4 of 7 · Load Docker images"

IMG_DIR="$USB_ROOT/docker-images/$PLATFORM_ARCH"
if [[ ! -d "$IMG_DIR" ]]; then
  fail "No Docker image tarballs for architecture $PLATFORM_ARCH at $IMG_DIR"
fi

# Handle both compressed (.tar.gz, .tar.zst) and uncompressed (.tar) tarballs.
# Pack-usb.sh ships .tar.gz; .tar.zst is supported for builders who pick zstd;
# bare .tar is the legacy path. gunzip is native on every platform; zstd on
# Mac usually requires `brew install zstd`.
count=0
skipped=0
for tar in "$IMG_DIR"/*.tar.gz "$IMG_DIR"/*.tar.zst "$IMG_DIR"/*.tar; do
  [[ -f "$tar" ]] || continue
  base="$(basename "$tar")"

  # Blackwell skip: don't waste 14 GB of disk loading kokoro-fastapi-gpu —
  # its bundled PyTorch (<2.6) has no sm_120 kernels, the container will
  # fail warmup on this GPU. install.sh step 8 auto-pins the CPU TTS image
  # via docker-compose.override.yml. The bundled image is still useful for
  # the kit itself (other attendees may not have Blackwell), so we leave
  # the tarball on the USB — just don't load it here.
  if [[ "$SETUP_GPU_BLACKWELL" = "1" ]] && [[ "$base" == *kokoro-fastapi-gpu* ]]; then
    warn "skipped $base — Blackwell GPU; this image's PyTorch lacks sm_120 kernels"
    skipped=$((skipped+1))
    continue
  fi

  size="$(du -h "$tar" | cut -f1)"
  say "  loading $base ($size)…"
  case "$tar" in
    *.tar.gz)
      if gunzip -c "$tar" | docker load >/dev/null; then
        ok "loaded $base"; count=$((count+1))
      else
        warn "load failed for $base"
      fi
      ;;
    *.tar.zst)
      if ! command -v zstd >/dev/null 2>&1; then
        warn "$base is zstd-compressed but zstd isn't installed"
        case "$PLATFORM" in
          mac)   warn "  install: brew install zstd" ;;
          linux) warn "  install: sudo apt-get install -y zstd" ;;
          wsl2)  warn "  install: sudo apt-get install -y zstd" ;;
        esac
        warn "  skipping this image — install zstd and re-run setup.sh"
        continue
      fi
      if zstd -dc "$tar" | docker load >/dev/null; then
        ok "loaded $base"; count=$((count+1))
      else
        warn "load failed for $base"
      fi
      ;;
    *.tar)
      if docker load -i "$tar" >/dev/null; then
        ok "loaded $base"; count=$((count+1))
      else
        warn "load failed for $base"
      fi
      ;;
  esac
done
ok "$count image(s) loaded, $skipped skipped"

# Retag the bundled stt + frontend images under the names docker-compose.yml
# expects. The USB ships them as `workshop-mvp-spec-{stt,frontend}:latest`
# (the build-time project name), but compose builds new images named
# `nodeava-workshop-{stt,frontend}:latest` (the runtime project name).
# Without this retag, the first `docker compose up` rebuilds them from
# scratch — which is fragile for stt because its Dockerfile FROM is a
# moving tag (ghcr.io/ggml-org/whisper.cpp:main-vulkan) that has regressed
# at least once mid-workshop-prep (May 2026: flash-attn + Blackwell crash,
# exit 132). Retagging lets compose use the known-good bundled image and
# skip the rebuild entirely.
for svc in stt frontend; do
  src_tag="workshop-mvp-spec-${svc}:latest"
  dst_tag="nodeava-workshop-${svc}:latest"
  if docker image inspect "$src_tag" >/dev/null 2>&1 \
     && ! docker image inspect "$dst_tag" >/dev/null 2>&1; then
    docker tag "$src_tag" "$dst_tag" && ok "retagged $src_tag → $dst_tag"
  fi
done

# ── 5. Stage Ollama models ─────────────────────────────────────────────────
step "Step 5 of 7 · Stage Ollama models"

OL_SRC="$USB_ROOT/ollama-models"

# Where does THIS machine's Ollama store models?
#
# On Linux/WSL2 the upstream installer creates an 'ollama' system user and
# runs the daemon under it via systemd; the daemon reads from
# /usr/share/ollama/.ollama/models — NOT $HOME/.ollama. Staging into $HOME
# silently fails: files land somewhere, daemon doesn't see them, `ollama list`
# returns empty, install.sh step 3 inventory marks models as missing, and
# step 6 falls through to `ollama pull` over the network — defeating the
# whole point of running setup.sh --offline.
#
# So: detect the daemon user first, and stage where the daemon will actually
# read from. Fall back to $HOME/.ollama for macOS / Ollama.app / no-systemd.
OL_DST=""
USE_SUDO=""
if [[ "$PLATFORM" =~ ^(linux|wsl2)$ ]] && id ollama >/dev/null 2>&1; then
  OL_DST="/usr/share/ollama/.ollama/models"
  USE_SUDO="sudo"
else
  for cand in "$HOME/.ollama/models" "/usr/share/ollama/.ollama/models" "/var/lib/ollama/.ollama/models"; do
    if [[ -d "$cand" ]]; then
      OL_DST="$cand"
      if [[ ! -w "$cand/blobs" ]] && [[ ! -w "$cand" ]]; then
        USE_SUDO="sudo"
      fi
      break
    fi
  done
fi

# Fallback: create user-local dir
if [[ -z "$OL_DST" ]]; then
  OL_DST="$HOME/.ollama/models"
  mkdir -p "$OL_DST/manifests" "$OL_DST/blobs"
fi

if [[ -d "$OL_SRC" ]]; then
  if [[ -n "$USE_SUDO" ]]; then
    warn "Ollama models dir is system-owned: $OL_DST"
    warn "Will use sudo to copy. You may be prompted for your password."
  fi
  $USE_SUDO mkdir -p "$OL_DST/manifests" "$OL_DST/blobs"

  # Copy manifests (small) — overwrite OK
  $USE_SUDO cp -R "$OL_SRC/manifests/." "$OL_DST/manifests/"

  # Copy blobs — skip if already present to save time
  copied=0
  for src in "$OL_SRC/blobs"/*; do
    [[ -f "$src" ]] || continue
    fname=$(basename "$src")
    if $USE_SUDO test -f "$OL_DST/blobs/$fname"; then
      :  # already cached on this machine
    else
      $USE_SUDO cp "$src" "$OL_DST/blobs/$fname"
      copied=$((copied+1))
    fi
  done

  # If we needed sudo, the systemd Ollama service runs as user 'ollama' —
  # fix ownership so the daemon can actually read the new files.
  if [[ -n "$USE_SUDO" ]]; then
    if id ollama >/dev/null 2>&1; then
      $USE_SUDO chown -R ollama:ollama "$OL_DST"
    fi
  fi

  ok "models staged to $OL_DST ($copied new blobs)"
  ollama list || true
else
  warn "no Ollama models on USB — you'll need to 'ollama pull qwen3:4b-instruct' manually"
fi

# ── 6. Stage source tree + whisper models ──────────────────────────────────
step "Step 6 of 7 · Stage source tree"

SRC_DST="$HOME/nodeava-workshop"
SRC_FROM="$USB_ROOT/source/nodeava-workshop"

if [[ -d "$SRC_DST" ]]; then
  warn "$SRC_DST already exists"
  read -r -p "Overwrite? (y/N) " yn
  if [[ "$yn" =~ ^[Yy]$ ]]; then
    rm -rf "$SRC_DST"
  else
    say "Keeping existing $SRC_DST — skipping copy"
    SRC_FROM=""
  fi
fi

if [[ -n "$SRC_FROM" ]]; then
  cp -R "$SRC_FROM" "$SRC_DST"
  ok "source copied to $SRC_DST"
fi

# Whisper models go into the project's models/ dir (mounted into STT container)
mkdir -p "$SRC_DST/models"
for w in "$USB_ROOT"/whisper-models/*.bin; do
  [[ -f "$w" ]] || continue
  cp -n "$w" "$SRC_DST/models/" && ok "whisper: $(basename "$w")"
done

# ── 7. Hand off to the installer wizard ────────────────────────────────────
step "Step 7 of 7 · Running install wizard"

cd "$SRC_DST"
chmod +x install.sh scripts/install.sh scripts/install/*.sh 2>/dev/null || true

# install.sh normally lives at the project root; older snapshots only have
# scripts/install.sh. Pick whichever exists so the hand-off never fails.
INSTALL_ENTRY=""
if [[ -x "./install.sh" ]]; then
  INSTALL_ENTRY="./install.sh"
elif [[ -x "./scripts/install.sh" ]]; then
  INSTALL_ENTRY="./scripts/install.sh"
else
  fail "Neither ./install.sh nor ./scripts/install.sh found in $SRC_DST"
fi

cat <<EOF

The base setup is complete. Now handing off to install.sh, which will:

  1. Welcome banner
  2. Preflight (platform / GPU / Docker / disk / network / ports)
  3. Inventory (Keep / Reset / Selective)
  4. LLM backend choice (Ollama default; llama.cpp opt-in)
  5. Install Ollama if needed (already done)
  6. Pull workshop models (already done via USB)
  7. Build the orchestrator image (uses pre-loaded Docker layers)
  8. Bring up the stack
  9. Smoke verify

EOF
read -r -p "Press <Enter> to run install.sh, or Ctrl-C to do it manually later … "
exec "$INSTALL_ENTRY"
