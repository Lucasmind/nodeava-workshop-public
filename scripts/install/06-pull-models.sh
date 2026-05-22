#!/bin/bash
# Wizard step 6: pull workshop models. Per-model skip if already pulled.

step_heading 6 9 "Pull models"

say "  Why this matters: we pull two models so the workshop can demo the"
say "  contrast between a competent fast model and a tiny weaker one."
say ""
say "  • qwen3:4b-instruct  — fast, conversational, no chain-of-thought."
say "                         Workshop default brain."
say "  • smollm2:360m       — tiny 360M model. Used in Demo 16 to show"
say "                         what a 'dumb' model looks like in the same pipe."
say ""
say "  Total download: ~2.8 GB. Good wifi: 1-3 min. Conference wifi: 5-20 min."
echo

if [[ "${NODEAVA_INV_MODELS:-missing}" = "keep" ]]; then
  ok "Both models already pulled — skipping (Inventory said Keep)."
  pause
  return 0
fi

# Pull each model if not already present; reset overrides this and re-pulls.
for model in qwen3:4b-instruct smollm2:360m; do
  if [[ "${NODEAVA_INV_MODELS:-missing}" != "reset" ]] && ollama list 2>/dev/null | awk 'NR>1{print $1}' | grep -qx "$model"; then
    ok "$model already pulled — skipping"
  else
    info "Pulling $model ..."
    ollama pull "$model"
    ok "$model pulled"
  fi
done

pause
