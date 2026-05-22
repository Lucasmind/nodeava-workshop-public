#!/bin/bash
# Wizard step 6b: register the running llama.cpp container as a catalog brain.

step_heading 6 9 "Register llama.cpp as the active LLM"

say "  Why this matters: NodeAva's catalog supports a 'kind: openai-compatible'"
say "  brain type — any OpenAI-API-speaking server can be used. We point a"
say "  catalog entry at your running llama.cpp container so the dashboard's"
say "  brain selector shows it as the active option."
echo

port="${NODEAVA_LLAMACPP_PORT:-8081}"
if ! curl --max-time 3 -fsS "http://localhost:${port}/v1/models" >/dev/null 2>&1; then
  fail "llama.cpp not reachable at http://localhost:${port}/v1 — is the container still running?"
fi

# Detect the loaded model name from /v1/models
model_id="$(curl --max-time 5 -fsS "http://localhost:${port}/v1/models" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("data",[{}])[0].get("id","unknown"))' 2>/dev/null \
  || echo unknown)"

ok "Detected llama.cpp at :${port} (model: ${model_id})"

catalog="$NODEAVA_REPO_ROOT/configs/catalog.yml"
state="$NODEAVA_REPO_ROOT/state/current.json"

# Idempotent insert: only append if id=llamacpp-local isn't already in the catalog
if grep -q '^  - id: llamacpp-local$' "$catalog"; then
  ok "Catalog already has llamacpp-local entry — skipping append."
else
  info "Appending llamacpp-local brain entry to $catalog ..."
  # Find the personalities: line and insert before it. If not found, append before EOF.
  python3 - "$catalog" "$port" "$model_id" <<'PYEOF'
import sys, pathlib
path, port, model_id = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
entry = f"""\
  - id: llamacpp-local
    label: "llama.cpp local (advanced)"
    kind: openai-compatible
    url: http://localhost:{port}/v1
    model: {model_id}
    thinks: false

"""
# Insert just before the "voices:" line (after the last brain entry)
import re
m = re.search(r'^voices:', text, re.MULTILINE)
if m:
    text = text[:m.start()] + entry + text[m.start():]
else:
    text += entry
p.write_text(text)
PYEOF
  ok "Catalog entry appended."
fi

# Update state.brain to llamacpp-local
info "Setting state.brain = llamacpp-local ..."
mkdir -p "$(dirname "$state")"
if [[ -f "$state" ]]; then
  python3 - "$state" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
d["brain"] = "llamacpp-local"
p.write_text(json.dumps(d, indent=2))
PYEOF
else
  cat > "$state" <<EOF
{
  "brain": "llamacpp-local",
  "voice": "bella",
  "avatar": "ava",
  "personality": "default",
  "tools": {"web_search": false, "wiki": true}
}
EOF
fi
ok "state.brain set to llamacpp-local"

pause
