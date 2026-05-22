#!/bin/bash
# Slide 13: Test the local LLM end-to-end (no agentic loop, just chat).
# Streams tokens as they arrive so attendees see the latency.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  PROMPT="Explain digital humans in one paragraph."
  echo "Using fixture prompt: $PROMPT"
else
  read -r -p "Your prompt: " PROMPT
fi

MODEL=$(curl -fsS "$OLLAMA_URL/api/tags" | python3 -c 'import json,sys;d=json.load(sys.stdin);print((d.get("models")or[{}])[0].get("name",""))')
echo "Calling Ollama (model=$MODEL):"

curl -fsSN "$OLLAMA_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':sys.argv[1],'messages':[{'role':'user','content':sys.argv[2]}],'stream':True}))" "$MODEL" "$PROMPT")" \
  | while IFS= read -r line; do
      case "$line" in
        data:*)
          payload="${line#data: }"
          [ "$payload" = "[DONE]" ] && break
          token=$(python3 -c "import json,sys;d=json.loads(sys.argv[1]);c=d.get('choices')or[{}];print(c[0].get('delta',{}).get('content',''),end='')" "$payload" 2>/dev/null || true)
          printf '%s' "$token"
          ;;
      esac
    done
echo
