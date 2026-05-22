#!/bin/bash
# Slide 15: Test STT with mic input (or --fixture for a shipped WAV).
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$DEMOS/../.." && pwd)"
. "$DEMOS/_audio.sh"

FIXTURE=false
[ "${1:-}" = "--fixture" ] && FIXTURE=true

if $FIXTURE; then
  WAV="$REPO_ROOT/assets/demos/sample-stt.wav"
  if [ ! -f "$WAV" ]; then
    echo "ERROR: fixture not found at $WAV" >&2; exit 1
  fi
  echo "Using fixture: $WAV"
else
  WAV="$(mktemp -t stt-XXXX.wav)"
  record_5s "$WAV"
fi

echo "Sending to Whisper..."
TRANSCRIPT=$(curl -fsS -X POST "$STT_URL/v1/audio/transcriptions" \
  -F "file=@$WAV" -F "model=base.en" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin).get("text",""))')

echo "Transcript: $TRANSCRIPT"
$FIXTURE || rm -f "$WAV"
