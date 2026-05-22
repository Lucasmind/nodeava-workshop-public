#!/bin/bash
# Wizard step 5: install Ollama. Skipped if already present (per inventory).

step_heading 5 9 "Install Ollama"

if [[ "${NODEAVA_INV_OLLAMA:-missing}" = "keep" ]]; then
  ok "Ollama already installed — skipping install (Inventory said Keep)."
  # The host-bind drop-in is a config concern, not an install concern: even
  # when Ollama was pre-installed (e.g., by the USB bootstrap before the
  # wizard ran), it may still be on the default 127.0.0.1, which leaves the
  # orchestrator container unable to reach it. Run the rebind unconditionally.
  ensure_ollama_host_bind || warn "Continuing without host-bind rebind; orchestrator may fail to reach Ollama."
  pause
  return 0
fi

say "  Why this matters: Ollama is the host-native LLM server. Plan #7 moved"
say "  NodeAva to Ollama for cross-platform consistency and automatic VRAM"
say "  management. The orchestrator container talks to it via"
say "  http://host.docker.internal:11434."
echo

case "$NODEAVA_PLATFORM" in
  linux|linux-wsl)
    setup_script="$NODEAVA_REPO_ROOT/scripts/setup-linux.sh"
    ;;
  mac)
    setup_script="$NODEAVA_REPO_ROOT/scripts/setup-mac.sh"
    ;;
  *)
    fail "No Ollama installer for platform $NODEAVA_PLATFORM"
    ;;
esac

if [[ ! -x "$setup_script" ]]; then
  fail "Installer script not executable: $setup_script (chmod +x and retry)"
fi

say "Running: bash $setup_script"
say "(You may be prompted for sudo if Ollama needs the systemd 0.0.0.0 bind.)"
echo

bash "$setup_script"

# Verify after
if ! curl --max-time 5 -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  fail "Ollama installed but not reachable at :11434. Try 'ollama serve' in another terminal."
fi
ok "Ollama is running."
pause
