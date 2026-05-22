#!/bin/bash
# Slide 23: End-to-end digital human in bash.
# Mic → Whisper → Ollama (active brain) → Kokoro (active voice) → speakers.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

# Step 1: Get spoken (or fixture) input
WAV="$(mktemp -t pipe-XXXX.wav)"
if $FIXTURE; then
  cp "$(cd "$DEMOS/../.." && pwd)/assets/demos/sample-stt.wav" "$WAV"
  echo "Using fixture audio"
else
  record_5s "$WAV"
fi

# Step 2: Transcribe
echo "[1/3] Transcribing..."
TRANSCRIPT=$(curl -fsS -X POST "$STT_URL/v1/audio/transcriptions" \
  -F "file=@$WAV" -F "model=base.en" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("text",""))')
echo "       \"$TRANSCRIPT\""
rm -f "$WAV"

# Step 3: Ask the orchestrator (this exercises the agentic loop + state)
echo "[2/3] Asking the agent..."
ANSWER=$(curl -fsS -X POST "$ORCH_URL/v1/chat/completions" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'messages':[{'role':'user','content':sys.argv[1]}],'stream':False}))" "$TRANSCRIPT")" \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d.get("choices",[{}])[0].get("message",{}).get("content",""))')
echo "       \"$ANSWER\""

# Step 4: Synthesize the answer with the active voice + play
echo "[3/3] Speaking..."
VOICE=$(curl -fsS "$ORCH_URL/v1/state" \
  | python3 -c 'import json,sys,urllib.request;d=json.load(sys.stdin);
v=d.get("active",{}).get("voice");
cat=json.loads(urllib.request.urlopen("'"$ORCH_URL"'/v1/catalog").read())
print(next((x["kokoro_voice"] for x in cat.get("voices",[]) if x["id"]==v),"af_bella"))')

OUT="$(mktemp -t reply-XXXX.wav)"
curl -fsS -X POST "$TTS_URL/dev/captioned_speech" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':'kokoro','input':sys.argv[1],'voice':sys.argv[2],'response_format':'pcm','stream':False,'return_timestamps':False}))" "$ANSWER" "$VOICE")" \
  | python3 -c 'import sys,wave,json,base64
d=json.load(sys.stdin); a=d.get("audio") or d.get("data") or ""
pcm=base64.b64decode(a) if a else b""
w=wave.open(sys.argv[1],"wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close()' "$OUT"
play_wav "$OUT"
rm -f "$OUT"
echo "Done."
