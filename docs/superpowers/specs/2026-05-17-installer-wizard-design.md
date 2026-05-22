# Plan #9 — Installer Wizard Design

**Status:** Draft (awaiting user review)
**Author:** Rob Lucas + Claude
**Date:** 2026-05-17
**Implements workshop block:** "Install / preflight" (the first 30-minute block of the 3-hour session)

## Why this exists

Workshop attendees arrive with their laptops and a 3-hour window. Block 1 is "install and preflight." Today that's a manual sequence — `docker compose build`, `ollama pull`, edit `state/current.json`, etc. Attendees with varied skill levels need a single guided onramp that doubles as a teaching moment: the wizard explains WHY each step happens so attendees understand the system as they install it.

The wizard is the attendee's FIRST interaction with NodeAva. It also has to be re-runnable: an attendee whose workshop session goes sideways at hour 2 should be able to run the wizard again and recover.

## Goals

1. A single interactive entry point: `./install.sh` from the repo root.
2. Comprehensive preflight that catches problems before they cause cascading failures (no GPU, no Docker, no disk space, captive wifi).
3. Inventory step that detects already-installed/configured components and offers per-component Keep / Reset / Skip. This is also where "reset to factory" lives — no separate `reset.sh`.
4. Branching on LLM serving choice: Ollama (default) or llama.cpp (advanced). Detects existing containers and offers a choice when both are available.
5. Chatty teaching output — each step starts with a 1-2 paragraph WHY explanation. Color-coded.
6. Idempotent: re-running the wizard twice in a row is always safe.
7. End with a smoke verification: curl `/v1/catalog` and `/v1/state`, confirm everything is green, point to `http://localhost:5173`.

## Non-goals

- Building a llama.cpp container from scratch. If attendee wants llama.cpp, they bring their own running container; the installer detects it and registers a catalog entry.
- Uninstall. Attendees run `docker compose down` and remove `~/.ollama/models/*` themselves if they want a clean slate.
- USB-stick fallback as an explicit feature. Pre-pulled models on disk are detected automatically via the inventory step — that's the implicit USB story.
- Native Windows. WSL2 only.
- Automated `gh` / `git` setup. Attendees are expected to have cloned the repo.
- CI mode beyond a basic `--auto` flag for the smoke test.

## Architecture

```
scripts/
├── install.sh                    # entry point (~150 LoC); dispatches steps
└── install/
    ├── _lib.sh                   # shared utils: prompt, color, platform-detect, log
    ├── 01-welcome.sh             # banner + agenda
    ├── 02-preflight.sh           # platform, GPU/VRAM, Docker, disk, network
    ├── 03-inventory.sh           # detect existing installs + offer Keep/Reset/Skip
    ├── 04-llm-choice.sh          # Ollama vs llama.cpp branch
    ├── 05-install-ollama.sh      # runs only on Ollama branch; calls setup-{linux,mac}.sh
    ├── 06-pull-models.sh         # ollama pull qwen3:4b-instruct + smollm2:360m
    ├── 06-register-llamacpp.sh   # on llama.cpp branch: writes a catalog entry
    ├── 07-build-stack.sh         # docker compose build orchestrator
    ├── 08-up-stack.sh            # docker compose up -d
    └── 09-smoke.sh               # curl /v1/catalog + /v1/state + final message
```

Each step is its own bash file sourced (not exec'd) by `install.sh`, so they can read/write the shared environment variables (`NODEAVA_PLATFORM`, `NODEAVA_LLM_BACKEND`, etc.) `_lib.sh` defines once.

The naming uses `NN-name.sh` numbering for grep-friendly ordering. Two `06-*` files are alternates (only one runs based on `NODEAVA_LLM_BACKEND`).

## Wizard flow detail

### Step 1: Welcome

Two-screen banner. First screen prints the workshop title + what the wizard does. Second screen prints the agenda:

```
NodeAva Installer Wizard

This wizard will get a self-contained digital human running on your laptop.
You'll watch each piece of the pipeline being assembled — STT, LLM, TTS,
avatar, orchestrator — and learn why each one is there.

Steps:
  1. Preflight    — verify your machine
  2. Inventory    — find what's already installed
  3. LLM serving  — Ollama or llama.cpp
  4. Models       — download Qwen3 4B Instruct + SmolLM2 360M
  5. Stack        — bring up the docker services
  6. Smoke        — confirm everything is green

Press Enter to begin, or Ctrl+C to cancel.
```

### Step 2: Preflight

Five checks, each with a one-line explanation displayed before the result:

| Check | Pass criterion | Fail behavior |
|-------|----------------|---------------|
| Platform | `uname -s` is `Linux` or `Darwin`; reject Windows native | Hard fail |
| GPU + VRAM | `nvidia-smi` / `rocm-smi` / Apple Silicon detection; ≥ 6 GB VRAM | Warn (allow continue with CPU fallback warning) |
| Docker reachable | `docker info` returns 0 | Hard fail with instructions to start daemon |
| Disk free | ≥ 10 GB free on `/` (or where `~/.ollama` will live) | Hard fail at < 5 GB; warn at < 10 GB |
| Network | `curl --max-time 5 https://ollama.com` returns 200 | Warn (attendee can proceed if models already pulled) |

Output:

```
[1/6] Preflight — verifying your machine is workshop-ready.

  Why this matters: the workshop expects a few baseline conditions. Catching
  problems here saves time later (a captive-wifi portal at hour 1 ruins the
  rest of the session).

  ✓ Platform: Linux x86_64 (kernel 6.17)
  ✓ GPU: NVIDIA RTX 4070 · 12 GB VRAM (workshop floor is 8 GB)
  ✓ Docker: reachable (Docker Engine 27.3.0)
  ✓ Disk: 142 GB free on /
  ✓ Network: ollama.com reachable

  All checks passed. Press Enter to continue.
```

On any hard fail, the wizard prints a recovery hint and exits non-zero.

### Step 3: Inventory

Detects existing pieces and offers per-item action:

| Detected | Prompt |
|----------|--------|
| Ollama at `:11434` reachable | "Found Ollama at :11434. Keep [K] / Reset (uninstall+reinstall) [R] / Skip [S]?" |
| Models in `ollama list` matching catalog | "Found qwen3:4b-instruct (2.5 GB) and smollm2:360m (280 MB). Keep / Re-pull / Skip?" |
| `nodeava-orch:latest` docker image | "Found nodeava-orch:latest (built 2 hours ago). Keep / Rebuild / Skip?" |
| `state/current.json` exists with non-default values | "Found state.json (active brain: qwen3-4b-thinking). Keep / Reset to defaults?" |
| Any llama.cpp container running | "Found llama.cpp container: ghcr.io/ggml-org/llama.cpp:server-cuda on port 8081. (Will be offered as LLM option in next step.)" |

Top of the inventory, after detection, before prompts:

```
Or press [F]ull reset — nuke everything, run all install steps fresh.
```

Choosing F skips per-component prompts and forces every step to do its full work.

### Step 4: LLM serving choice

Branches based on inventory findings:

- **Only Ollama detected (or neither)**: skip the prompt, default to Ollama branch.
- **Only llama.cpp container detected**: ask "Use existing llama.cpp container? [Y]es / [N]o (install Ollama instead)"
- **Both detected**: ask "Which LLM serving layer? [O]llama (recommended) / [L]lama.cpp (advanced)"

The teaching text:

```
NodeAva originally used llama.cpp (Plans #1–#6) before migrating to Ollama in
Plan #7. Why we switched:
  • Cross-platform: same install on Linux, WSL2, and macOS
  • Auto VRAM management — Ollama swaps models in and out without restarts
  • Single API across local + (with LiteLLM) cloud models

llama.cpp is still useful for: passing custom flags (--ctx-size, --temp, etc.),
benchmarking with a specific model file, or production deployments where you
need bare-metal control.

For the workshop, Ollama is recommended. You can swap to llama.cpp later via
the dashboard's brain selector.
```

Sets `NODEAVA_LLM_BACKEND=ollama` or `=llamacpp` for downstream steps.

### Step 5: Install Ollama (Ollama branch only)

Skipped if Ollama already installed (per inventory).

Otherwise calls `bash scripts/setup-linux.sh` or `bash scripts/setup-mac.sh` (already shipped in Plan #7). On Linux, this requires sudo for the systemd dropin that binds Ollama to 0.0.0.0:11434 (for Docker → host reachability); the wizard surfaces this requirement and prompts before sudo.

### Step 6a (Ollama branch): Pull models

```bash
ollama pull qwen3:4b-instruct  # ~2.5 GB
ollama pull smollm2:360m        # ~280 MB
```

Skipped per-model if `ollama list` already shows them.

Teaching text:

```
We pull two models:
  • qwen3:4b-instruct  — fast, conversational, no chain-of-thought. The workshop default.
  • smollm2:360m       — tiny 360M-parameter model. Used in Demo 16 to show the
                         contrast between a competent model and a "dumb" one
                         running the same pipeline.

Total download: ~2.8 GB. On good wifi this takes 1–3 minutes; on conference
wifi expect 5–20 minutes.
```

### Step 6b (llama.cpp branch): Register catalog entry

Skipped if `configs/catalog.yml` already has an `openai-compatible` brain pointing to the detected llama.cpp container.

Otherwise: detect the container's exposed port and currently-loaded model via `docker inspect` and `curl http://localhost:<port>/v1/models`, then APPEND a brain entry to `configs/catalog.yml`:

```yaml
  - id: llamacpp-local
    label: "llama.cpp local (advanced)"
    kind: openai-compatible
    url: http://localhost:8081/v1
    model: <detected-model-name>
    thinks: false
    default: true   # only set if user chose llama.cpp as the workshop default
```

And update `state/current.json` to set `brain: llamacpp-local`.

The catalog parser already accepts `kind: openai-compatible` (Plan #7 Task 4).

### Step 7: Build orchestrator image

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml \
  build orchestrator
```

Picks the right GPU compose file based on `NODEAVA_PLATFORM` (nvidia / amd / mac / cpu). Skipped if image is younger than 1 hour AND inventory's "Keep" was chosen.

### Step 8: Bring up the stack

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu-nvidia.yml \
  up -d orchestrator tts stt searxng
```

Waits up to 60s for all four containers to report `healthy`. Reports per-service status as they come up.

Teaching text names each service:

```
Starting four services:
  • orchestrator  — the agentic-loop brain that routes requests to tools
  • tts           — Kokoro neural text-to-speech (port 8880)
  • stt           — Whisper speech-to-text (port 8080)
  • searxng       — bundled meta-search for the browser.search tool

Ollama is on your host machine (not in Docker) and serves the LLM.
```

### Step 9: Smoke verification

Runs three live probes:

1. `curl http://localhost:8082/v1/state` — confirms orchestrator + state load
2. `curl http://localhost:8082/v1/catalog | jq '.brains | length'` — confirms catalog loaded
3. `curl http://localhost:11434/api/tags` — confirms Ollama reachable from the host

If all three pass:

```
✓ All smoke checks passed.

You're ready. Open http://localhost:5173 in your browser. The drawer toggle
is the small button top-right; press ] to toggle, or click it.

Try saying "What ports does NodeAva use?" — the avatar will call the wiki tool
and answer with real ports cited from the page.

To stop the stack: docker compose down
To re-run this wizard: ./install.sh
```

If any fails: print the failing probe's stderr + a recovery hint.

## Argv / env vars

| Flag / env | Effect |
|---|---|
| `./install.sh --help` | Print usage and exit |
| `./install.sh --auto` | Suppress all Enter-to-continue pauses; useful in CI / dry-run |
| `./install.sh --full-reset` | Force "full reset" at step 3, skipping the inventory prompt |
| `NODEAVA_LLM_BACKEND=ollama \| llamacpp` | Override the LLM-serving choice (skips step 4 prompt) |
| `NODEAVA_QUIET=1` | Suppress teaching text; just run the steps. Useful for impatient devs. |

## Output style

Color codes (defined in `_lib.sh`):
- **Cyan** — step heading (`[3/6] Inventory ...`)
- **Gray** — teaching prose
- **Green** — `✓ pass`
- **Yellow** — `! warning`
- **Red** — `✗ fail`
- **Bold** — prompts ("Press Enter to continue")

Tab-completion via `prompt_yn`, `prompt_choice`, and `pause` helpers in `_lib.sh`.

Cross-platform: `_lib.sh` falls back to plain ASCII if `TERM` is unset or the terminal doesn't support color (`!tput colors` returns < 8).

## Error handling

Each step file uses `set -euo pipefail`. The top-level `install.sh` traps `ERR` and prints:

```
✗ Step <N> failed: <step name>
  <last command>
  exit code: <code>

What this likely means:
  <hint mapped by step name>

You can re-run ./install.sh — completed steps will be detected and skipped.
```

Common hints are defined in `_lib.sh` (`hint_for_step()` switches on step name).

## Testing strategy

The wizard runs interactively and exercises the system end-to-end, so testing approaches mirror Plan #6/#7's "smoke + manual" pattern:

1. **Bash syntax checks** (`bash -n` on every step file) — quick CI gate.
2. **Dry-run mode**: `./install.sh --auto --dry-run` (a new `--dry-run` flag that calls each step's `dry_run()` function instead of its action) — prints what WOULD happen without doing it. Catches argv typos in step scripts.
3. **Manual smoke**: run `./install.sh --full-reset` on the dev machine end-to-end, verify the stack comes up clean.
4. **Re-run idempotency**: run twice in a row; second run should fast-skip all completed steps.

Pytest is not required — the installer is bash, not Python. The orchestrator's test suite continues to cover the catalog parser changes.

## Cross-platform notes

| Platform | Special handling |
|----------|------------------|
| Linux + NVIDIA | Default reference path. systemd dropin for Ollama. |
| Linux + AMD (ROCm) | Same as NVIDIA. ROCm detection via `rocm-smi`. |
| Linux + CPU only | Warn at preflight; proceeds. Models run on CPU (slow). |
| Linux WSL2 | Detected via `/proc/version` containing `microsoft`. Same install as Linux but a note about WSL networking. |
| macOS Apple Silicon | Brew install. No systemd. Docker Desktop required. |
| macOS Intel | Warn at preflight ("Apple Silicon recommended for Metal acceleration"); proceeds. |
| Windows native | Hard fail with WSL2 instructions. |

## Risks & open questions

1. **Sudo prompt on Linux** for the Ollama systemd dropin (`OLLAMA_HOST=0.0.0.0:11434`). Some workshop attendees may not have sudo. Mitigation: setup-linux.sh already handles the no-sudo case by printing manual instructions; the wizard surfaces this clearly.

2. **Conference wifi captive portals** — preflight catches this via the ollama.com probe. If the probe fails the wizard offers to proceed anyway if Ollama is already installed (i.e., pure offline mode using pre-pulled models).

3. **Docker Desktop on Mac** uses a Linux VM with no host-network passthrough. The setup-mac.sh + Plan #7 work already documented Ollama-must-run-on-host; wizard reaffirms.

4. **Brew is required on Mac** — preflight checks for `brew` and prints an install URL if missing.

5. **catalog.yml mutation risk**: the llama.cpp branch APPENDS a brain entry. If the attendee re-runs `--full-reset` they might end up with duplicate entries. Mitigation: idempotent insertion (check for `id: llamacpp-local` before appending).

6. **Workshop time budget** — wizard takes 5–20 minutes wall-clock depending on wifi and existing state. The 30-minute block 1 has room for this plus instructor explanation.

## Success criteria

Plan #9 is done when:

1. A fresh attendee laptop (Linux + NVIDIA, no Ollama installed, no models) can run `./install.sh` and end with `localhost:5173` showing the dashboard and the avatar responding to "What ports does NodeAva use?" with wiki-cited port numbers.
2. Re-running `./install.sh` on the same laptop completes in under 60 seconds (everything detected, all steps skipped, smoke passes).
3. `./install.sh --full-reset` wipes state to defaults and reinstalls cleanly.
4. The llama.cpp branch successfully registers a catalog entry when an attendee has a running llama.cpp container, and the dashboard's brain selector shows it as the active option after the wizard completes.
5. All existing orchestrator tests (≥ 146) still pass.

## What comes next (Plan #10)

Plan #10 covers benchmark + walkthrough overlay + workshop polish. Benchmark hooks into the existing event stream (tok/s, RTF, first-word latency). Walkthrough is a Shepherd-style guided tour layered on top of the dashboard. Polish addresses whatever else surfaces during workshop dry-runs.
