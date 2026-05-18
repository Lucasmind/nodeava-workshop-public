#!/bin/bash
# Wizard step 8: bring up the docker stack.

step_heading 8 9 "Bring up the stack"

say "  Starting five services:"
say "    • frontend      — Vite-built dashboard served by nginx (port 3000)"
say "    • orchestrator  — the agentic-loop brain (port 8082)"
say "    • tts           — Kokoro neural text-to-speech (port 8880)"
say "    • stt           — Whisper speech-to-text (port 8080)"
say "    • searxng       — bundled meta-search for the browser tool"
say ""
say "  Ollama is on your host (not in Docker) and serves the LLM at :11434."
echo

# Pick GPU overlay (same logic as build step)
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
  mac) gpu_overlay="" ;;
  *) gpu_overlay="" ;;
esac

override_overlay=""
if [[ -f "$NODEAVA_REPO_ROOT/docker-compose.override.yml" ]]; then
  override_overlay="-f docker-compose.override.yml"
fi

cd "$NODEAVA_REPO_ROOT"
info "Starting services ..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $gpu_overlay $override_overlay up -d orchestrator tts stt searxng frontend

# Wait for healthy. Loop up to 60s.
# A line is OK if Health is "healthy" OR empty (service has no healthcheck —
# e.g. searxng before it implements one, or the frontend nginx container).
# A line is BLOCKING if Health is "starting" or "unhealthy".
deadline=$(( $(date +%s) + 60 ))
while true; do
  blocking="$(docker compose -f docker-compose.yml $gpu_overlay $override_overlay ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -E ' (starting|unhealthy)$' || true)"
  [[ -z "$blocking" ]] && break
  if [[ "$(date +%s)" -gt "$deadline" ]]; then
    warn "Some services did not become healthy within 60s:"
    echo "$blocking"
    break
  fi
  sleep 2
done
ok "Stack is up."
pause
