# Shared library for the install wizard. Sourced (not exec'd) by step files
# and by scripts/install.sh. Defines color codes, prompt helpers, platform
# detection, and the step heading printer.

# --- Color codes ---
if [[ -t 1 ]] && [[ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]]; then
  C_CYAN="\033[1;36m"
  C_GRAY="\033[0;37m"
  C_GREEN="\033[1;32m"
  C_YELLOW="\033[1;33m"
  C_RED="\033[1;31m"
  C_BOLD="\033[1m"
  C_RESET="\033[0m"
else
  C_CYAN="" C_GRAY="" C_GREEN="" C_YELLOW="" C_RED="" C_BOLD="" C_RESET=""
fi

# --- Logging helpers ---
info() { printf "%b%s%b\n" "$C_CYAN" "$*" "$C_RESET"; }
say()  { printf "%b%s%b\n" "$C_GRAY" "$*" "$C_RESET"; }
ok()   { printf "  %b✓%b %s\n" "$C_GREEN" "$C_RESET" "$*"; }
warn() { printf "  %b!%b %s\n" "$C_YELLOW" "$C_RESET" "$*"; }
fail() { printf "  %b✗%b %s\n" "$C_RED" "$C_RESET" "$*"; exit 1; }

# --- Step heading ---
# Usage: step_heading 2 6 "Preflight — verifying your machine"
step_heading() {
  local n=$1 total=$2 name=$3
  echo
  printf "%b[%d/%d] %s%b\n" "$C_CYAN" "$n" "$total" "$name" "$C_RESET"
  echo
}

# --- Prompts ---
# Skip all prompts when NODEAVA_AUTO=1 (--auto flag).
pause() {
  [[ "${NODEAVA_AUTO:-0}" = "1" ]] && return 0
  printf "%bPress Enter to continue%b" "$C_BOLD" "$C_RESET"
  read -r _ < /dev/tty
}

# prompt_yn "Question?" → returns 0 on Y/y/empty, 1 on N/n
prompt_yn() {
  [[ "${NODEAVA_AUTO:-0}" = "1" ]] && return 0
  local q="$1"
  while true; do
    printf "%b%s [Y/n] %b" "$C_BOLD" "$q" "$C_RESET"
    read -r ans < /dev/tty
    case "${ans:-y}" in
      y|Y|yes|YES) return 0 ;;
      n|N|no|NO)   return 1 ;;
      *) echo "Please answer y or n." ;;
    esac
  done
}

# prompt_choice "Question" letter1 label1 letter2 label2 ...
# Echoes the chosen letter (lowercase). Caller captures via $(...).
#
# All user-facing prose is written to /dev/tty rather than stdout — caller
# uses $(...), which would otherwise swallow the question and "Choice:"
# prompt, leaving the wizard apparently hung waiting for a keypress the
# user can't see being asked for.
prompt_choice() {
  local q="$1"; shift
  if [[ "${NODEAVA_AUTO:-0}" = "1" ]]; then
    # Default to first option
    echo "$1"
    return 0
  fi
  {
    echo
    echo "$q"
    while [[ $# -gt 0 ]]; do
      printf "  [%s] %s\n" "$1" "$2"
      shift 2
    done
  } > /dev/tty
  while true; do
    printf "%bChoice: %b" "$C_BOLD" "$C_RESET" > /dev/tty
    read -r ans < /dev/tty
    # POSIX lowercase via tr — bash 3.2 on macOS rejects the ${var,,} form
    # introduced in bash 4 with a "bad substitution" error.
    ans="$(printf '%s' "$ans" | tr '[:upper:]' '[:lower:]')"
    if [[ -n "$ans" ]]; then echo "$ans"; return 0; fi
  done
}

# --- Platform detection ---
# Sets NODEAVA_PLATFORM = linux | linux-wsl | mac | unsupported
detect_platform() {
  case "$(uname -s)" in
    Linux*)
      if grep -qi microsoft /proc/version 2>/dev/null; then
        NODEAVA_PLATFORM=linux-wsl
      else
        NODEAVA_PLATFORM=linux
      fi
      ;;
    Darwin*) NODEAVA_PLATFORM=mac ;;
    *) NODEAVA_PLATFORM=unsupported ;;
  esac
  export NODEAVA_PLATFORM
}

# --- Misc ---
has_command() { command -v "$1" > /dev/null 2>&1; }

# Resolve repo root from a step script's location.
nodeava_repo_root() {
  # _lib.sh is at scripts/install/_lib.sh; root is two levels up
  cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd
}

NODEAVA_REPO_ROOT="$(nodeava_repo_root)"
export NODEAVA_REPO_ROOT

# Ensure the host's Ollama systemd service binds to 0.0.0.0:11434 so that
# the orchestrator container can reach it via host.docker.internal. Without
# this, Ollama listens on 127.0.0.1 only and the container sees connection
# refused. Idempotent: skips silently if already bound off-loopback, or if
# the host has no systemd to configure.
ensure_ollama_host_bind() {
  has_command systemctl || return 0
  [[ -d /etc/systemd/system ]] || return 0

  local bind
  bind=$(ss -tlnH 2>/dev/null | awk '$4 ~ /:11434$/ {print $4; exit}')
  if [[ -n "$bind" && "$bind" != 127.0.0.1:11434 && "$bind" != "[::1]:11434" ]]; then
    return 0
  fi

  local dropin_dir=/etc/systemd/system/ollama.service.d
  local dropin_file="$dropin_dir/override.conf"
  say "Configuring Ollama to listen on 0.0.0.0:11434 (so Docker containers can reach it)..."
  if sudo mkdir -p "$dropin_dir" 2>/dev/null && \
     sudo tee "$dropin_file" >/dev/null 2>&1 <<'OLLAMA_DROPIN_EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
OLLAMA_DROPIN_EOF
  then
    sudo systemctl daemon-reload
    sudo systemctl restart ollama
    sleep 2
    ok "Ollama rebound to 0.0.0.0:11434"
    return 0
  fi

  warn "Could not write $dropin_file (sudo failed). Run manually:"
  say  "  sudo mkdir -p $dropin_dir"
  say  "  printf '[Service]\\nEnvironment=\"OLLAMA_HOST=0.0.0.0:11434\"\\n' | sudo tee $dropin_file"
  say  "  sudo systemctl daemon-reload && sudo systemctl restart ollama"
  return 1
}
