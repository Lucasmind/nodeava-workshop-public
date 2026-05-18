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
  # nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
  output=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1)
  IFS=',' read -r gpu_name vram_mb <<< "$output"
  gpu_name=$(echo "$gpu_name" | sed 's/^ *//;s/ *$//')  # Trim whitespace
  vram_mb=$(echo "$vram_mb" | sed 's/^ *//;s/ *$//')    # Trim whitespace
  if [[ -n "$gpu_name" ]]; then
    NODEAVA_GPU="$gpu_name"
    NODEAVA_VRAM_MB="$vram_mb"
  fi
fi
if [[ -z "$NODEAVA_GPU" ]] && has_command rocm-smi; then
  NODEAVA_GPU="$(rocm-smi --showproductname 2>/dev/null | grep -i 'card series' | head -1 | sed 's/.*: //')"
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
# Check the partition containing $HOME (where ~/.ollama lives)
disk_avail_gb=$(df -BG "$HOME" 2>/dev/null | awk 'NR==2{gsub("G","",$4); print $4}')
if [[ -z "$disk_avail_gb" ]]; then
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
