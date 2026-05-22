#!/usr/bin/env bash
# Installs Docker Engine + Compose plugin on Linux.
#
# Hybrid strategy:
#   1. If we can reach download.docker.com quickly, use the official
#      get.docker.com installer (covers every common distro, latest stable).
#   2. Otherwise, fall back to the static binaries bundled on the USB
#      (docker-static-amd64.tgz + docker-compose-linux-amd64). Distro-
#      agnostic — works on Ubuntu/Debian/Fedora/Arch/Zorin/Pop/etc.
#
# Usage:  sudo ./install-docker.sh
# Flags:  --offline    skip the online attempt, go straight to USB tarballs
#         --online     skip the offline fallback (fail if no network)

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET_USER="${SUDO_USER:-}"
ARCH="$(uname -m)"
MODE="auto"

for arg in "$@"; do
  case "$arg" in
    --offline) MODE="offline" ;;
    --online)  MODE="online" ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (use sudo)." >&2
  exit 1
fi

if [[ "$ARCH" != "x86_64" ]]; then
  echo "This installer only ships an amd64 bundle. Detected: $ARCH" >&2
  echo "Use your distro's docker package, or 'curl -fsSL https://get.docker.com | sh'." >&2
  exit 1
fi

# ── Reachability probe (3s timeout). Treat slow/no-response as "offline".
online() {
  curl -fsS --max-time 3 -o /dev/null https://download.docker.com/linux/ 2>/dev/null
}

# ── Online path ────────────────────────────────────────────────────────────
install_online() {
  echo "==> Online install via get.docker.com"
  if ! command -v curl >/dev/null 2>&1; then
    apt-get update -qq && apt-get install -y curl ca-certificates
  fi
  curl -fsSL https://get.docker.com | sh
}

# ── Offline path (bundled static binaries) ─────────────────────────────────
install_offline() {
  local docker_tgz="$HERE/docker-static-amd64.tgz"
  local compose_bin="$HERE/docker-compose-linux-amd64"
  echo "==> Offline install from USB tarballs"
  [[ -f "$docker_tgz" ]]  || { echo "Missing: $docker_tgz" >&2; return 1; }
  [[ -f "$compose_bin" ]] || { echo "Missing: $compose_bin" >&2; return 1; }

  echo "  - extracting $(basename "$docker_tgz") → /usr/local/bin"
  tar -xzf "$docker_tgz" -C /tmp/
  install -m 0755 /tmp/docker/* /usr/local/bin/
  rm -rf /tmp/docker

  echo "  - installing compose plugin → /usr/local/lib/docker/cli-plugins"
  install -d -m 0755 /usr/local/lib/docker/cli-plugins
  install -m 0755 "$compose_bin" /usr/local/lib/docker/cli-plugins/docker-compose

  # The static tarball doesn't ship systemd units. Write minimal ones.
  echo "  - writing systemd units (containerd.service, docker.socket, docker.service)"
  if ! getent group docker >/dev/null; then groupadd --system docker; fi

  cat > /etc/systemd/system/containerd.service <<'UNIT'
[Unit]
Description=containerd container runtime
Documentation=https://containerd.io
After=network.target local-fs.target

[Service]
ExecStartPre=-/sbin/modprobe overlay
ExecStart=/usr/local/bin/containerd
Type=notify
Delegate=yes
KillMode=process
Restart=always
RestartSec=5
LimitNPROC=infinity
LimitCORE=infinity
LimitNOFILE=1048576
TasksMax=infinity
OOMScoreAdjust=-999

[Install]
WantedBy=multi-user.target
UNIT

  cat > /etc/systemd/system/docker.socket <<'UNIT'
[Unit]
Description=Docker Socket for the API

[Socket]
ListenStream=/var/run/docker.sock
SocketMode=0660
SocketUser=root
SocketGroup=docker

[Install]
WantedBy=sockets.target
UNIT

  cat > /etc/systemd/system/docker.service <<'UNIT'
[Unit]
Description=Docker Application Container Engine
Documentation=https://docs.docker.com
After=network-online.target docker.socket containerd.service
Wants=network-online.target
Requires=docker.socket containerd.service

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd -H fd:// --containerd=/run/containerd/containerd.sock
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
StartLimitBurst=3
StartLimitInterval=60s
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
UNIT

  systemctl daemon-reload
  systemctl enable --now containerd.service docker.socket docker.service
}

# ── Decide ─────────────────────────────────────────────────────────────────
case "$MODE" in
  online)
    install_online
    ;;
  offline)
    install_offline || { echo "Offline install failed." >&2; exit 1; }
    ;;
  auto)
    if online; then
      echo "==> Network reachable — preferring online installer"
      if install_online; then
        :
      else
        echo "==> Online installer failed, falling back to USB bundle"
        install_offline || { echo "Both online and offline installs failed." >&2; exit 1; }
      fi
    else
      echo "==> No connection to download.docker.com (3s timeout) — using USB bundle"
      install_offline || { echo "Offline install failed." >&2; exit 1; }
    fi
    ;;
esac

# ── Post-install: docker group + verify ────────────────────────────────────
if [[ -n "$TARGET_USER" && "$TARGET_USER" != "root" ]]; then
  if ! id -nG "$TARGET_USER" | tr ' ' '\n' | grep -qx docker; then
    usermod -aG docker "$TARGET_USER"
    echo "  - added $TARGET_USER to the 'docker' group (effective on next login)"
  fi
fi

echo
echo "==> Versions"
docker --version || true
docker compose version || true

echo
echo "Done. To use docker without sudo in this shell:  sg docker -c '<command>'"
echo "Or log out and back in so the group membership takes effect."
