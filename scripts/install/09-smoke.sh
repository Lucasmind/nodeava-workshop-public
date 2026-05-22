#!/bin/bash
# Wizard step 9: smoke verify + final message.

step_heading 9 9 "Smoke verify"

say "  Why this matters: we confirm the orchestrator can load the catalog,"
say "  reach Ollama, and respond to /v1/state queries. If any check fails,"
say "  the recovery hint points to the most likely cause."
echo

failures=0

# Probe 1: /v1/state
if curl --max-time 5 -fsS http://localhost:8082/v1/state >/dev/null 2>&1; then
  ok "orchestrator /v1/state reachable"
else
  warn "orchestrator /v1/state failed — is the container healthy? 'docker logs nodeava-orch'"
  failures=$((failures+1))
fi

# Probe 2: /v1/catalog has brains
brains_count="$(curl --max-time 5 -fsS http://localhost:8082/v1/catalog 2>/dev/null \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("brains",[])))' 2>/dev/null || echo 0)"
if [[ "$brains_count" -ge 2 ]]; then
  ok "/v1/catalog returns $brains_count brains"
else
  warn "/v1/catalog returned $brains_count brains — catalog file may be malformed"
  failures=$((failures+1))
fi

# Probe 3: Ollama reachable from the orchestrator's perspective
# We probe from the host as a proxy — same host network
if curl --max-time 5 -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama /api/tags reachable from host"
else
  warn "Ollama not reachable at :11434"
  failures=$((failures+1))
fi

# Probe 4: STT — direct port 8080
# Catches the case where stt's container failed to start (e.g., missing
# nvidia-container-toolkit on a non-Blackwell NVIDIA system) but orchestrator
# came up anyway — without this probe, smoke says "all passed" while the
# dashboard is unusable.
if curl --max-time 5 -fsS http://localhost:8080/ >/dev/null 2>&1; then
  ok "STT (whisper.cpp) reachable on :8080"
else
  warn "STT not reachable at :8080 — 'docker logs nodeava-workshop-stt-1'"
  failures=$((failures+1))
fi

# Probe 5: TTS — direct port 8880
if curl --max-time 5 -fsS http://localhost:8880/v1/models >/dev/null 2>&1; then
  ok "TTS (Kokoro) reachable on :8880"
else
  warn "TTS not reachable at :8880 — 'docker logs nodeava-workshop-tts-1'"
  failures=$((failures+1))
fi

# Probe 6: frontend — dashboard wouldn't load without it
frontend_port="${FRONTEND_PORT:-3000}"
if curl --max-time 5 -fsS "http://localhost:${frontend_port}/" >/dev/null 2>&1; then
  ok "Frontend dashboard reachable on :${frontend_port}"
else
  warn "Frontend not reachable at :${frontend_port} — 'docker logs nodeava-workshop-frontend-1'"
  warn "  Common cause: stt/tts didn't become healthy → frontend's depends_on prevented creation."
  failures=$((failures+1))
fi

# Probe 7: full end-to-end through nginx — the dashboard's actual fetch path
if curl --max-time 5 -fsS "http://localhost:${frontend_port}/api/orch/v1/state" >/dev/null 2>&1; then
  ok "Dashboard → orchestrator path (/api/orch/) works through nginx"
else
  warn "/api/orch/v1/state failed through nginx — dashboard will render 'offline'"
  warn "  Check frontend/nginx.conf has 'location /api/orch/' pointing at orchestrator:8082"
  failures=$((failures+1))
fi

echo
if [[ "$failures" -gt 0 ]]; then
  warn "$failures probe(s) failed. The stack is up but something is off."
  warn "Re-running ./install.sh will retry; or check 'docker compose logs'."
  exit 1
fi

# Final message
echo
printf "%b%s%b\n" "$C_GREEN" "✓ All smoke checks passed." "$C_RESET"
echo
frontend_port="${FRONTEND_PORT:-3000}"
cat <<EOF
You're ready. Open http://localhost:${frontend_port} in your browser. The drawer toggle
is the small button at the top-right; press ] to toggle, or click it.

Try saying (or typing): "What ports does NodeAva use?" The avatar will call
the wiki tool and answer with real ports cited from the page.

To stop the stack:    docker compose down
To re-run the wizard: ./install.sh
To force fresh install: ./install.sh --full-reset

Workshop pedagogy moments to demo:
  • Open the drawer → see Brain / Voice / Avatar / Personality / Tools
  • Swap Brain to "Qwen3 4B Thinking" → ask the same question → see the
    flow diagram show the thinking phase plus chained wiki.search → wiki.open
  • Toggle Web search on → ask "What's recent in open-source LLMs?" →
    watch the browser.search tool fire
EOF
