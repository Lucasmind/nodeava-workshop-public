#!/usr/bin/env bash
# Set a custom personality system prompt from a file.
# Usage: scripts/demos/personality-set.sh <prompt-file.txt>
#
# Mirrors what the dashboard's Personality Editor does — POSTs the file
# contents to /v1/personality/custom and switches NodeAva to use it.
set -euo pipefail

ORCH_URL="${NODEAVA_ORCH_URL:-http://localhost:8082}"

if [[ $# -ne 1 ]]; then
  echo "usage: $(basename "$0") <prompt-file.txt>" >&2
  exit 1
fi

PROMPT_FILE="$1"
if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "error: $PROMPT_FILE not found" >&2
  exit 1
fi

PROMPT=$(cat "$PROMPT_FILE")
if [[ -z "${PROMPT//[[:space:]]/}" ]]; then
  echo "error: $PROMPT_FILE is empty" >&2
  exit 1
fi

# Build the JSON body with a here-doc + python for safe escaping
JSON=$(python3 -c '
import json, sys
print(json.dumps({"system_prompt": sys.stdin.read()}))
' <<< "$PROMPT")

echo "POST $ORCH_URL/v1/personality/custom  ($(wc -c <<< "$PROMPT") chars)"
curl -fsS -X POST "$ORCH_URL/v1/personality/custom" \
  -H 'Content-Type: application/json' \
  -d "$JSON" | python3 -m json.tool
