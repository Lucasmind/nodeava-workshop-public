#!/usr/bin/env bash
# Install + configure the NVIDIA Container Toolkit so Docker can pass the
# GPU into containers (required by docker-compose.gpu-nvidia.yml).
#
# Idempotent — safe to re-run. Needs internet + sudo.
# Invoked automatically by scripts/install/02-preflight.sh when the docker
# nvidia runtime is missing and the user accepts the auto-install prompt.
set -euo pipefail

KEYRING=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
LISTFILE=/etc/apt/sources.list.d/nvidia-container-toolkit.list

# NVIDIA publishes amd64 and arm64 deb repos; pick the right one for this host.
# (NVIDIA GPU architecture — Ampere/Hopper/Blackwell/etc. — is unrelated;
# the toolkit is the same userland regardless of GPU compute capability.)
case "$(uname -m)" in
  x86_64)        ARCH=amd64 ;;
  aarch64|arm64) ARCH=arm64 ;;
  *) echo "Unsupported CPU architecture: $(uname -m). NVIDIA Container Toolkit debs are published for amd64 and arm64 only." >&2; exit 1 ;;
esac

say()  { printf "\033[1;36m== %s\033[0m\n" "$*"; }
ok()   { printf "  \033[1;32m✓\033[0m %s\n" "$*"; }
warn() { printf "  \033[1;33m!\033[0m %s\n" "$*"; }

command -v apt-get >/dev/null || { echo "apt-get not found — this script targets Debian/Ubuntu."; exit 1; }
command -v docker  >/dev/null || { echo "docker not installed — install Docker first."; exit 1; }

# Already installed and runtime registered? Bail early.
if dpkg -s nvidia-container-toolkit >/dev/null 2>&1 \
   && docker info 2>/dev/null | grep -q ' nvidia '; then
  ok "nvidia-container-toolkit already installed and registered with Docker"
  docker info 2>/dev/null | grep -iE 'runtimes:' | sed 's/^/    /'
  exit 0
fi

say "1/5  Adding NVIDIA keyring"
if [[ ! -s "$KEYRING" ]]; then
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
    | sudo gpg --dearmor -o "$KEYRING"
  ok "keyring written to $KEYRING"
else
  ok "keyring already present"
fi

say "2/5  Adding apt source"
LINE="deb [signed-by=$KEYRING] https://nvidia.github.io/libnvidia-container/stable/deb/$ARCH /"
if [[ -s "$LISTFILE" ]] && grep -qF "$LINE" "$LISTFILE"; then
  ok "apt source already present"
else
  echo "$LINE" | sudo tee "$LISTFILE" >/dev/null
  ok "apt source written to $LISTFILE"
fi

say "3/5  Installing nvidia-container-toolkit"
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y nvidia-container-toolkit
ok "package installed: $(dpkg-query -W -f='${Version}' nvidia-container-toolkit)"

say "4/5  Configuring Docker runtime"
sudo nvidia-ctk runtime configure --runtime=docker
ok "/etc/docker/daemon.json updated"

say "5/5  Restarting Docker"
sudo systemctl restart docker
for _ in 1 2 3 4 5 6 7 8 9 10; do
  docker info >/dev/null 2>&1 && break
  sleep 1
done
docker info >/dev/null 2>&1 || { warn "Docker didn't come back up — check 'sudo systemctl status docker'"; exit 1; }
ok "Docker is back"

echo
say "Verifying"
runtimes_line="$(docker info 2>/dev/null | grep -iE 'runtimes:' || true)"
echo "  $runtimes_line"
if echo "$runtimes_line" | grep -qw nvidia; then
  ok "nvidia runtime registered"
else
  warn "nvidia runtime NOT in the Runtimes list — daemon.json may not have been read."
  exit 1
fi

echo
say "Smoke test: docker run --rm --gpus all ubuntu:24.04 nvidia-smi"
# Capture first to avoid SIGPIPE+pipefail false-fail when grep -q matches.
smoke_out="$(docker run --rm --gpus all ubuntu:24.04 nvidia-smi 2>&1)" || true
echo "$smoke_out"
if grep -q 'NVIDIA-SMI' <<< "$smoke_out"; then
  ok "containers can see the GPU"
else
  warn "smoke test failed — see output above"
  exit 1
fi
