#!/bin/bash
# Stop NodeAva Docker services
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICES=(llm tts stt frontend)

cd "$PROJECT_DIR"

show_help() {
  cat <<'EOF'
Usage: ./scripts/stop.sh [OPTIONS] [SERVICE...]

Stop NodeAva Docker services.

Services:
  llm         Language model (llama.cpp)
  tts         Text-to-speech (Kokoro-FastAPI)
  stt         Speech-to-text (whisper.cpp)
  frontend    Web frontend (nginx + Vite)

Options:
  --help      Show this help message
  --all       Stop all services and remove volumes (full cleanup)

Examples:
  ./scripts/stop.sh              Stop all services
  ./scripts/stop.sh tts          Stop only TTS
  ./scripts/stop.sh llm stt      Stop LLM and STT
  ./scripts/stop.sh --all        Stop all and remove volumes
EOF
  exit 0
}

# Parse arguments
TARGETS=()
FULL_CLEANUP=false

for arg in "$@"; do
  case "$arg" in
    --help|-h)  show_help ;;
    --all)      FULL_CLEANUP=true ;;
    llm|tts|stt|frontend)
      TARGETS+=("$arg")
      ;;
    *)
      echo "ERROR: Unknown argument '$arg'"
      echo "Run './scripts/stop.sh --help' for usage."
      exit 1
      ;;
  esac
done

echo "=== Stopping NodeAva ==="
echo ""

# Detect GPU to use the same compose files
GPU_TYPE=$("$SCRIPT_DIR/detect-gpu.sh")

COMPOSE_FILES="-f docker-compose.yml"
case "$GPU_TYPE" in
  nvidia)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-nvidia.yml"
    ;;
  amd)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-amd.yml"
    ;;
esac

# Stopping specific services
if [ ${#TARGETS[@]} -gt 0 ]; then
  TARGET_LIST="${TARGETS[*]}"

  # Check which targets are actually running
  RUNNING=()
  for svc in "${TARGETS[@]}"; do
    if docker compose $COMPOSE_FILES ps --format '{{.Name}}' 2>/dev/null | grep -q "$svc"; then
      RUNNING+=("$svc")
    fi
  done

  if [ ${#RUNNING[@]} -eq 0 ]; then
    echo "None of the specified services are running: $TARGET_LIST"
    exit 0
  fi

  echo "Stopping: ${RUNNING[*]}"
  docker compose $COMPOSE_FILES stop "${RUNNING[@]}"
  echo ""
  echo "Stopped: ${RUNNING[*]}"
  echo ""
  echo "Remaining services:"
  docker compose $COMPOSE_FILES ps 2>/dev/null || echo "  (none)"
  exit 0
fi

# Stopping all services
RUNNING=$(docker compose $COMPOSE_FILES ps --format '{{.Name}}' 2>/dev/null | wc -l)
if [ "$RUNNING" -eq 0 ]; then
  echo "No running NodeAva services found."
  exit 0
fi

echo "Stopping all services..."
docker compose $COMPOSE_FILES ps
echo ""

if [ "$FULL_CLEANUP" = true ]; then
  docker compose $COMPOSE_FILES down -v
  echo ""
  echo "All services stopped and volumes removed."
else
  docker compose $COMPOSE_FILES down
  echo ""
  echo "All services stopped."
fi
