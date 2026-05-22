#!/bin/bash
# Wizard step 7: build the project's first-party container images.
#
# Linux/WSL2 attendees got pre-built images via setup.sh step 4 (loaded
# from the USB's docker-images/amd64/), so we only need to (re)build the
# orchestrator here in case the user's repo HEAD differs from the bundle.
#
# Mac attendees have NO pre-built arm64 images for orchestrator/frontend
# (the USB only ships arm64 versions of third-party images: searxng and
# kokoro-fastapi-gpu). We build both from source on Mac.

step_heading 7 9 "Build first-party images"

if [[ "${NODEAVA_INV_IMAGE:-missing}" = "keep" ]] \
   && [[ "$NODEAVA_PLATFORM" != "mac" ]]; then
  ok "nodeava-orch:latest already built — skipping (Inventory said Keep)."
  pause
  return 0
fi

say "  Why this matters: the orchestrator is the agentic-loop brain. It"
say "  receives chat requests, decides which tools to call (wiki / web /"
say "  ingest), routes to the active LLM brain, and streams events back"
say "  to the dashboard."
if [[ "$NODEAVA_PLATFORM" = "mac" ]]; then
  say "  On Apple Silicon we also build the frontend image (with the lab"
  say "  pages baked in) — no arm64 frontend tarball ships in the kit."
fi
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

# Inject Mac overlay so `build` sees stt/tts assigned to the linux profile
# and skips them (they run natively on Mac via Metal/MPS, not Docker).
# Without this, compose 2.36+ BuildKit bake mode evaluates all services
# and tries to build stt/tts unnecessarily.
mac_overlay=""
[[ "$NODEAVA_PLATFORM" = "mac" ]] && mac_overlay="-f docker-compose.mac.yml"

# Build list — orchestrator always; add frontend on Mac (no arm64 image ships).
if [[ "$NODEAVA_PLATFORM" = "mac" ]]; then
  build_services=(orchestrator frontend)
  build_label="orchestrator + frontend (Mac builds frontend from source)"
else
  build_services=(orchestrator)
  build_label="orchestrator"
fi

cd "$NODEAVA_REPO_ROOT"
info "Building $build_label (this can take 1-4 min on first run) ..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $mac_overlay $gpu_overlay $override_overlay build "${build_services[@]}"
ok "Built: ${build_services[*]}"
pause
