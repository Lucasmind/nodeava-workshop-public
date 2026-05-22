#!/bin/bash
# Slide 14: Test the TTS engine. Type a phrase, hear it synthesized.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  PHRASE="The pipeline is up and running."
else
  read -r -p "Phrase to synthesize: " PHRASE
fi

# Get active voice from orchestrator state
VOICE=$(curl -fsS "$ORCH_URL/v1/state" 2>/dev/null \
  | python3 -c 'import json,sys;d=json.load(sys.stdin);
v=d.get("active",{}).get("voice");
import urllib.request,json as j
cat=j.loads(urllib.request.urlopen("'"$ORCH_URL"'/v1/catalog").read());
print(next((x["kokoro_voice"] for x in cat.get("voices",[]) if x["id"]==v),"af_bella"))' 2>/dev/null || echo "af_bella")

OUT="$(mktemp -t tts-XXXX.wav)"
echo "Synthesizing with voice=$VOICE ..."
curl -fsS -X POST "$TTS_URL/dev/captioned_speech" \
  -H 'Content-Type: application/json' \
  -d "$(python3 -c "import json,sys;print(json.dumps({'model':'kokoro','input':sys.argv[1],'voice':sys.argv[2],'response_format':'pcm','stream':False,'return_timestamps':False}))" "$PHRASE" "$VOICE")" \
  | python3 -c 'import sys, wave, json
# Read JSON envelope, extract base64 audio
import base64
d = json.load(sys.stdin)
audio_b64 = d.get("audio") or d.get("data") or ""
pcm = base64.b64decode(audio_b64) if audio_b64 else b""
w = wave.open(sys.argv[1], "wb"); w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm); w.close()' "$OUT"
echo "Playing $OUT"
play_wav "$OUT"
rm -f "$OUT"
