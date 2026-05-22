#!/bin/bash
# Start NodeAva Docker services with GPU auto-detection
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
SERVICES=(llm tts stt frontend)

cd "$PROJECT_DIR"

show_help() {
  cat <<'EOF'
Usage: ./scripts/start.sh [OPTIONS] [SERVICE...]

Start NodeAva Docker services with automatic GPU detection.

Services:
  llm         Language model (llama.cpp)
  tts         Text-to-speech (Kokoro-FastAPI)
  stt         Speech-to-text (whisper.cpp)
  frontend    Web frontend (nginx + Vite)

Options:
  --help      Show this help message
  --no-wait   Start services without waiting for health checks
  --logs      Follow logs after starting

Examples:
  ./scripts/start.sh              Start all services and wait for healthy
  ./scripts/start.sh llm tts      Start only LLM and TTS
  ./scripts/start.sh stt --logs   Start STT and follow its logs
  ./scripts/start.sh --no-wait    Start all without waiting for health checks
EOF
  exit 0
}

# Parse arguments
TARGETS=()
NO_WAIT=false
FOLLOW_LOGS=false

for arg in "$@"; do
  case "$arg" in
    --help|-h)  show_help ;;
    --no-wait)  NO_WAIT=true ;;
    --logs)     FOLLOW_LOGS=true ;;
    llm|tts|stt|frontend)
      TARGETS+=("$arg")
      ;;
    *)
      echo "ERROR: Unknown argument '$arg'"
      echo "Run './scripts/start.sh --help' for usage."
      exit 1
      ;;
  esac
done

# Default to all services
if [ ${#TARGETS[@]} -eq 0 ]; then
  TARGETS=("${SERVICES[@]}")
fi

echo "=== NodeAva Start ==="
echo ""

# Detect GPU
GPU_TYPE=$("$SCRIPT_DIR/detect-gpu.sh")

if [ "$GPU_TYPE" = "none" ]; then
  echo "ERROR: No supported GPU detected."
  echo "NodeAva requires an NVIDIA or AMD GPU."
  exit 1
fi

# Build compose command with GPU overlay
COMPOSE_FILES="-f docker-compose.yml"
case "$GPU_TYPE" in
  nvidia)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-nvidia.yml"
    echo "GPU: NVIDIA (CUDA)"
    ;;
  amd)
    COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.gpu-amd.yml"
    echo "GPU: AMD (Vulkan + ROCm)"
    ;;
esac
echo ""

# Check if target services are already running
ALREADY_RUNNING=()
for svc in "${TARGETS[@]}"; do
  if docker compose $COMPOSE_FILES ps --format '{{.Name}}' 2>/dev/null | grep -q "$svc"; then
    ALREADY_RUNNING+=("$svc")
  fi
done

if [ ${#ALREADY_RUNNING[@]} -gt 0 ]; then
  echo "Already running: ${ALREADY_RUNNING[*]}"
  echo "Stop them first with: ./scripts/stop.sh ${ALREADY_RUNNING[*]}"
  exit 1
fi

TARGET_LIST="${TARGETS[*]}"
echo "Starting: $TARGET_LIST"
echo ""

# Start services
docker compose $COMPOSE_FILES up --build -d "${TARGETS[@]}"

if [ "$FOLLOW_LOGS" = true ]; then
  echo ""
  docker compose $COMPOSE_FILES logs -f "${TARGETS[@]}"
  exit 0
fi

if [ "$NO_WAIT" = true ]; then
  echo ""
  echo "Services starting in background (health check wait skipped)."
  docker compose $COMPOSE_FILES ps "${TARGETS[@]}"
  exit 0
fi

# Determine which targets have health checks to wait for
HEALTH_TARGETS=()
for svc in "${TARGETS[@]}"; do
  case "$svc" in
    llm|tts|stt) HEALTH_TARGETS+=("$svc") ;;
  esac
done

if [ ${#HEALTH_TARGETS[@]} -eq 0 ]; then
  echo ""
  echo "No health-checked services to wait for."
  docker compose $COMPOSE_FILES ps "${TARGETS[@]}"
  exit 0
fi

echo ""
echo "Waiting for health checks: ${HEALTH_TARGETS[*]}"
echo ""

# Poll health status until all healthy or timeout
TIMEOUT=180
ELAPSED=0
EXPECTED=${#HEALTH_TARGETS[@]}

while [ $ELAPSED -lt $TIMEOUT ]; do
  HEALTH=$(docker compose $COMPOSE_FILES ps --format '{{.Name}} {{.Status}}' "${HEALTH_TARGETS[@]}" 2>/dev/null)
  HEALTHY_COUNT=$(echo "$HEALTH" | grep -c "(healthy)" || true)

  printf "\r  Healthy: %d/%d (elapsed: %ds)" "$HEALTHY_COUNT" "$EXPECTED" "$ELAPSED"

  if [ "$HEALTHY_COUNT" -ge "$EXPECTED" ]; then
    echo ""
    echo ""
    echo "All services healthy!"
    echo ""
    docker compose $COMPOSE_FILES ps "${TARGETS[@]}"
    echo ""
    if printf '%s\n' "${TARGETS[@]}" | grep -q "frontend"; then
      echo "Open http://localhost:3000 in your browser."
    fi
    exit 0
  fi

  # Check for exited containers
  FAILED=$(docker compose $COMPOSE_FILES ps --format '{{.Name}} {{.State}}' "${TARGETS[@]}" 2>/dev/null | grep -c "exited" || true)
  if [ "$FAILED" -gt 0 ]; then
    echo ""
    echo ""
    echo "ERROR: Some services failed to start:"
    docker compose $COMPOSE_FILES ps "${TARGETS[@]}"
    echo ""
    echo "Check logs with: docker compose $COMPOSE_FILES logs ${TARGET_LIST}"
    exit 1
  fi

  sleep 5
  ELAPSED=$((ELAPSED + 5))
done

echo ""
echo ""
echo "WARNING: Timed out after ${TIMEOUT}s. Some services may still be loading."
docker compose $COMPOSE_FILES ps "${TARGETS[@]}"
echo ""
echo "Check logs with: docker compose $COMPOSE_FILES logs ${TARGET_LIST}"
