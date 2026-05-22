#!/bin/bash
# Wizard step 1: welcome + agenda.

step_heading 1 9 "Welcome"

cat <<'EOF'
NodeAva Installer Wizard

This wizard will get a self-contained digital human running on your laptop.
You'll watch each piece of the pipeline being assembled — STT, LLM, TTS,
avatar, orchestrator — and learn why each one is there.

Agenda:
  1. Welcome
  2. Preflight     — verify your machine
  3. Inventory     — find what's already installed (also where reset lives)
  4. LLM serving   — Ollama (recommended) or llama.cpp
  5. Install LLM   — Ollama installer / register llama.cpp catalog entry
  6. Models        — download Qwen3 4B Instruct + SmolLM2 360M
  7. Build image   — orchestrator container
  8. Stack up      — docker compose up
  9. Smoke verify  — confirm everything is green

The wizard pauses at each step. Press Ctrl+C to abort safely at any time.
Re-running the wizard is always safe — completed steps will be detected
and skipped.
EOF
echo
pause
