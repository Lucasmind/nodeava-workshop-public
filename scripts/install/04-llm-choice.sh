#!/bin/bash
# Wizard step 4: choose LLM serving layer. Sets NODEAVA_LLM_BACKEND.

step_heading 4 9 "LLM serving — Ollama or llama.cpp"

# Honor pre-set env var (e.g., NODEAVA_LLM_BACKEND=ollama ./install.sh)
if [[ -n "${NODEAVA_LLM_BACKEND:-}" ]]; then
  ok "LLM backend pinned via env var: $NODEAVA_LLM_BACKEND"
  pause
  return 0
fi

say "  Why this matters: the LLM is the model that generates avatar replies."
say "  NodeAva supports two serving layers:"
say ""
say "  • Ollama   — cross-platform, auto VRAM swap, single API for many models."
say "               Workshop default. Plans #7+ migrated to this."
say "  • llama.cpp — bare-metal, custom flags, fixed model per process."
say "               What NodeAva used in Plans #1-#6 before the Ollama migration."
echo

if [[ "${NODEAVA_INV_LLAMACPP:-missing}" = "present" ]]; then
  choice="$(prompt_choice "Which LLM backend?" \
    o "Ollama (recommended)" \
    l "llama.cpp (use the running container on port ${NODEAVA_LLAMACPP_PORT:-?})")"
  case "$choice" in
    l) NODEAVA_LLM_BACKEND=llamacpp ;;
    *) NODEAVA_LLM_BACKEND=ollama ;;
  esac
else
  NODEAVA_LLM_BACKEND=ollama
  ok "Using Ollama (no llama.cpp container detected; that's the recommended path anyway)."
fi

export NODEAVA_LLM_BACKEND
echo
pause
