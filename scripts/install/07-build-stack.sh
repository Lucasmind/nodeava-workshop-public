#!/bin/bash
# Wizard step 7: build the orchestrator image.

step_heading 7 9 "Build orchestrator image"

if [[ "${NODEAVA_INV_IMAGE:-missing}" = "keep" ]]; then
  ok "nodeava-orch:latest already built — skipping (Inventory said Keep)."
  pause
  return 0
fi

say "  Why this matters: the orchestrator is the agentic-loop brain. It"
say "  receives chat requests, decides which tools to call (wiki / web /"
say "  ingest), routes to the active LLM brain, and streams events back"
say "  to the dashboard."
echo

# Pick GPU overlay
case "$NODEAVA_PLATFORM" in
  linux|linux-wsl)
    if [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ NVIDIA ]]; then
      gpu_overlay="-f docker-compose.gpu-nvidia.yml"
    elif [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ (AMD|Radeon) ]]; then
      gpu_overlay="-f docker-compose.gpu-amd.yml"
    else
      gpu_overlay=""
    fi
    ;;
  mac)
    gpu_overlay=""
    ;;
  *) gpu_overlay="" ;;
esac

# Pick up a local override if present (e.g., dev mounts)
override_overlay=""
if [[ -f "$NODEAVA_REPO_ROOT/docker-compose.override.yml" ]]; then
  override_overlay="-f docker-compose.override.yml"
fi

cd "$NODEAVA_REPO_ROOT"
info "Building orchestrator image (this can take 1-2 min on first run) ..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $gpu_overlay $override_overlay build orchestrator
ok "nodeava-orch:latest built."
pause
