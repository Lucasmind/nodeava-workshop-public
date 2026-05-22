#!/bin/bash
# Slide 24+33: Interactively poke the orchestrator's swap endpoints.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

show_state() {
  echo "--- /v1/state ---"
  curl -fsS "$ORCH_URL/v1/state" | python3 -m json.tool
}

swap_kind() {
  local kind="$1"
  echo "Available ${kind}s:"
  curl -fsS "$ORCH_URL/v1/catalog" \
    | python3 -c "import json,sys;d=json.load(sys.stdin)
for x in d.get(\"${kind}s\",[]):
    avail = '✓' if x.get('available',True) else '✗'
    print(f'  {avail} {x[\"id\"]:25s} {x[\"label\"]}')"
  read -r -p "Swap to id: " ID
  curl -fsS -X POST "$ORCH_URL/v1/swap" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'kind':sys.argv[1],'id':sys.argv[2]}))" "$kind" "$ID")" \
    | python3 -m json.tool
}

toggle_tool() {
  read -r -p "Tool to toggle (web_search|wiki): " T
  read -r -p "Value (true|false): " V
  curl -fsS -X POST "$ORCH_URL/v1/swap" \
    -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'kind':'tools','id':sys.argv[1],'value':sys.argv[2].lower()=='true'}))" "$T" "$V")" \
    | python3 -m json.tool
}

while true; do
  cat <<EOF

NodeAva Orchestrator Demo Menu
  [1] show state
  [2] swap brain
  [3] swap voice
  [4] swap personality
  [5] toggle tool
  [q] quit
EOF
  read -r -p "> " choice
  case "$choice" in
    1) show_state;;
    2) swap_kind brain;;
    3) swap_kind voice;;
    4) swap_kind personality;;
    5) toggle_tool;;
    q|Q|exit|quit) break;;
    *) echo "unknown: $choice";;
  esac
done
