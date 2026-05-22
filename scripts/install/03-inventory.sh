#!/bin/bash
# Wizard step 3: inventory + reset.

step_heading 3 9 "Inventory — finding what's already installed"

say "  Why this matters: re-running the wizard should not duplicate work."
say "  We detect existing pieces (Ollama, pulled models, the orchestrator"
say "  image, a saved state file, a running llama.cpp container) and skip"
say "  steps that are already done. This is also where 'reset' lives — if"
say "  things are broken, pick Full Reset and the wizard does everything fresh."
echo

# Honor --full-reset flag: skip detection prompts entirely
if [[ "${NODEAVA_FULL_RESET:-0}" = "1" ]]; then
  warn "--full-reset specified — every step will perform its full action."
  export NODEAVA_INV_OLLAMA=reset
  export NODEAVA_INV_MODELS=reset
  export NODEAVA_INV_IMAGE=reset
  export NODEAVA_INV_STATE=reset
  pause
  return 0
fi

# --- Detect Ollama ---
NODEAVA_INV_OLLAMA=missing
if has_command ollama && curl --max-time 2 -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  ollama_version="$(ollama --version 2>/dev/null | head -1 | sed 's/^.*version //')"
  echo "  Found: Ollama at :11434 (version ${ollama_version})"
  NODEAVA_INV_OLLAMA=present
fi

# --- Detect pulled models ---
NODEAVA_INV_MODELS=missing
if [[ "$NODEAVA_INV_OLLAMA" = "present" ]]; then
  pulled="$(ollama list 2>/dev/null | awk 'NR>1{print $1}')"
  have_qwen=0; have_smol=0
  echo "$pulled" | grep -q '^qwen3:4b-instruct' && have_qwen=1
  echo "$pulled" | grep -q '^smollm2:360m'      && have_smol=1
  if [[ "$have_qwen" = "1" ]] && [[ "$have_smol" = "1" ]]; then
    echo "  Found: both workshop models (qwen3:4b-instruct, smollm2:360m)"
    NODEAVA_INV_MODELS=present
  elif [[ "$have_qwen" = "1" ]]; then
    echo "  Partial: qwen3:4b-instruct pulled, smollm2:360m missing"
    NODEAVA_INV_MODELS=partial
  elif [[ "$have_smol" = "1" ]]; then
    echo "  Partial: smollm2:360m pulled, qwen3:4b-instruct missing"
    NODEAVA_INV_MODELS=partial
  fi
fi

# --- Detect orchestrator image ---
NODEAVA_INV_IMAGE=missing
if docker image inspect nodeava-orch:latest >/dev/null 2>&1; then
  built_at="$(docker image inspect nodeava-orch:latest --format '{{.Created}}' 2>/dev/null | cut -c1-19)"
  echo "  Found: nodeava-orch:latest (built ${built_at})"
  NODEAVA_INV_IMAGE=present
fi

# --- Detect state file ---
NODEAVA_INV_STATE=missing
state_path="$NODEAVA_REPO_ROOT/state/current.json"
if [[ -f "$state_path" ]]; then
  active_brain="$(python3 -c "import json; print(json.load(open('$state_path'))['brain'])" 2>/dev/null || echo unknown)"
  echo "  Found: state/current.json (active brain: ${active_brain})"
  NODEAVA_INV_STATE=present
fi

# --- Detect running llama.cpp container ---
NODEAVA_INV_LLAMACPP=missing
NODEAVA_LLAMACPP_PORT=""
if has_command docker; then
  llamacpp_cid="$(docker ps --filter 'ancestor=ghcr.io/ggml-org/llama.cpp:server-cuda' --filter 'status=running' --format '{{.ID}}' | head -1)"
  if [[ -z "$llamacpp_cid" ]]; then
    llamacpp_cid="$(docker ps --filter 'ancestor=ghcr.io/ggml-org/llama.cpp:server' --filter 'status=running' --format '{{.ID}}' | head -1)"
  fi
  if [[ -n "$llamacpp_cid" ]]; then
    llamacpp_port="$(docker port "$llamacpp_cid" 2>/dev/null | head -1 | awk -F: '{print $NF}')"
    echo "  Found: running llama.cpp container on port ${llamacpp_port:-?} (offered in next step)"
    NODEAVA_INV_LLAMACPP=present
    NODEAVA_LLAMACPP_PORT="$llamacpp_port"
  fi
fi

export NODEAVA_INV_OLLAMA NODEAVA_INV_MODELS NODEAVA_INV_IMAGE NODEAVA_INV_STATE NODEAVA_INV_LLAMACPP NODEAVA_LLAMACPP_PORT

# --- Top-level prompt: Full Reset or per-component decisions? ---
echo
if [[ "$NODEAVA_INV_OLLAMA" = "missing" ]] && [[ "$NODEAVA_INV_MODELS" = "missing" ]] && [[ "$NODEAVA_INV_IMAGE" = "missing" ]] && [[ "$NODEAVA_INV_STATE" = "missing" ]]; then
  say "Nothing to inventory — this looks like a fresh install. Continuing."
  pause
  return 0
fi

choice="$(prompt_choice "How would you like to handle the existing pieces?" \
  k "Keep — use existing pieces (re-runnable)" \
  r "Reset — wipe and reinstall everything from scratch" \
  s "Selective — decide per piece")"

case "$choice" in
  r)
    warn "Full reset chosen. Every step will perform its full action."
    NODEAVA_INV_OLLAMA=reset
    NODEAVA_INV_MODELS=reset
    NODEAVA_INV_IMAGE=reset
    NODEAVA_INV_STATE=reset
    ;;
  s)
    say "Selective mode — answering per piece."
    [[ "$NODEAVA_INV_STATE" = "present" ]] && \
      { prompt_yn "Reset state file to defaults?" && NODEAVA_INV_STATE=reset || NODEAVA_INV_STATE=keep; }
    [[ "$NODEAVA_INV_IMAGE" = "present" ]] && \
      { prompt_yn "Rebuild orchestrator image?" && NODEAVA_INV_IMAGE=reset || NODEAVA_INV_IMAGE=keep; }
    [[ "$NODEAVA_INV_MODELS" != "missing" ]] && \
      { prompt_yn "Re-pull workshop models?" && NODEAVA_INV_MODELS=reset || NODEAVA_INV_MODELS=keep; }
    # Ollama is rarely worth reinstalling; default keep.
    [[ "$NODEAVA_INV_OLLAMA" = "present" ]] && NODEAVA_INV_OLLAMA=keep
    ;;
  *)
    say "Keep mode — every step skips if already complete."
    [[ "$NODEAVA_INV_OLLAMA" = "present" ]] && NODEAVA_INV_OLLAMA=keep
    [[ "$NODEAVA_INV_MODELS" = "present" ]] && NODEAVA_INV_MODELS=keep
    [[ "$NODEAVA_INV_MODELS" = "partial" ]] && NODEAVA_INV_MODELS=partial
    [[ "$NODEAVA_INV_IMAGE" = "present" ]]  && NODEAVA_INV_IMAGE=keep
    [[ "$NODEAVA_INV_STATE" = "present" ]]  && NODEAVA_INV_STATE=keep
    ;;
esac

export NODEAVA_INV_OLLAMA NODEAVA_INV_MODELS NODEAVA_INV_IMAGE NODEAVA_INV_STATE
echo
pause
