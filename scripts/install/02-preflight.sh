#!/bin/bash
# Wizard step 2: preflight. Five system checks before any install action.

step_heading 2 9 "Preflight — verifying your machine"

say "  Why this matters: the workshop expects a few baseline conditions."
say "  Catching problems here saves time later (a captive-wifi portal at"
say "  hour 1 ruins the rest of the session)."
echo

# --- Check 1: platform ---
detect_platform
case "$NODEAVA_PLATFORM" in
  linux)     ok "Platform: Linux $(uname -m) (kernel $(uname -r | cut -d- -f1))" ;;
  linux-wsl) ok "Platform: WSL2 (Linux on Windows)" ;;
  mac)       ok "Platform: macOS $(sw_vers -productVersion 2>/dev/null || echo unknown)" ;;
  unsupported) fail "Unsupported platform ($(uname -s)). The workshop supports Linux, WSL2, and macOS." ;;
esac

# --- Check 2: GPU + VRAM ---
NODEAVA_GPU=""
NODEAVA_VRAM_MB=0
if has_command nvidia-smi; then
  # nvidia-smi may be installed without an active GPU (hybrid laptops, stale
  # driver, undocked workstations). Two traps:
  #   1. nvidia-smi exits non-zero (e.g., 6 = "No devices were found"). Combined
  #      with `set -e -o pipefail` in install.sh this aborts the wizard, so we
  #      run it via `if` to swallow the status.
  #   2. The same "No devices were found" string is written to STDOUT, not
  #      stderr — so we can't trust the captured text just because it's
  #      non-empty. Require `vram_mb` to parse as an integer before using it.
  if output=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1); then
    IFS=',' read -r gpu_name vram_mb <<< "$output"
    gpu_name=$(echo "$gpu_name" | sed 's/^ *//;s/ *$//')
    vram_mb=$(echo "$vram_mb"   | sed 's/^ *//;s/ *$//')
    if [[ -n "$gpu_name" ]] && [[ "$vram_mb" =~ ^[0-9]+$ ]]; then
      NODEAVA_GPU="$gpu_name"
      NODEAVA_VRAM_MB="$vram_mb"
    fi
  fi
fi
if [[ -z "$NODEAVA_GPU" ]] && has_command rocm-smi; then
  # Same guard as nvidia-smi: grep returns 1 with no match → pipefail aborts.
  NODEAVA_GPU="$(rocm-smi --showproductname 2>/dev/null | grep -i 'card series' | head -1 | sed 's/.*: //' || true)"
  NODEAVA_VRAM_MB="$(rocm-smi --showmeminfo vram --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(iter(d.values()))["VRAM Total Memory (B)"] // 1024 // 1024)' 2>/dev/null || echo 0)"
fi
if [[ "$NODEAVA_PLATFORM" = "mac" ]] && [[ -z "$NODEAVA_GPU" ]]; then
  # Apple Silicon — unified memory; report system memory minus reserved
  NODEAVA_GPU="Apple Silicon (Metal, unified memory)"
  NODEAVA_VRAM_MB=$(($(sysctl -n hw.memsize) / 1024 / 1024))
fi
export NODEAVA_GPU NODEAVA_VRAM_MB

if [[ -n "$NODEAVA_GPU" ]]; then
  if [[ "$NODEAVA_VRAM_MB" -ge 8192 ]]; then
    ok "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB (workshop floor is 8192 MB)"
  elif [[ "$NODEAVA_VRAM_MB" -ge 6144 ]]; then
    warn "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB — below the 8 GB workshop floor; expect slow inference"
  else
    warn "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB — significantly below 8 GB; consider CPU mode or a smaller model"
  fi
else
  warn "GPU: none detected — Ollama will run on CPU (slower; smollm2 still usable)"
fi

# --- Blackwell detection ---
# Kokoro-FastAPI v0.2.x / v0.3.0 GPU images bundle PyTorch <2.6, which has
# no precompiled CUDA kernels for sm_120 (Blackwell, RTX 50-series and the
# RTX PRO Blackwell line). The container fails warmup with "CUDA error: no
# kernel image is available for execution on the device".
#
# When we see a Blackwell GPU, set a flag so step 8 auto-writes a
# docker-compose.override.yml that pins the CPU TTS image. Voice quality is
# identical; latency goes from ~0.5s/sentence to ~2-5s/sentence.
NODEAVA_GPU_BLACKWELL=0
if has_command nvidia-smi && [[ -n "$NODEAVA_GPU" ]]; then
  compute_cap="$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | tr -d ' \r' || true)"
  case "$compute_cap" in
    12.*|13.*|14.*|15.*)
      NODEAVA_GPU_BLACKWELL=1
      warn "Blackwell-class GPU (compute cap ${compute_cap}) — Kokoro TTS GPU image lacks sm_120 kernels."
      warn "  Step 8 will auto-pin the CPU TTS image (~2-5s/sentence vs <0.5s on GPU)."
      ;;
  esac
fi
export NODEAVA_GPU_BLACKWELL

# --- NVIDIA Container Toolkit (required for ANY NVIDIA GPU, including Blackwell) ---
# The gpu-nvidia overlay reserves 'driver: nvidia' devices on BOTH tts and stt.
# tts is bypassed on Blackwell (override → CPU image), but stt still uses GPU
# via Vulkan (whisper.cpp Vulkan backend works fine on sm_120 — only PyTorch's
# precompiled CUDA kernels are the Blackwell problem). So the toolkit is
# required whenever there's an NVIDIA GPU, Blackwell or not.
#
# Without nvidia-container-toolkit installed + `nvidia-ctk runtime configure`,
# `docker compose up` errors at step 8:
#   "could not select device driver "nvidia" with capabilities: [[gpu]]"
# Catching that here saves a confusing failure at step 8 and points the user
# at the exact fix.
if [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ NVIDIA ]]; then
  if docker info 2>/dev/null | grep -qE '^ Runtimes:[^[:cntrl:]]* nvidia( |$)'; then
    ok "Docker nvidia runtime registered"
  else
    warn "Docker nvidia runtime NOT registered — containers cannot use the GPU."
    warn "  stt (whisper.cpp Vulkan) needs the runtime even on Blackwell."
    if [[ "$NODEAVA_PLATFORM" = "linux-wsl" ]]; then
      warn "  (WSL2) Prerequisites on the Windows side:"
      warn "    • Recent NVIDIA Game Ready or Studio driver (includes WSL CUDA)"
      warn "    • WSL kernel ≥ 5.10.43 — run 'wsl --update' in Windows PowerShell"
      warn "  Then the kit will install nvidia-container-toolkit inside this WSL distro."
    fi
    nvctk_installer="$NODEAVA_REPO_ROOT/scripts/install-nvidia-container-toolkit.sh"
    if [[ -x "$nvctk_installer" ]] && prompt_yn "Install nvidia-container-toolkit now? (needs internet + sudo password)"; then
      echo
      if bash "$nvctk_installer"; then
        echo
        # Re-check Docker runtime list after the install + daemon restart
        if docker info 2>/dev/null | grep -qE '^ Runtimes:[^[:cntrl:]]* nvidia( |$)'; then
          ok "Docker nvidia runtime now registered — continuing preflight"
        else
          fail "Toolkit installer ran but Docker still has no 'nvidia' runtime — check /etc/docker/daemon.json"
        fi
      else
        fail "Toolkit installer failed — see output above"
      fi
    else
      warn "Manual install (also at $nvctk_installer):"
      warn "    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \\"
      warn "      | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg"
      warn "    echo 'deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://nvidia.github.io/libnvidia-container/stable/deb/amd64 /' \\"
      warn "      | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list"
      warn "    sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit"
      warn "    sudo nvidia-ctk runtime configure --runtime=docker && sudo systemctl restart docker"
      fail "GPU runtime missing — install nvidia-container-toolkit and re-run ./install.sh"
    fi
  fi
fi

# --- Check 3: Docker reachable ---
if ! has_command docker; then
  fail "Docker not installed. Install Docker Desktop (mac) or docker.io (Linux) and re-run."
fi
if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon not reachable. Start Docker Desktop / 'sudo systemctl start docker' and re-run."
fi
docker_version="$(docker --version | awk '{print $3}' | sed 's/,$//')"
ok "Docker: reachable (version $docker_version)"

# --- Check 4: Disk free ---
# Check the partition containing $HOME (where ~/.ollama lives).
# `df -BG` is a GNU coreutils extension; macOS ships BSD `df` which rejects
# it. Use `-k` (POSIX, kibibytes) and convert in shell arithmetic.
disk_avail_kb=$(df -k "$HOME" 2>/dev/null | awk 'NR==2{print $4}')
disk_avail_gb=$(( ${disk_avail_kb:-0} / 1048576 ))
if [[ "$disk_avail_gb" -eq 0 ]]; then
  warn "Disk: could not determine free space"
elif [[ "$disk_avail_gb" -lt 5 ]]; then
  fail "Disk: ${disk_avail_gb} GB free on $HOME's partition. The workshop needs at least 5 GB."
elif [[ "$disk_avail_gb" -lt 10 ]]; then
  warn "Disk: ${disk_avail_gb} GB free — tight but workable (workshop needs ~10 GB ideally)"
else
  ok "Disk: ${disk_avail_gb} GB free on $HOME's partition"
fi

# --- Check 5: Network ---
if curl --max-time 5 -fsS https://ollama.com -o /dev/null 2>/dev/null; then
  ok "Network: ollama.com reachable"
else
  warn "Network: ollama.com unreachable (captive portal? offline?). If models are already pulled the wizard can still proceed."
fi

# --- Check 6: Required ports available ---
# We check 5 host-bound ports. Ours-on-re-run is fine; anything else conflicts.
port_in_use() {
  local p="$1"
  if has_command ss; then
    ss -tln 2>/dev/null | awk '{print $4}' | grep -qE "[:.]${p}\$"
  elif has_command lsof; then
    lsof -iTCP:"$p" -sTCP:LISTEN -P -n 2>/dev/null | grep -q LISTEN
  else
    timeout 1 bash -c "exec 3<>/dev/tcp/127.0.0.1/$p" 2>/dev/null
  fi
}
service_running() {
  docker compose ps -q "$1" 2>/dev/null | grep -q .
}

NODEAVA_PORT_CONFLICTS=0
for entry in \
    "${FRONTEND_PORT:-3000}:frontend:FRONTEND_PORT" \
    "${STT_PORT:-8080}:stt:STT_PORT" \
    "8082:orchestrator:" \
    "${TTS_PORT:-8880}:tts:TTS_PORT" \
    "11434:ollama:"; do
  IFS=: read -r port svc envvar <<< "$entry"
  if port_in_use "$port"; then
    if [[ "$svc" = "ollama" ]]; then
      ok "Port $port: Ollama already running (expected — host-native)"
    elif service_running "$svc"; then
      ok "Port $port: held by our $svc container (re-run, fine)"
    else
      if [[ -n "$envvar" ]]; then
        warn "Port $port in use by something other than NodeAva. Set $envvar=<other> and re-run, or stop the conflicting service."
      else
        warn "Port $port (orchestrator) in use; orchestrator has no env-var override. Stop the conflicting service before continuing."
      fi
      NODEAVA_PORT_CONFLICTS=$((NODEAVA_PORT_CONFLICTS+1))
    fi
  else
    ok "Port $port: free for $svc"
  fi
done
if [[ "$NODEAVA_PORT_CONFLICTS" -gt 0 ]]; then
  warn "$NODEAVA_PORT_CONFLICTS port conflict(s) detected — 'docker compose up -d' will fail at step 8 unless you resolve them."
fi
export NODEAVA_PORT_CONFLICTS

echo
say "All preflight checks complete."
pause
