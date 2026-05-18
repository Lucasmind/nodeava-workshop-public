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
│     2. Install Docker Desktop if missing (run from USB)         │
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

# ── 2. Docker Desktop ──────────────────────────────────────────────────────
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
    wsl2)
      EXE="$USB_ROOT/installers/DockerDesktop-Win.exe"
      if [[ -f "$EXE" ]]; then
        warn "Docker Desktop is a Windows-side install."
        echo "    1. Open Windows Explorer to the USB drive"
        echo "    2. Run '$EXE'"
        echo "    3. Reboot if prompted (Docker enables WSL2 integration)"
        echo "    4. Launch Docker Desktop, accept the EULA"
        echo "    5. Re-run this script from WSL2: cd $USB_ROOT && ./setup.sh"
        fail "Docker Desktop install required"
      else
        fail "Docker Desktop installer not found at $EXE"
      fi
      ;;
    linux)
      warn "Docker isn't installed."
      echo "    Try:  sudo apt-get install -y docker.io docker-compose-plugin"
      echo "    Or:   curl -fsSL https://get.docker.com | sh"
      echo "    Then: sudo usermod -aG docker \$USER && newgrp docker"
      fail "Install Docker via your distro, then re-run ./setup.sh"
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
    wsl2)
      warn "Run the Ollama Windows installer from Windows Explorer:"
      echo "    $USB_ROOT/installers/Ollama-Win.exe"
      echo "Then re-run this script from WSL2."
      fail "Ollama Windows install required"
      ;;
    linux)
      SH="$USB_ROOT/installers/ollama-linux-install.sh"
      if [[ -f "$SH" ]]; then
        say "Running Linux Ollama installer (may prompt for sudo)…"
        bash "$SH" || warn "Ollama install reported errors — try again or install manually"
      else
        fail "Linux Ollama installer not found"
      fi
      ;;
  esac
fi

# Verify Ollama is reachable
if ! curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null; then
  warn "Ollama daemon not responding on :11434"
  case "$PLATFORM" in
    mac) say "Launch Ollama.app from /Applications/ (it lives in the menubar), then re-run ./setup.sh" ;;
    linux) say "Start the daemon:  ollama serve   (or systemd: sudo systemctl start ollama)" ;;
    wsl2) say "Start Ollama on Windows (it should auto-start a menubar agent)" ;;
  esac
  fail "Ollama daemon must be running before continuing"
else
  ok "Ollama daemon reachable on :11434"
fi

# ── 4. Load Docker images ──────────────────────────────────────────────────
step "Step 4 of 7 · Load Docker images"

IMG_DIR="$USB_ROOT/docker-images/$PLATFORM_ARCH"
if [[ ! -d "$IMG_DIR" ]]; then
  fail "No Docker image tarballs for architecture $PLATFORM_ARCH at $IMG_DIR"
fi

count=0
for tar in "$IMG_DIR"/*.tar; do
  [[ -f "$tar" ]] || continue
  size="$(du -h "$tar" | cut -f1)"
  say "  loading $(basename "$tar") ($size)…"
  if docker load -i "$tar" >/dev/null; then
    ok "loaded $(basename "$tar")"
    count=$((count+1))
  else
    warn "load failed for $(basename "$tar")"
  fi
done
ok "$count image(s) loaded"

# ── 5. Stage Ollama models ─────────────────────────────────────────────────
step "Step 5 of 7 · Stage Ollama models"

OL_SRC="$USB_ROOT/ollama-models"

# Where does THIS machine's Ollama store models? Try the standard locations
# in order and use the first one that exists with the right ownership.
OL_DST=""
USE_SUDO=""
for cand in "$HOME/.ollama/models" "/usr/share/ollama/.ollama/models" "/var/lib/ollama/.ollama/models"; do
  if [[ -d "$cand" ]]; then
    OL_DST="$cand"
    # Determine if we need sudo to write here
    if [[ ! -w "$cand/blobs" ]] && [[ ! -w "$cand" ]]; then
      USE_SUDO="sudo"
    fi
    break
  fi
done

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
chmod +x install.sh scripts/install/*.sh 2>/dev/null || true

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
exec ./install.sh
