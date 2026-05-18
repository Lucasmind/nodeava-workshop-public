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
