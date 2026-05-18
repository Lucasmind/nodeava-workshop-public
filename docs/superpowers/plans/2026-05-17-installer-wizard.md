# Installer Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the interactive `./install.sh` wizard described in the Plan #9 spec — preflight + inventory + LLM-serving choice + Ollama install + model pull + stack bring-up + smoke verify, with chatty teaching output and idempotent re-runs.

**Architecture:** Bash. Top-level `scripts/install.sh` dispatches to numbered step scripts in `scripts/install/NN-name.sh`. A shared `scripts/install/_lib.sh` provides colors, prompts, platform detection, and step heading helpers. Steps source `_lib.sh` and rely on shared env vars (`NODEAVA_PLATFORM`, `NODEAVA_GPU`, `NODEAVA_LLM_BACKEND`, etc.) set by earlier steps.

**Tech Stack:** Bash 4+, standard Unix utilities (`curl`, `docker`, `ollama`, `python3`, `jq`, `sed`, `awk`). The orchestrator's Python catalog parser already handles the runtime brain entry the llama.cpp branch appends (Plan #7's `kind: openai-compatible`).

**Spec:** `docs/superpowers/specs/2026-05-17-installer-wizard-design.md`

---

## File structure

### New files

| Path | Purpose |
|------|---------|
| `scripts/install.sh` | Entry point. Argv parsing, step dispatch, top-level error trap. |
| `scripts/install/_lib.sh` | Shared utils: color codes, prompts (`pause`, `prompt_yn`, `prompt_choice`), platform detection, step headings, `has_command`. |
| `scripts/install/01-welcome.sh` | Two-screen welcome banner + agenda. |
| `scripts/install/02-preflight.sh` | 5 checks: platform, GPU/VRAM, Docker, disk, network. |
| `scripts/install/03-inventory.sh` | Detect existing Ollama / models / image / state / llama.cpp container. Per-component Keep/Reset/Skip prompts; top-level Full Reset. |
| `scripts/install/04-llm-choice.sh` | Branch on inventory: Ollama (default) vs llama.cpp (advanced). Sets `NODEAVA_LLM_BACKEND`. |
| `scripts/install/05-install-ollama.sh` | Runs `bash scripts/setup-linux.sh` or `bash scripts/setup-mac.sh` (existing Plan #7 scripts). |
| `scripts/install/06-pull-models.sh` | `ollama pull qwen3:4b-instruct smollm2:360m` (per-model skip if already pulled). |
| `scripts/install/06-register-llamacpp.sh` | Detects running llama.cpp container's port + model; appends a `kind: openai-compatible` catalog entry; sets state.brain. |
| `scripts/install/07-build-stack.sh` | `docker compose build orchestrator` with the right GPU overlay. |
| `scripts/install/08-up-stack.sh` | `docker compose up -d orchestrator tts stt searxng`; waits for healthy. |
| `scripts/install/09-smoke.sh` | Three live probes + final message with `localhost:5173` instructions. |

### Modified files

None initially. The plan touches only new files under `scripts/install/`. The two existing setup scripts (`scripts/setup-linux.sh`, `scripts/setup-mac.sh`) from Plan #7 are CALLED, not modified.

---

## Task 1: Library + entry scaffold

**Files:**
- Create: `scripts/install.sh`
- Create: `scripts/install/_lib.sh`

A minimal end-to-end shell that prints a banner and exits. Establishes the conventions every other step will reuse: color helpers, prompts, step heading, platform detection.

- [ ] **Step 1: Create `scripts/install/_lib.sh`**

```bash
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
prompt_choice() {
  local q="$1"; shift
  if [[ "${NODEAVA_AUTO:-0}" = "1" ]]; then
    # Default to first option
    echo "$1"
    return 0
  fi
  echo
  echo "$q"
  while [[ $# -gt 0 ]]; do
    printf "  [%s] %s\n" "$1" "$2"
    shift 2
  done
  while true; do
    printf "%bChoice: %b" "$C_BOLD" "$C_RESET"
    read -r ans < /dev/tty
    ans="${ans,,}"  # lowercase
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
```

- [ ] **Step 2: Create `scripts/install.sh`**

```bash
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
NODEAVA_AUTO=0
NODEAVA_FULL_RESET=0
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
```

```bash
chmod +x scripts/install.sh
```

- [ ] **Step 3: Create stub step files so `install.sh` can dispatch**

For each step file, create a one-line placeholder that prints its name. We'll replace these in subsequent tasks.

```bash
mkdir -p scripts/install
for f in 01-welcome 02-preflight 03-inventory 04-llm-choice 05-install-ollama 06-pull-models 06-register-llamacpp 07-build-stack 08-up-stack 09-smoke; do
  echo '#!/bin/bash' > scripts/install/${f}.sh
  echo "say '[stub: ${f}.sh]'" >> scripts/install/${f}.sh
done
```

- [ ] **Step 4: Syntax check + dry run**

```bash
bash -n scripts/install.sh
bash -n scripts/install/_lib.sh
for f in scripts/install/0*.sh; do bash -n "$f"; done
echo "syntax OK"

NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | head -20
```

Expected: `syntax OK` then 10 lines of "[stub: ...]" output.

- [ ] **Step 5: Commit**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
git add scripts/install.sh scripts/install/
git commit -m "feat(installer): wizard scaffold (entry + _lib + step stubs)"
```

---

## Task 2: Welcome step (01-welcome.sh)

**Files:**
- Modify: `scripts/install/01-welcome.sh`

Two-screen welcome banner. Sets the tone for the wizard's chatty teaching style.

- [ ] **Step 1: Replace stub with welcome content**

Replace `scripts/install/01-welcome.sh` with:

```bash
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
```

- [ ] **Step 2: Test**

```bash
bash -n scripts/install/01-welcome.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | head -25
```

Expected: welcome banner prints; the wizard proceeds to the stub steps after a brief pause-skip.

- [ ] **Step 3: Commit**

```bash
git add scripts/install/01-welcome.sh
git commit -m "feat(installer): welcome banner + agenda"
```

---

## Task 3: Preflight step (02-preflight.sh)

**Files:**
- Modify: `scripts/install/02-preflight.sh`

Five checks. Each prints a one-line WHY before the result.

- [ ] **Step 1: Replace stub with full preflight content**

Replace `scripts/install/02-preflight.sh` with:

```bash
#!/bin/bash
# Wizard step 2: preflight. Five system checks before any install action.

step_heading 2 9 "Preflight — verifying your machine"

say "  Why this matters: the workshop expects a few baseline conditions."
say "  Catching problems here saves time later (a captive-wifi portal at"
say "  hour 1 ruins the rest of the session)."
echo

# --- Check 1: platform ---
detect_platform
case "$NODEAVA_PLATFORM" in
  linux)     ok "Platform: Linux $(uname -m) (kernel $(uname -r | cut -d- -f1))" ;;
  linux-wsl) ok "Platform: WSL2 (Linux on Windows)" ;;
  mac)       ok "Platform: macOS $(sw_vers -productVersion 2>/dev/null || echo unknown)" ;;
  unsupported) fail "Unsupported platform ($(uname -s)). The workshop supports Linux, WSL2, and macOS." ;;
esac

# --- Check 2: GPU + VRAM ---
NODEAVA_GPU=""
NODEAVA_VRAM_MB=0
if has_command nvidia-smi; then
  # nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits
  read -r gpu_name vram_mb < <(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null | head -1 | awk -F',' '{gsub(/^ +| +$/,"",$1); gsub(/^ +| +$/,"",$2); print $1, $2}')
  if [[ -n "$gpu_name" ]]; then
    NODEAVA_GPU="$gpu_name"
    NODEAVA_VRAM_MB="$vram_mb"
  fi
fi
if [[ -z "$NODEAVA_GPU" ]] && has_command rocm-smi; then
  NODEAVA_GPU="$(rocm-smi --showproductname 2>/dev/null | grep -i 'card series' | head -1 | sed 's/.*: //')"
  NODEAVA_VRAM_MB="$(rocm-smi --showmeminfo vram --json 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next(iter(d.values()))["VRAM Total Memory (B)"] // 1024 // 1024)' 2>/dev/null || echo 0)"
fi
if [[ "$NODEAVA_PLATFORM" = "mac" ]] && [[ -z "$NODEAVA_GPU" ]]; then
  # Apple Silicon — unified memory; report system memory minus reserved
  NODEAVA_GPU="Apple Silicon (Metal, unified memory)"
  NODEAVA_VRAM_MB=$(($(sysctl -n hw.memsize) / 1024 / 1024))
fi
export NODEAVA_GPU NODEAVA_VRAM_MB

if [[ -n "$NODEAVA_GPU" ]]; then
  if [[ "$NODEAVA_VRAM_MB" -ge 8192 ]]; then
    ok "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB (workshop floor is 8192 MB)"
  elif [[ "$NODEAVA_VRAM_MB" -ge 6144 ]]; then
    warn "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB — below the 8 GB workshop floor; expect slow inference"
  else
    warn "GPU: $NODEAVA_GPU · ${NODEAVA_VRAM_MB} MB — significantly below 8 GB; consider CPU mode or a smaller model"
  fi
else
  warn "GPU: none detected — Ollama will run on CPU (slower; smollm2 still usable)"
fi

# --- Check 3: Docker reachable ---
if ! has_command docker; then
  fail "Docker not installed. Install Docker Desktop (mac) or docker.io (Linux) and re-run."
fi
if ! docker info >/dev/null 2>&1; then
  fail "Docker daemon not reachable. Start Docker Desktop / 'sudo systemctl start docker' and re-run."
fi
docker_version="$(docker --version | awk '{print $3}' | sed 's/,$//')"
ok "Docker: reachable (version $docker_version)"

# --- Check 4: Disk free ---
# Check the partition containing $HOME (where ~/.ollama lives)
disk_avail_gb=$(df -BG "$HOME" 2>/dev/null | awk 'NR==2{gsub("G","",$4); print $4}')
if [[ -z "$disk_avail_gb" ]]; then
  warn "Disk: could not determine free space"
elif [[ "$disk_avail_gb" -lt 5 ]]; then
  fail "Disk: ${disk_avail_gb} GB free on $HOME's partition. The workshop needs at least 5 GB."
elif [[ "$disk_avail_gb" -lt 10 ]]; then
  warn "Disk: ${disk_avail_gb} GB free — tight but workable (workshop needs ~10 GB ideally)"
else
  ok "Disk: ${disk_avail_gb} GB free on $HOME's partition"
fi

# --- Check 5: Network ---
if curl --max-time 5 -fsS https://ollama.com -o /dev/null 2>/dev/null; then
  ok "Network: ollama.com reachable"
else
  warn "Network: ollama.com unreachable (captive portal? offline?). If models are already pulled the wizard can still proceed."
fi

echo
say "All preflight checks complete."
pause
```

- [ ] **Step 2: Test on this host**

```bash
bash -n scripts/install/02-preflight.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Preflight/,/All preflight checks complete/p'
```

Expected output: 5 checks listed, all green or yellow on this dev box. No `fail` exits.

- [ ] **Step 3: Commit**

```bash
git add scripts/install/02-preflight.sh
git commit -m "feat(installer): preflight — platform/GPU/Docker/disk/network checks"
```

---

## Task 4: Inventory step (03-inventory.sh)

**Files:**
- Modify: `scripts/install/03-inventory.sh`

Detects pre-installed pieces and offers Keep / Reset / Skip per item. Also where the top-level "full reset" lives.

- [ ] **Step 1: Replace stub with inventory content**

Replace `scripts/install/03-inventory.sh` with:

```bash
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
```

- [ ] **Step 2: Test on dev box (which has many things already installed)**

```bash
bash -n scripts/install/03-inventory.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Inventory/,/^\[4/p' | head -30
```

Expected: inventory shows the detected pieces (Ollama, models if pulled, image if built, state if present). With `--auto` the first prompt option is chosen automatically (Keep mode).

- [ ] **Step 3: Test --full-reset flag**

```bash
NODEAVA_AUTO=1 NODEAVA_FULL_RESET=1 ./scripts/install.sh 2>&1 | sed -n '/Inventory/,/^\[4/p' | head -20
```

Expected: see `--full-reset specified` warning; all `NODEAVA_INV_*` set to `reset` (visible via the trace if you uncomment).

- [ ] **Step 4: Commit**

```bash
git add scripts/install/03-inventory.sh
git commit -m "feat(installer): inventory + reset (Keep/Reset/Selective + --full-reset)"
```

---

## Task 5: LLM choice step (04-llm-choice.sh)

**Files:**
- Modify: `scripts/install/04-llm-choice.sh`

Branches based on inventory: Ollama default, llama.cpp available if a container was detected. Sets `NODEAVA_LLM_BACKEND`.

- [ ] **Step 1: Replace stub**

Replace `scripts/install/04-llm-choice.sh` with:

```bash
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
```

- [ ] **Step 2: Test**

```bash
bash -n scripts/install/04-llm-choice.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/LLM serving/,/^\[5/p' | head -25
```

Expected: prints LLM serving section, defaults to Ollama, proceeds.

Test the llamacpp branch by exporting the env var:

```bash
NODEAVA_AUTO=1 NODEAVA_LLM_BACKEND=llamacpp ./scripts/install.sh 2>&1 | sed -n '/LLM serving/,/^\[/p' | head -5
```

Expected: "LLM backend pinned via env var: llamacpp"

- [ ] **Step 3: Commit**

```bash
git add scripts/install/04-llm-choice.sh
git commit -m "feat(installer): LLM choice — Ollama default, llama.cpp opt-in"
```

---

## Task 6: Install Ollama step (05-install-ollama.sh)

**Files:**
- Modify: `scripts/install/05-install-ollama.sh`

Runs only on the Ollama branch. Calls existing `setup-linux.sh` or `setup-mac.sh`.

- [ ] **Step 1: Replace stub**

Replace `scripts/install/05-install-ollama.sh` with:

```bash
#!/bin/bash
# Wizard step 5: install Ollama. Skipped if already present (per inventory).

step_heading 5 9 "Install Ollama"

if [[ "${NODEAVA_INV_OLLAMA:-missing}" = "keep" ]]; then
  ok "Ollama already installed — skipping (Inventory said Keep)."
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
```

- [ ] **Step 2: Test (since Ollama is already installed, this will hit the Keep path)**

```bash
bash -n scripts/install/05-install-ollama.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Install Ollama/,/^\[6/p' | head -10
```

Expected: "Ollama already installed — skipping (Inventory said Keep)."

- [ ] **Step 3: Commit**

```bash
git add scripts/install/05-install-ollama.sh
git commit -m "feat(installer): install Ollama via existing setup-{linux,mac}.sh"
```

---

## Task 7: Pull models step (06-pull-models.sh)

**Files:**
- Modify: `scripts/install/06-pull-models.sh`

Pulls workshop models, skipping per-model if already present.

- [ ] **Step 1: Replace stub**

Replace `scripts/install/06-pull-models.sh` with:

```bash
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
```

- [ ] **Step 2: Test**

```bash
bash -n scripts/install/06-pull-models.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Pull models/,/^\[7/p' | head -15
```

Expected: with --auto + existing models, prints "skipping". With `NODEAVA_FULL_RESET=1`, re-pulls (slow — only run that test if you want to spend the bandwidth).

- [ ] **Step 3: Commit**

```bash
git add scripts/install/06-pull-models.sh
git commit -m "feat(installer): pull workshop models (qwen3:4b-instruct + smollm2:360m)"
```

---

## Task 8: llama.cpp catalog registration (06-register-llamacpp.sh)

**Files:**
- Modify: `scripts/install/06-register-llamacpp.sh`

Runs on the llama.cpp branch. Detects port + loaded model, appends a `kind: openai-compatible` brain entry to `configs/catalog.yml`, updates `state/current.json` to set it active.

- [ ] **Step 1: Replace stub**

Replace `scripts/install/06-register-llamacpp.sh` with:

```bash
#!/bin/bash
# Wizard step 6b: register the running llama.cpp container as a catalog brain.

step_heading 6 9 "Register llama.cpp as the active LLM"

say "  Why this matters: NodeAva's catalog supports a 'kind: openai-compatible'"
say "  brain type — any OpenAI-API-speaking server can be used. We point a"
say "  catalog entry at your running llama.cpp container so the dashboard's"
say "  brain selector shows it as the active option."
echo

port="${NODEAVA_LLAMACPP_PORT:-8081}"
if ! curl --max-time 3 -fsS "http://localhost:${port}/v1/models" >/dev/null 2>&1; then
  fail "llama.cpp not reachable at http://localhost:${port}/v1 — is the container still running?"
fi

# Detect the loaded model name from /v1/models
model_id="$(curl --max-time 5 -fsS "http://localhost:${port}/v1/models" 2>/dev/null \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("data",[{}])[0].get("id","unknown"))' 2>/dev/null \
  || echo unknown)"

ok "Detected llama.cpp at :${port} (model: ${model_id})"

catalog="$NODEAVA_REPO_ROOT/configs/catalog.yml"
state="$NODEAVA_REPO_ROOT/state/current.json"

# Idempotent insert: only append if id=llamacpp-local isn't already in the catalog
if grep -q '^  - id: llamacpp-local$' "$catalog"; then
  ok "Catalog already has llamacpp-local entry — skipping append."
else
  info "Appending llamacpp-local brain entry to $catalog ..."
  # Find the personalities: line and insert before it. If not found, append before EOF.
  python3 - "$catalog" "$port" "$model_id" <<'PYEOF'
import sys, pathlib
path, port, model_id = sys.argv[1], sys.argv[2], sys.argv[3]
p = pathlib.Path(path)
text = p.read_text()
entry = f"""\
  - id: llamacpp-local
    label: "llama.cpp local (advanced)"
    kind: openai-compatible
    url: http://localhost:{port}/v1
    model: {model_id}
    thinks: false

"""
# Insert just before the "voices:" line (after the last brain entry)
import re
m = re.search(r'^voices:', text, re.MULTILINE)
if m:
    text = text[:m.start()] + entry + text[m.start():]
else:
    text += entry
p.write_text(text)
PYEOF
  ok "Catalog entry appended."
fi

# Update state.brain to llamacpp-local
info "Setting state.brain = llamacpp-local ..."
mkdir -p "$(dirname "$state")"
if [[ -f "$state" ]]; then
  python3 - "$state" <<'PYEOF'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text())
d["brain"] = "llamacpp-local"
p.write_text(json.dumps(d, indent=2))
PYEOF
else
  cat > "$state" <<EOF
{
  "brain": "llamacpp-local",
  "voice": "bella",
  "avatar": "ava",
  "personality": "default",
  "tools": {"web_search": false, "wiki": true}
}
EOF
fi
ok "state.brain set to llamacpp-local"

pause
```

- [ ] **Step 2: Test the llamacpp branch (without an actual llama.cpp container, this should fail gracefully)**

```bash
bash -n scripts/install/06-register-llamacpp.sh
# Force the llamacpp branch via env var
NODEAVA_AUTO=1 NODEAVA_LLM_BACKEND=llamacpp NODEAVA_LLAMACPP_PORT=99999 ./scripts/install.sh 2>&1 | sed -n '/Register llama.cpp/,/^\[/p' | head -10
```

Expected: "llama.cpp not reachable at http://localhost:99999/v1" and exit. Trap should print the recovery hint.

- [ ] **Step 3: Test with an ACTUAL running llama.cpp container (the user has one from earlier sessions)**

```bash
# Confirm there's a llama.cpp container running
docker ps --filter 'ancestor=ghcr.io/ggml-org/llama.cpp:server-cuda' --format '{{.ID}} {{.Ports}}'
```

If that returns a container, run:

```bash
NODEAVA_AUTO=1 NODEAVA_LLM_BACKEND=llamacpp ./scripts/install.sh 2>&1 | sed -n '/Register llama.cpp/,/^\[/p' | head -15
grep -A 6 'id: llamacpp-local' configs/catalog.yml
```

Expected: catalog entry appears with the detected port + model. If no llama.cpp container is running on this host, skip this sub-step.

If you modified the catalog, restore the original state:

```bash
git diff configs/catalog.yml | head -20
# If undesired, revert: git checkout configs/catalog.yml
```

- [ ] **Step 4: Commit**

```bash
git add scripts/install/06-register-llamacpp.sh
git commit -m "feat(installer): register running llama.cpp container as catalog brain"
```

---

## Task 9: Build + up stack (07-build-stack.sh + 08-up-stack.sh)

**Files:**
- Modify: `scripts/install/07-build-stack.sh`
- Modify: `scripts/install/08-up-stack.sh`

Build the orchestrator image, bring up the four services.

- [ ] **Step 1: Replace `07-build-stack.sh`**

```bash
#!/bin/bash
# Wizard step 7: build the orchestrator image.

step_heading 7 9 "Build orchestrator image"

if [[ "${NODEAVA_INV_IMAGE:-missing}" = "keep" ]]; then
  ok "nodeava-orch:latest already built — skipping (Inventory said Keep)."
  pause
  return 0
fi

say "  Why this matters: the orchestrator is the agentic-loop brain. It"
say "  receives chat requests, decides which tools to call (wiki / web /"
say "  ingest), routes to the active LLM brain, and streams events back"
say "  to the dashboard."
echo

# Pick GPU overlay
case "$NODEAVA_PLATFORM" in
  linux|linux-wsl)
    if [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ NVIDIA ]]; then
      gpu_overlay="-f docker-compose.gpu-nvidia.yml"
    elif [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ (AMD|Radeon) ]]; then
      gpu_overlay="-f docker-compose.gpu-amd.yml"
    else
      gpu_overlay=""
    fi
    ;;
  mac)
    gpu_overlay=""
    ;;
  *) gpu_overlay="" ;;
esac

# Pick up a local override if present (e.g., dev mounts)
override_overlay=""
if [[ -f "$NODEAVA_REPO_ROOT/docker-compose.override.yml" ]]; then
  override_overlay="-f docker-compose.override.yml"
fi

cd "$NODEAVA_REPO_ROOT"
info "Building orchestrator image (this can take 1-2 min on first run) ..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $gpu_overlay $override_overlay build orchestrator
ok "nodeava-orch:latest built."
pause
```

- [ ] **Step 2: Replace `08-up-stack.sh`**

```bash
#!/bin/bash
# Wizard step 8: bring up the docker stack.

step_heading 8 9 "Bring up the stack"

say "  Starting four services:"
say "    • orchestrator  — the agentic-loop brain (port 8082)"
say "    • tts           — Kokoro neural text-to-speech (port 8880)"
say "    • stt           — Whisper speech-to-text (port 8080)"
say "    • searxng       — bundled meta-search for the browser tool"
say ""
say "  Ollama is on your host (not in Docker) and serves the LLM at :11434."
echo

# Pick GPU overlay (same logic as build step)
case "$NODEAVA_PLATFORM" in
  linux|linux-wsl)
    if [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ NVIDIA ]]; then
      gpu_overlay="-f docker-compose.gpu-nvidia.yml"
    elif [[ -n "$NODEAVA_GPU" ]] && [[ "$NODEAVA_GPU" =~ (AMD|Radeon) ]]; then
      gpu_overlay="-f docker-compose.gpu-amd.yml"
    else
      gpu_overlay=""
    fi
    ;;
  mac) gpu_overlay="" ;;
  *) gpu_overlay="" ;;
esac

override_overlay=""
if [[ -f "$NODEAVA_REPO_ROOT/docker-compose.override.yml" ]]; then
  override_overlay="-f docker-compose.override.yml"
fi

cd "$NODEAVA_REPO_ROOT"
info "Starting services ..."
# shellcheck disable=SC2086
docker compose -f docker-compose.yml $gpu_overlay $override_overlay up -d orchestrator tts stt searxng

# Wait for healthy. Loop up to 60s.
deadline=$(( $(date +%s) + 60 ))
while true; do
  unhealthy="$(docker compose -f docker-compose.yml $gpu_overlay $override_overlay ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -v 'healthy' | grep -v '^$' || true)"
  [[ -z "$unhealthy" ]] && break
  if [[ "$(date +%s)" -gt "$deadline" ]]; then
    warn "Some services did not become healthy within 60s:"
    echo "$unhealthy"
    break
  fi
  sleep 2
done
ok "Stack is up."
pause
```

- [ ] **Step 3: Test (since the stack is already up from earlier sessions, build will be quick and up will be no-op)**

```bash
bash -n scripts/install/07-build-stack.sh scripts/install/08-up-stack.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Build orchestrator/,/Stack is up/p' | head -30
```

Expected: build runs (cached layers), up reports services healthy.

- [ ] **Step 4: Commit**

```bash
git add scripts/install/07-build-stack.sh scripts/install/08-up-stack.sh
git commit -m "feat(installer): build orchestrator image + bring up stack"
```

---

## Task 10: Smoke verify + final message (09-smoke.sh)

**Files:**
- Modify: `scripts/install/09-smoke.sh`

Three live probes + the final "you're ready" message.

- [ ] **Step 1: Replace stub**

Replace `scripts/install/09-smoke.sh` with:

```bash
#!/bin/bash
# Wizard step 9: smoke verify + final message.

step_heading 9 9 "Smoke verify"

say "  Why this matters: we confirm the orchestrator can load the catalog,"
say "  reach Ollama, and respond to /v1/state queries. If any check fails,"
say "  the recovery hint points to the most likely cause."
echo

failures=0

# Probe 1: /v1/state
if curl --max-time 5 -fsS http://localhost:8082/v1/state >/dev/null 2>&1; then
  ok "orchestrator /v1/state reachable"
else
  warn "orchestrator /v1/state failed — is the container healthy? 'docker logs nodeava-orch'"
  failures=$((failures+1))
fi

# Probe 2: /v1/catalog has brains
brains_count="$(curl --max-time 5 -fsS http://localhost:8082/v1/catalog 2>/dev/null \
  | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("brains",[])))' 2>/dev/null || echo 0)"
if [[ "$brains_count" -ge 2 ]]; then
  ok "/v1/catalog returns $brains_count brains"
else
  warn "/v1/catalog returned $brains_count brains — catalog file may be malformed"
  failures=$((failures+1))
fi

# Probe 3: Ollama reachable from the orchestrator's perspective
# We probe from the host as a proxy — same host network
if curl --max-time 5 -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama /api/tags reachable from host"
else
  warn "Ollama not reachable at :11434"
  failures=$((failures+1))
fi

echo
if [[ "$failures" -gt 0 ]]; then
  warn "$failures probe(s) failed. The stack is up but something is off."
  warn "Re-running ./install.sh will retry; or check 'docker compose logs'."
  exit 1
fi

# Final message
echo
printf "%b%s%b\n" "$C_GREEN" "✓ All smoke checks passed." "$C_RESET"
echo
cat <<'EOF'
You're ready. Open http://localhost:5173 in your browser. The drawer toggle
is the small button at the top-right; press ] to toggle, or click it.

Try saying (or typing): "What ports does NodeAva use?" The avatar will call
the wiki tool and answer with real ports cited from the page.

To stop the stack:    docker compose down
To re-run the wizard: ./install.sh
To force fresh install: ./install.sh --full-reset

Workshop pedagogy moments to demo:
  • Open the drawer → see Brain / Voice / Avatar / Personality / Tools
  • Swap Brain to "Qwen3 4B Thinking" → ask the same question → see the
    flow diagram show the thinking phase plus chained wiki.search → wiki.open
  • Toggle Web search on → ask "What's recent in open-source LLMs?" →
    watch the browser.search tool fire
EOF
```

- [ ] **Step 2: Test**

```bash
bash -n scripts/install/09-smoke.sh
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | sed -n '/Smoke verify/,$p' | head -30
```

Expected: 3 ✓ lines + the final "you're ready" message.

- [ ] **Step 3: Commit**

```bash
git add scripts/install/09-smoke.sh
git commit -m "feat(installer): smoke verify + final 'you're ready' message"
```

---

## Task 11: End-to-end + idempotency verification

**Files:** none (manual verification).

Walk through the wizard front-to-back and verify the spec's success criteria.

- [ ] **Step 1: Full wizard run from clean state**

```bash
cd /media/rob/Workspace/Development/nodeava/.claude/worktrees/workshop-mvp-spec
NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | tail -40
```

Expected: all 9 steps print headings, each step says either "skipping (Keep)" or executes cleanly, smoke verify ends with 3 ✓ lines.

- [ ] **Step 2: Re-run for idempotency**

```bash
time NODEAVA_AUTO=1 ./scripts/install.sh 2>&1 | tail -10
```

Expected: under 60 seconds (per spec success criterion 2). Every step says "already installed" or skips cleanly.

- [ ] **Step 3: --full-reset test**

```bash
# First check what we'll wipe
ls state/ 2>&1
NODEAVA_AUTO=1 NODEAVA_FULL_RESET=1 ./scripts/install.sh 2>&1 | tail -20
```

Expected: wizard runs every step in its "do the action" branch. State.json is rewritten to defaults. Stack is rebuilt + recreated. Smoke passes.

NOTE: this WILL re-pull models if the models step's "reset" path is taken. Skip this sub-step if bandwidth is a concern; the idempotency test in step 2 is the workshop-relevant one.

- [ ] **Step 4: --help**

```bash
./scripts/install.sh --help
```

Expected: usage lines from the top of the script.

- [ ] **Step 5: bash -n on all installer files**

```bash
for f in scripts/install.sh scripts/install/*.sh; do
  bash -n "$f" && echo "OK: $f" || echo "FAIL: $f"
done
```

Expected: 11 OK lines.

- [ ] **Step 6: Verify dashboard still works after the install**

```bash
curl -fsS http://localhost:5173/ -o /dev/null -w "vite: HTTP %{http_code}\n"
curl -fsS http://localhost:8082/v1/state | python3 -c "import json,sys;d=json.load(sys.stdin);print('brain:',d['active']['brain'])"
```

Expected: Vite 200, brain is `qwen3-4b-instruct`.

- [ ] **Step 7: Final report**

Tell the controller:
- Status (PASSED or list of failing checks)
- E2E run time (Step 1 wall clock)
- Re-run time (Step 2 wall clock)
- Any concerns

If any fix was needed during testing, commit it with a clear message.

---

## Self-Review (already run; documenting for clarity)

**Spec coverage:**
- Spec Goal 1 (single entry `./install.sh`): Task 1
- Spec Goal 2 (preflight): Task 3
- Spec Goal 3 (inventory + per-component Keep/Reset/Skip): Task 4
- Spec Goal 4 (LLM serving branch): Task 5 + Task 6 + Task 8
- Spec Goal 5 (chatty teaching output): every task (each step prints WHY paragraph)
- Spec Goal 6 (idempotent): Task 11 step 2 verifies
- Spec Goal 7 (smoke verify): Task 10

**Argv coverage:** `--auto` Task 1; `--full-reset` Task 1 + Task 4; `NODEAVA_LLM_BACKEND` Task 5; `--help` Task 1.

**Cross-platform:** `detect_platform` in `_lib.sh` (Task 1); GPU overlay selection in Tasks 9.

**Risks from spec:**
- Sudo prompt on Linux (Risk 1): handled by Task 6 which calls setup-linux.sh; that script already handles the sudo case.
- Catalog mutation idempotency (Risk 5): Task 8 step explicitly greps for existing entry before appending.

**Type consistency:**
- `NODEAVA_PLATFORM`, `NODEAVA_GPU`, `NODEAVA_VRAM_MB`, `NODEAVA_LLM_BACKEND`, `NODEAVA_INV_*` env var names used consistently across tasks.
- `step_heading N total name` signature consistent (N=current, total=9).
- `prompt_choice` returns lowercase letter via stdout consistently.

**No placeholders:** every step has actual code + commands + expected output.

---

## What comes next (Plan #10)

Plan #10 covers benchmark + walkthrough overlay + workshop polish. Benchmark hooks into the existing event stream (tok/s, RTF, first-word latency). Walkthrough is a Shepherd-style guided tour. Polish addresses dry-run feedback.
