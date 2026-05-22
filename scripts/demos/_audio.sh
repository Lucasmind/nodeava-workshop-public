# Sourced helper for cross-platform mic recording + audio playback.
# Workshop attendees run scripts on Linux, WSL2, or macOS.
# Usage: source this file; then call record_5s OUTPUT_WAV or play_wav INPUT_WAV

_audio_detect() {
  case "$(uname -s)" in
    Darwin) AUDIO_OS=mac;;
    Linux)  AUDIO_OS=linux;;
    *)      AUDIO_OS=unknown;;
  esac
}
_audio_detect

record_5s() {
  local out="$1"
  if [ -z "$out" ]; then echo "record_5s: missing output path" >&2; return 2; fi
  echo "Recording 5s — speak now in: 3..."; sleep 1
  echo "                       2..."; sleep 1
  echo "                       1..."; sleep 1
  printf "\a"  # terminal bell
  echo "GO. Recording..."
  case "$AUDIO_OS" in
    linux)
      if ! command -v arecord >/dev/null 2>&1; then
        echo "ERROR: arecord not found. Install: sudo apt install alsa-utils" >&2
        return 1
      fi
      arecord -d 5 -f S16_LE -r 16000 -c 1 "$out" >/dev/null 2>&1
      ;;
    mac)
      if ! command -v sox >/dev/null 2>&1; then
        echo "ERROR: sox not found. Install: brew install sox" >&2
        return 1
      fi
      sox -d -c 1 -r 16000 -b 16 "$out" trim 0 5 >/dev/null 2>&1
      ;;
    *)
      echo "ERROR: unsupported OS for mic recording" >&2; return 1;;
  esac
  printf "\a"  # done bell
  echo "Recorded $(du -h "$out" | cut -f1) → $out"
}

play_wav() {
  local in="$1"
  if [ -z "$in" ]; then echo "play_wav: missing input path" >&2; return 2; fi
  case "$AUDIO_OS" in
    linux)
      if command -v aplay >/dev/null 2>&1; then aplay -q "$in"; else paplay "$in" 2>/dev/null || echo "ERROR: no aplay/paplay" >&2; fi
      ;;
    mac)
      afplay "$in"
      ;;
    *)
      echo "ERROR: unsupported OS for playback" >&2; return 1;;
  esac
}

# Endpoint defaults — overridable via env
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
TTS_URL="${TTS_URL:-http://localhost:8880}"
STT_URL="${STT_URL:-http://localhost:8080}"
ORCH_URL="${ORCH_URL:-http://localhost:8082}"
