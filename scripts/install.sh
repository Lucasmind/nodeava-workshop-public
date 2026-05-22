#!/bin/bash
# NodeAva Workshop Installer Wizard.
#
# Usage:
#   ./install.sh                      Run the interactive wizard.
#   ./install.sh --auto               Skip all "Press Enter" pauses.
#   ./install.sh --full-reset         Force factory reset at the inventory step.
#   ./install.sh --help               Print usage.
#
# Env vars:
#   NODEAVA_LLM_BACKEND=ollama|llamacpp   Override the LLM-serving choice.
#   NODEAVA_QUIET=1                       Suppress teaching prose.
set -euo pipefail

# Source the shared library
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/install/_lib.sh
source "$SCRIPT_DIR/install/_lib.sh"

# --- Argv parsing ---
NODEAVA_AUTO="${NODEAVA_AUTO:-0}"
NODEAVA_FULL_RESET="${NODEAVA_FULL_RESET:-0}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --auto) NODEAVA_AUTO=1; shift ;;
    --full-reset) NODEAVA_FULL_RESET=1; shift ;;
    --help|-h)
      sed -n '2,15p' "$0" | sed 's/^# //;s/^#//'
      exit 0
      ;;
    *)
      fail "Unknown argument: $1 (try --help)"
      ;;
  esac
done
export NODEAVA_AUTO NODEAVA_FULL_RESET

# --- Error trap ---
on_error() {
  local lineno=$1 cmd=$2
  echo
  printf "%b✗ Step failed at line %d%b\n" "$C_RED" "$lineno" "$C_RESET"
  printf "  Command: %s\n" "$cmd"
  echo
  echo "You can re-run ./install.sh — completed steps will be skipped."
  exit 1
}
trap 'on_error $LINENO "$BASH_COMMAND"' ERR

# --- Step dispatch ---
STEPS_DIR="$SCRIPT_DIR/install"

run_step() {
  local file="$1"
  # shellcheck source=/dev/null
  source "$STEPS_DIR/$file"
}

# Run each step in order. Step files print their own headings via step_heading.
run_step 01-welcome.sh
run_step 02-preflight.sh
run_step 03-inventory.sh
run_step 04-llm-choice.sh

if [[ "${NODEAVA_LLM_BACKEND:-ollama}" = "ollama" ]]; then
  run_step 05-install-ollama.sh
  run_step 06-pull-models.sh
else
  run_step 06-register-llamacpp.sh
fi

run_step 07-build-stack.sh
run_step 08-up-stack.sh
run_step 09-smoke.sh
