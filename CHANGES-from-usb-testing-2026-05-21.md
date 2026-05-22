# Workshop Kit — Session Changes

**Last updated:** 2026-05-21 (multi-session, two Claude agents on the same machine)
**Kit base build:** 2026-05-19 (`VERSION`: commit `66b60db`, branch `worktree-workshop-mvp-spec`, amd64)
**Test machine:** Dell laptop, NVIDIA RTX PRO 2000 Blackwell Generation Laptop GPU (sm_120, 8 GB), Ubuntu 24.04, kernel 6.17.0-29, native Linux (not WSL2)

Tested end-to-end on the Linux Blackwell box above. WSL2 and macOS paths got the same fixes applied but were not booted; should be exercised before workshop day.

**Note on co-author:** A second Claude agent on this machine made parallel changes mid-session — added a custom Blackwell build path (failed, see Session 2 Issue 16 below), then reverted several `setup.sh` fixes. Session 2 below restored the reverted edits, kept the parts of the other agent's work that were genuine improvements, and added new fixes that surfaced from end-to-end testing. **If you're coordinating with another agent on a different machine: read Session 2 first — it has the current state and lessons that aren't yet end-to-end tested elsewhere.**

---

## Session 1 — Issues caught and fixed

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 1 | `install.sh` step 2 silently exited right after printing "Platform: linux" | `nvidia-smi` exits 6 ("No devices found") on hybrid-graphics laptops or when GPU is mis-bound. `set -euo pipefail` + the pipeline `nvidia-smi … \| head -1` propagates the non-zero status; ERR trap fires; `2>/dev/null` hid the message. | `02-preflight.sh`: run `nvidia-smi` inside an `if`, validate `vram_mb` is an integer (the "No devices found" string also leaks to stdout). Same guard for the rocm-smi branch (grep returns 1 on no match → pipefail trap). |
| 2 | install.sh step 3 looked hung at "How would you like to handle the existing pieces?" | `prompt_choice` writes the question + menu + `Choice:` prompt to **stdout**, but the caller uses `choice="$(prompt_choice …)"` which captures stdout. The user saw nothing while `read -r ans < /dev/tty` blocked. | `_lib.sh`: write all user-facing prose to `/dev/tty`; only the chosen letter goes to stdout. |
| 3 | Blackwell GPU not visible to `nvidia-smi` despite driver installed and kernel modules loaded | NVIDIA driver 580.142 was installed with **closed** kernel modules; Blackwell GPUs require **open** kernel modules. Kernel log showed `RmInitAdapter failed! (0x22:0x56:897)`. | Host-level fix (not script-fixable): `sudo ubuntu-drivers install nvidia:595-open` + reboot. Documented in this file. |
| 4 | Step 8 `docker compose up` errored with `could not select device driver "nvidia" with capabilities: [[gpu]]` | `nvidia-container-toolkit` not installed; Docker had only `runc`, not `nvidia` runtime. Required for any NVIDIA GPU including Blackwell (stt uses Vulkan in-container). | New script `scripts/install-nvidia-container-toolkit.sh` (idempotent, auto-detects amd64/arm64). Preflight detects missing runtime → prompts "Install now?" → runs the installer → re-verifies. |
| 5 | `setup.sh` step 5 staged models but Ollama daemon couldn't see them ("ollama list" empty) | On Linux, the systemd Ollama service runs as user `ollama` reading from `/usr/share/ollama/.ollama/models`. setup.sh staged to `$HOME/.ollama` first by default. Step 6 of install.sh then fell through to `ollama pull` over the network — defeating `--offline`. | `setup.sh`: detect the `ollama` system user on Linux/WSL2 and stage to `/usr/share/ollama/.ollama/models` with sudo. Chown to ollama:ollama after copy. |
| 6 | Wrong Ollama model tag in standalone setup scripts | `setup-linux.sh` and `setup-mac.sh` both pulled `qwen3:4b`. install.sh step 6 expects `qwen3:4b-instruct`. Mismatch caused a redundant network pull. | Both setup scripts updated to `qwen3:4b-instruct`. |
| 7 | Kokoro TTS container crashed with `CUDA error: no kernel image is available for execution on the device` on Blackwell | The bundled `ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4` image ships PyTorch < 2.6, which has no precompiled CUDA kernels for sm_120. v0.3.0 same problem. | `02-preflight.sh`: detect compute cap ≥ 12.0 → set `NODEAVA_GPU_BLACKWELL=1` and warn. `08-up-stack.sh`: when flag set, auto-write `docker-compose.override.yml` that pins `ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4` + `DEVICE_TYPE=cpu` + clears the GPU device reservation. CPU TTS: ~2-5 s/sentence vs <0.5 s on GPU; voice quality identical. |
| 8 | Step 8 reported "Stack is up" but the dashboard rendered "Dashboard offline (orchestrator unreachable)" | Nginx config had a stale upstream: `proxy_pass http://llm:8080/` for `/api/llm/`. The `llm` container was removed when Plan #7 migrated to Ollama+orchestrator; nginx crashed on startup with `host not found in upstream "llm"`. | `frontend/nginx.conf`: `/api/llm/` → `http://orchestrator:8082/`. |
| 9 | After fixing `/api/llm/`, dashboard still showed "offline" | Dashboard's `dashboard/api.js` fetches `/api/orch/v1/catalog` and `/api/orch/v1/state` for the control plane. Nginx had no `/api/orch/` location → 404 → `_loadInitial` failed. | `frontend/nginx.conf`: added `location /api/orch/` proxying to `orchestrator:8082` (sibling of `/api/llm/`). |
| 10 | Step 8 aborted with `dependency failed to start: container nodeava-workshop-tts-1 is unhealthy` even though tts became healthy ~30 s later | Compose's `depends_on` declared the dependency failed before tts (CPU mode, model download on first boot) reached the healthcheck. The dependent containers (frontend) were not created, and `docker compose up -d` exited non-zero, which install.sh's ERR trap treated as fatal. | `08-up-stack.sh`: `up -d \|\| true` so compose's verdict doesn't kill the wizard; wait deadline raised 60 s → 240 s; after the wait, **re-run** `up -d` to create any containers that were skipped; final state report tells the truth. |
| 11 | Step 9 reported "All smoke checks passed" but the dashboard was unreachable (stt + tts + frontend were `Created`, never `Started`) | Step 9 only probed orchestrator `:8082` and Ollama `:11434`. Both were up. Smoke probes lied. | `09-smoke.sh`: added probes for stt `:8080`, tts `:8880`, frontend `:3000`, plus the end-to-end `/api/orch/v1/state` route through nginx. 3 probes → 7 probes. |
| 12 | Uninstall left workshop containers, network, pulled images, source tree, and ollama models behind | Original script only purged Docker + Ollama packages. | `uninstall-docker-ollama.sh` now does: `docker compose down -v --remove-orphans`, removes containers by name **and** label `com.docker.compose.project=nodeava-workshop`, removes project-built images (`nodeava-orch`, `nodeava-kokoro-rocm`), enumerates RepoTags from USB tarballs and `docker rmi`s each base image, also removes kokoro-fastapi-cpu (auto-pulled at install time, not on USB), removes the compose network and labeled volumes, removes `~/nodeava-workshop/`, removes `~/.ollama`, purges `nvidia-container-toolkit` + apt source + keyring. Extended verification block. |
| 13 | Windows install path used hybrid Docker Desktop (Windows side) + WSL2 | Friction-minimizing for non-technical attendees but Docker Desktop has license restrictions, slower I/O across the `/mnt/c/` boundary, and forced special-case branches throughout the kit. | Collapsed: `setup.bat` no longer mentions Docker Desktop. `setup.sh`'s `wsl2)` branches for Docker step and Ollama step are merged into `linux\|wsl2)` — same `installers/linux/install-*.sh` path, native Docker daemon inside WSL2. `02-preflight.sh` drops the "enable WSL Integration in Docker Desktop" instructions; falls through to the standard `nvidia-container-toolkit` auto-install (with a WSL2 note about needing recent NVIDIA Game Ready driver + `wsl --update`). |

---

## Files modified on the USB

| File | What changed |
|---|---|
| `setup.sh` | Welcome banner updated; Step 2 Docker `wsl2` branch merged into `linux\|wsl2`; Step 3 Ollama same merge; Step 5 model staging prefers daemon path on Linux/WSL2; "Ollama not responding" hint updated for WSL2 |
| `setup.bat` | Dropped Docker Desktop messaging; clarified that everything installs inside WSL2 |
| `uninstall-docker-ollama.sh` | Comprehensive teardown (compose stack, images, source tree, ~/.ollama, nvidia-container-toolkit, kokoro-fastapi-{cpu,gpu}, etc.) |
| `source/nodeava-workshop/scripts/install/_lib.sh` | `prompt_choice` writes to `/dev/tty` |
| `source/nodeava-workshop/scripts/install/02-preflight.sh` | nvidia-smi / rocm-smi probes guarded; Blackwell detection sets `NODEAVA_GPU_BLACKWELL`; nvidia-container-toolkit auto-install offer with WSL2-aware messaging |
| `source/nodeava-workshop/scripts/install/08-up-stack.sh` | Auto-writes Blackwell CPU TTS override; `up -d \|\| true`; 240 s health wait; re-up after wait; accurate final state |
| `source/nodeava-workshop/scripts/install/09-smoke.sh` | Added probes for stt, tts, frontend, and end-to-end nginx `/api/orch/` route (3 → 7 probes) |
| `source/nodeava-workshop/scripts/setup-linux.sh` | `qwen3:4b` → `qwen3:4b-instruct` |
| `source/nodeava-workshop/scripts/setup-mac.sh` | Same tag fix |
| `source/nodeava-workshop/frontend/nginx.conf` | `/api/llm/` upstream points at `orchestrator:8082`; added `/api/orch/` location for the dashboard control plane |

## Files added on the USB

| File | Purpose |
|---|---|
| `source/nodeava-workshop/scripts/install-nvidia-container-toolkit.sh` | Idempotent installer for the NVIDIA Container Toolkit. Auto-detects amd64/arm64. Adds NVIDIA keyring + apt source, installs the package, runs `nvidia-ctk runtime configure --runtime=docker`, restarts Docker, smoke-tests with `docker run --gpus all`. Invoked automatically by `02-preflight.sh` when the runtime is missing and the user accepts the prompt. |
| `CHANGES.md` | This file. |

## Files NOT changed but worth noting

- `installers/DockerDesktop-Win.exe` (618 MB) and `installers/Ollama-Win.exe` (2 GB) are still on the USB but **no longer referenced by the install path**. Safe to delete to free ~2.6 GB if a leaner USB is wanted.
- `source/nodeava-workshop/scripts/setup.ps1` is the dev workflow for cloning the repo directly on Windows-native (not the USB path) — left alone.
- The Kokoro GPU image (`ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4`) is still bundled; only Blackwell hosts get the CPU override.

---

## Known outstanding issues

| Issue | Severity | Workaround | Real fix |
|---|---|---|---|
| Kokoro TTS GPU image lacks Blackwell (sm_120) PyTorch kernels | Medium — affects RTX 50-series + RTX PRO Blackwell laptops | Auto-detected; falls back to CPU TTS (~2-5 s/sentence) | Upstream rebuild of `kokoro-fastapi-gpu` against PyTorch 2.6+; watch `ghcr.io/remsky/kokoro-fastapi-gpu` for a tag built after Feb 2026 |
| Kokoro tarball "peek" in setup.sh step 4 reads the entire 6.9 GB tar to find `manifest.json` — silent for ~55 s on USB I/O | Low — confusing first-time UX | Wait it out | Pipe through `head -c 65536` to SIGPIPE-close after enough JSON, or print "checking manifest…" before the peek |
| WSL2 model-staging assumes Ollama is installed inside WSL2 (now true with the simplified path), but does not detect or guide if user has Ollama on Windows-side | Low — only affects users running a hybrid setup | Document; or delete Ollama-Win.exe from USB | n/a — by design after the WSL2 simplification |
| Windows + macOS paths got fixes applied but were not booted/tested end-to-end this session | Medium | Test on Windows + macOS before workshop day | Run through the same uninstall → setup → install → smoke loop on each |

---

## How to verify the USB is ready for a fresh test

```bash
# From any Linux/WSL2 box, with the USB mounted at /media/<user>/Workshop:
USB=/media/<user>/Workshop/Workshop
bash -n $USB/setup.sh
bash -n $USB/uninstall-docker-ollama.sh
bash -n $USB/source/nodeava-workshop/install.sh
for f in $USB/source/nodeava-workshop/scripts/install/*.sh \
         $USB/source/nodeava-workshop/scripts/install-nvidia-container-toolkit.sh \
         $USB/source/nodeava-workshop/scripts/setup-{linux,mac}.sh; do
  bash -n "$f" || echo "SYNTAX FAIL: $f"
done
# Expect zero output beyond filenames — every script parses clean.
```

## Full reset + reinstall test sequence (Linux)

```bash
sudo /media/<user>/Workshop/Workshop/uninstall-docker-ollama.sh   # ~30 s
# Open a fresh shell so the docker group membership clears cleanly
cd /media/<user>/Workshop/Workshop
./setup.sh                                                         # 5-15 min depending on USB speed
# At setup step 1 if Blackwell: "Blackwell GPU detected — step 4 will skip the kokoro-fastapi-gpu tarball"
# At setup step 5 expect: "models staged to /usr/share/ollama/.ollama/models"
# At install step 2 if Blackwell: "Blackwell-class GPU (compute cap 12.0)"
# At install step 2 if nvidia-container-toolkit missing: prompts "Install now? [Y/n]"
# At install step 3 inventory: pick 'k'
# At install step 8: writes Blackwell-tts overlay (CPU image), takes 30-90 s for CPU TTS first-boot
# At install step 9: should show 7 ✓ probes (orchestrator, catalog, ollama, stt, tts, frontend, /api/orch/)
```

---

# Session 2 — Co-agent collisions, end-to-end testing, voice-id bug

This session ran after Session 1 in a separate Claude conversation on the same machine, with a parallel agent also making changes. Several Session 1 fixes were reverted by the other agent and had to be restored; new bugs surfaced once the dashboard could actually be exercised end-to-end (which only became possible after Session 1's nginx fix); and a custom Blackwell TTS rebuild attempt failed.

## Session 2 — Additional issues caught and fixed

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| 14 | After `Set TTS via dashboard` worked once, future runs of `setup.sh` re-loaded the bundled `ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4` tarball (~14 GB on disk, ~55 s of USB I/O) even though the image is useless on this GPU | `setup.sh` step 4 indiscriminately loads every `.tar.gz` in `docker-images/$ARCH/`. No GPU-arch awareness. | `setup.sh` step 1 now detects Blackwell (compute cap ≥ 12.0 via `nvidia-smi --query-gpu=compute_cap`) and exports `SETUP_GPU_BLACKWELL=1`. Step 4 checks the flag and `continue`s past any tarball whose name matches `*kokoro-fastapi-gpu*`. The tarball is left on the USB so non-Blackwell attendees still get the GPU image. |
| 15 | First TTS call from the dashboard returned no audio; TTS container logs showed `WARNING: Invalid request: Voice 'bella' not found. Available voices: af_alloy, ..., af_bella, ...` and HTTP 400 | Latent voice-id mismatch since Plan #7/8: the orchestrator's `state.voice` holds the UI-facing id (`"bella"`), the catalog has a `kokoro_voice` field mapping to the actual Kokoro voice (`"af_bella"`), but `TTSManager._loadVoiceFromState()` did the mapping as fire-and-forget from the constructor and `setVoice()` had no mapping at all. First synthesis raced the catalog fetch and sent the bare UI id. The bug was hidden until Session 1 fixed the nginx `/api/orch/` route — before that the dashboard couldn't load at all so this code path was never reached. | `TTSManager.js`: (a) `_loadVoiceFromState()` return value captured as `this._voiceReady` promise; (b) `_processNext()` awaits `_voiceReady` before the first utterance; (c) `setVoice()` rewritten to detect kokoro-style ids by regex `^[a-z]{2}_` and use them directly, otherwise async-resolve via `/api/orch/v1/catalog`. Callers don't need to know the difference. |
| 16 | **Failed Blackwell GPU TTS rebuild attempt.** Other agent created `docker/kokoro-blackwell/Dockerfile`, `docker-compose.gpu-blackwell.yml`, and rewrote `08-up-stack.sh` to auto-detect a local `kokoro-fastapi-blackwell:nightly` image and use it instead of the CPU fallback. The user built the image (45.6 GB). TTS container exited 2 in a restart loop with `python: can't open file '/app/download_model.py': [Errno 2] No such file or directory`. The Dockerfile was missing a file the upstream Kokoro entrypoint expects. | Custom Dockerfile (now removed) only `COPY`'d a subset of the upstream repo into `/app/`. Upstream Kokoro's entrypoint at runtime invokes `python /app/download_model.py` to lazy-fetch model weights — a file the custom build never copied in. | Removed the broken image (`docker rmi kokoro-fastapi-blackwell:nightly` — freed 45 GB), deleted the Dockerfile (`docker/kokoro-blackwell/Dockerfile`), deleted the manual overlay (`docker-compose.gpu-blackwell.yml`). Kept the auto-generated `docker-compose.blackwell-tts.yml` (currently points at CPU image) and the detection block in `08-up-stack.sh` — so if a future working Blackwell rebuild is produced, the kit picks it up automatically. **For anyone retrying the Blackwell rebuild path: don't follow the deleted Dockerfile recipe; it's missing `download_model.py` (and possibly other files). Start from the upstream Kokoro-FastAPI repo's Dockerfile, swap the PyTorch base image to one with sm_120 kernels (PyTorch 2.6+ / CUDA 12.8+), keep the rest of the build context intact.** |
| 17 | Several Session 1 fixes to `setup.sh` had been reverted by the other agent mid-session — missing: --offline/--online arg parsing, disk space check (20 / 40 GB thresholds), welcome banner Docker line, step 2 header rename ("Docker Desktop" → "Docker"), `linux\|wsl2` collapsed branches in Step 2 and Step 3, `$INSTALL_MODE_FLAG` propagation to bundled installers, `install-ollama.sh` invocation, daemon-path preference for model staging, `INSTALL_ENTRY` fallback at install.sh handoff. | The other agent was working from an older mental model of setup.sh and rewrote sections without picking up Session 1's changes. | All restored via targeted `Edit` calls (not a wholesale rewrite — the other agent's legitimate improvements were preserved, namely: better Ollama startup retry loop with 30 s deadline, `sudo -E` for `SUDO_USER` preservation, better post-install verification of `docker info`, and the 0.0.0.0 systemd drop-in applied at setup time instead of waiting for the wizard). |
| 18 | The auto-generated `docker-compose.blackwell-tts.yml` from `08-up-stack.sh` (other agent's rewrite) became empty (0 bytes) at some point — TTS then started against the base compose's GPU image, hit the Blackwell kernel error, restart-looped. | Unknown trigger — possibly the other agent's overlay-write block had a transient bug, possibly the user wrote it then truncated it. | Direct re-write of the file with the correct CPU pinning: `image: ghcr.io/remsky/kokoro-fastapi-cpu:v0.2.4`, `DEVICE_TYPE=cpu`, empty `devices: []`. Confirmed `08-up-stack.sh`'s detect-and-write block will re-create it on every install run, so a future revert can't strand the stack. |
| 19 | Apt cache + journal logs + downloaded installers accumulated to ~3-4 GB of bit-rot on root partition during testing | Normal accumulation from rebooting, apt-installing toolkit, journaling | Documented cleanup snippet in this file (apt clean, journalctl --vacuum, prune dangling Docker images, remove one-time .deb installers in ~/Downloads). |

## Session 2 — Files modified beyond Session 1

| File | What changed in Session 2 |
|---|---|
| `setup.sh` | Restored 9 reverted Session 1 fixes; added new Step 1 Blackwell detection (`SETUP_GPU_BLACKWELL` flag); added new Step 4 skip of `*kokoro-fastapi-gpu*` tarballs when Blackwell flag set; output now reports both loaded **and skipped** counts |
| `setup.bat` | Restored Session 1 wording (Docker Desktop messaging dropped again by other agent) |
| `source/nodeava-workshop/frontend/src/tts/TTSManager.js` | Constructor: `_loadVoiceFromState()` captured as `this._voiceReady` promise. `_processNext()`: `await this._voiceReady` before first utterance. `setVoice()`: regex-detects kokoro vs UI id, async-resolves UI ids via `/api/orch/v1/catalog`. |
| `source/nodeava-workshop/scripts/install/08-up-stack.sh` | Significantly enhanced by other agent (preserved): service list is now a `${services_to_start[@]}` array; added `$mac_overlay`, `$gpu_overlay`, `$blackwell_overlay`, `$user_override_overlay` variables; detects local `kokoro-fastapi-blackwell:nightly` and auto-writes `docker-compose.blackwell-tts.yml` pointing at either (a) the local Blackwell image if present, or (b) the CPU fallback if not. The `\|\| true` after `up -d`, 240 s health wait, re-up, and accurate final state report from Session 1 are all still present. |

## Session 2 — Files deleted

| File | Why |
|---|---|
| `source/nodeava-workshop/docker/kokoro-blackwell/Dockerfile` (USB + staged) | The Blackwell custom rebuild it produced was broken (missing `download_model.py`). Recipe was misleading. |
| `source/nodeava-workshop/docker/kokoro-blackwell/` directory (USB + staged) | Empty after Dockerfile removal |
| `source/nodeava-workshop/docker-compose.gpu-blackwell.yml` (USB + staged) | Manual user-facing overlay for the broken image — no longer useful |

## Session 2 — Files that stay even though they look auto-generated

| File | Why kept |
|---|---|
| `docker-compose.blackwell-tts.yml` (staged only — not on USB) | Auto-regenerated by `08-up-stack.sh` on every install run. Currently pins the CPU image (Blackwell fallback). Removing it doesn't help — the script re-creates it. Leaving it makes the current state obvious to anyone inspecting the repo. |

## Session 2 — Disk reclamation accomplished

| Action | Reclaimed |
|---|---|
| `docker rmi ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4` (the original bundled GPU image, useless on Blackwell) | ~27 GB |
| `docker rmi kokoro-fastapi-blackwell:nightly` (the failed custom rebuild) | ~45 GB |
| `sudo apt clean` + `apt autoremove --purge` | ~3 GB |
| `rm ~/Downloads/google-chrome-stable_current_amd64.deb` + browser caches | ~280 MB |

**Going from 8.9 GB free → 46+ GB free.** Important: the bundled tarball at `docker-images/amd64/ghcr.io-remsky-kokoro-fastapi-gpu-v0.2.4.tar.gz` is still on the USB (used by non-Blackwell attendees). With the new Session 2 Step 4 skip, Blackwell hosts no longer pay the disk cost of loading it.

## Session 2 — New outstanding issues for the other-machine agent

| Issue | Severity | Notes |
|---|---|---|
| TTSManager voice-id fix is in source + staged + USB but **the running frontend container needs a rebuild** (`docker compose build frontend` + `up -d --force-recreate frontend`) before the fix takes effect in the browser. A fresh `./install.sh` does this automatically. | Low | Mention to attendees if they hit "no audio" after an in-place patch. |
| Browser cache needs hard-refresh (Ctrl+Shift+R) after frontend rebuild — Vite uses content-hashed filenames so the bundle name *should* change with each rebuild, but if the source didn't change between rebuilds the hash stays the same and the browser keeps the old version. | Low | First-time test: hard-refresh once. |
| The other agent's `08-up-stack.sh` rewrite is more complex than Session 1's version (4 overlay variables, service array). Both versions work; the other-agent version is the live one. Worth a code review before workshop day. | Low | Read `scripts/install/08-up-stack.sh` end-to-end if you're going to modify it. |

## Session 4 — Upstream whisper.cpp regression (STT exit 132)

**Discovered during a clean baseline test after the kit rebuild.**

### Symptom
After `setup.sh` + `install.sh` completed, `docker compose up` failed with:
```
dependency failed to start: container nodeava-workshop-stt-1 is unhealthy
```
The stt container went into a restart loop, exiting with code 132 (SIGILL) within 0.2 s of start. install.sh step 8 reported "Stack is up" (because of the `\|\| true` softening) but the dashboard couldn't reach STT.

### Root cause — NOT our scripts
`stt-service/Dockerfile` uses `FROM ghcr.io/ggml-org/whisper.cpp:main-vulkan`. **That's a moving tag** — it points to the latest build of upstream whisper.cpp's main branch. install.sh step 7 runs `docker compose build`, which re-pulls that tag and rebuilds, producing `nodeava-workshop-stt:latest`.

Between the kit build date (`2026-05-19`) and the test date (`2026-05-22`), upstream whisper.cpp pushed a regression: `whisper-server` from the current `:main-vulkan` crashes with exit 132 on startup when **either** (a) it tries to enumerate Vulkan devices on a Blackwell GPU, or (b) it runs with `--no-gpu` but with flash attention enabled (the default). Both modes crash. The OLDER image bundled on the USB (`workshop-mvp-spec-stt:latest`, built ~May 16) does NOT have this regression and starts cleanly using CPU (the entrypoint's default behavior).

This is an externally-introduced regression, not something the kit's scripts caused. But the kit's design — rebuild from a moving tag at install time — made the kit vulnerable to it.

### Diagnosis attempts that didn't work (recorded for the next agent)
1. Adding `USE_GPU=0` to the entrypoint (passes `--no-gpu`): container still crashed exit 132 because flash-attn is on by default.
2. Adding `--no-flash-attn` as well: container still crashed exit 132 in the new build. (The OLDER image with the same flag set doesn't crash — confirms upstream regression.)
3. Adding `NVIDIA_VISIBLE_DEVICES=void` env var: didn't actually hide the GPU because the `gpu-nvidia.yml` overlay's `deploy.resources.reservations.devices` reservation takes precedence over the env var.
4. Using `devices: []` in the Blackwell overlay to clear the GPU reservation: **silently no-ops** — docker-compose merge appends to lists, doesn't replace empty.
5. Using `deploy: !reset null` (Compose 2.24+ extension): correctly cleared the deploy section in the merged config (verified via `docker compose config`), and ggml_vulkan reported "No devices found" — but the new whisper-server binary STILL crashed exit 132 even with no Vulkan devices visible. The bug isn't only about device probing — flash-attention path itself is broken in the new build.

### What worked: use the bundled image, skip the rebuild
`workshop-mvp-spec-stt:latest` (bundled on USB) runs cleanly:
```
docker tag workshop-mvp-spec-stt:latest nodeava-workshop-stt:latest
docker compose up -d --no-build --force-recreate stt
```
Container becomes healthy in ~5 s. Whisper-server logs `whisper_backend_init_gpu: no GPU found` and `whisper server listening at http://0.0.0.0:8080`. Pure CPU, but functional.

### Kit fix applied (Session 4)
`setup.sh` step 4 now retags the bundled images at the end of `docker load`:
- `workshop-mvp-spec-stt:latest` → `nodeava-workshop-stt:latest`
- `workshop-mvp-spec-frontend:latest` → `nodeava-workshop-frontend:latest`

Compose then finds the named images already loaded and skips rebuilding them. Step 7 still builds the orchestrator (which genuinely needs our wiki/state/configs COPY'd in), but stt now uses the bundled image. This is a workshop-day stability win even outside the regression case — `docker compose build stt` would pull megabytes of Vulkan deps that aren't needed if the image is already loaded.

### Things the entrypoint changes from Session 4 leave behind
`stt-service/entrypoint.sh` was patched to honor `USE_GPU=0` (passes `--no-gpu --no-flash-attn`). This patch is **harmless but currently inert**, because the retag means we use the bundled image (with the *older* entrypoint) instead of rebuilding. If a future kit pack rebuilds stt from upstream and the regression is fixed, the entrypoint patch becomes the safety net.

`08-up-stack.sh`'s Blackwell overlay was also updated to set `USE_GPU=0` and clear the deploy section on stt — also inert with the bundled image, also a safety net if the rebuild path is ever re-enabled.

### Recommended follow-ups for the other-machine agent (also: please push USB to GitHub)

1. **Pin the stt Dockerfile FROM to a digest** (`FROM ghcr.io/ggml-org/whisper.cpp:main-vulkan@sha256:...`) so future rebuilds are deterministic. Pick a known-good digest — start from the layers of `workshop-mvp-spec-stt:latest`.
2. **Same with frontend's `node:22-alpine` and `nginx:alpine` FROMs** — both are moving tags. Less likely to regress dramatically, but worth pinning for reproducibility.
3. **Add the Session 4 retag logic to your kit-build pipeline's testing** — a fresh-machine smoke test that runs `setup.sh` then verifies all 5 containers reach healthy.
4. **Push the USB tree to GitHub** so this version is canonical and inspectable. The Session 4 retag + entrypoint patches are on the USB and need to land in the repo before any future kit rebuild.

## Session 3 — Post-rebuild cleanup

After the other-agent rebuilt the kit (new commit `50a8a77`, build timestamp `2026-05-22T02:19:57Z`), the `kokoro-fastapi-cpu:v0.2.4` image was bundled directly into `docker-images/amd64/` — so Blackwell hosts no longer need internet for the fallback TTS image. With the WSL2 path now using `install-docker.sh` + `install-ollama.sh` natively (Session 1 issue 13), the Windows-side installers are no longer referenced by any script.

| Removed from USB | Size | Reason |
|---|---|---|
| `installers/DockerDesktop-Win.exe` | 618 MB | Unreferenced — Session 1 collapse to native-WSL2 Docker means this is never invoked |
| `installers/Ollama-Win.exe` | 2.0 GB | Same — Session 1 collapse to native-WSL2 Ollama |

**Total: ~2.6 GB freed on USB.** Confirmed by `grep -rln` against `setup.sh` and `scripts/` — neither file is referenced anywhere in the install path.

The Mac installers (`DockerDesktop-Mac-{AppleSilicon,Intel}.dmg`, `Ollama-Mac.zip`) and the Linux `install-{docker,ollama}.sh` bundled binaries are all still on the USB and still referenced by setup.sh — those stay.

## Session 5 — Lab pages: knobs + Lab 1 direct-Ollama + voice-id race fix

**Context:** the install flow is stable enough to ship. Pedagogical UX moved into the lab pages themselves so attendees experiment one piece at a time instead of staring at compose logs. Most user-facing change of any session.

### 5a — Lab 1 (Brain) re-routed to Ollama directly

`frontend/public/lab/01-llm.html` used to POST to `/api/llm/v1/chat/completions` → orchestrator → Ollama. That added the orchestrator's personality system prompt (~580 tokens), the agentic tool loop (when toggled on in state), and a tool-routing decision per turn — Lab 1's TTFT numbers therefore weren't "raw LLM" at all, which was the lab's stated pedagogical purpose. Lab 4 is where the orchestrator gets demoed.

**Fix:** new nginx route `location /api/ollama/ { proxy_pass http://host.docker.internal:11434/; ... }` that bypasses the orchestrator entirely. Lab 1 now POSTs to `/api/ollama/v1/chat/completions`. To make the route work, the `frontend` compose service needed `extra_hosts: ["host.docker.internal:host-gateway"]`. Ollama's OpenAI-compatible endpoint **requires `model` in the body** (the orchestrator was filling that in server-side from `state.brain`); Lab 1 now hardcodes `model: "qwen3:4b-instruct"` (with a comment explaining where to change it).

Bare-Ollama TTFT on Blackwell: 90-220 ms typical. Through-orchestrator was misleadingly 400 ms+ before plus whatever tool-loop overhead state.tools added.

A new `ollama` probe was added to `_shared.js`'s preflight so Lab 1 verifies the direct path works (`/api/ollama/v1/models`).

### 5b — TTSManager voice-id race (dashboard silently produced no audio)

Latent since Plan #7/8, surfaced only after Session 1's `/api/orch/` nginx route landed (before that the dashboard couldn't load at all so this code path was never reached). Two bugs in `frontend/src/tts/TTSManager.js`:

1. `_loadVoiceFromState()` (which translates the orchestrator's UI-side voice id like `"bella"` → Kokoro voice id `"af_bella"` via `/v1/catalog`'s `kokoro_voice` field) was fire-and-forget from the constructor. First synthesis raced the catalog fetch and POSTed to Kokoro with `voice: "bella"` — Kokoro returned **HTTP 400 "Voice 'bella' not found"** and the dashboard silently produced no audio.
2. `setVoice(voiceName)` did `this._voice = voiceName` with no catalog mapping at all. Any caller passing a UI id (the ControlsPanel does) bypassed the mapping.

**Fix:**
- Constructor captures the load as `this._voiceReady` promise.
- `_processNext()` awaits `_voiceReady` before the first utterance.
- `setVoice()` rewritten: if input matches `^[a-z]{2}_` it's already a kokoro id, use directly; else async-resolve via `/api/orch/v1/catalog`'s `kokoro_voice` field.

Diagnosed via TTS container logs (`Voice 'bella' not found. Available voices: af_alloy, ..., af_bella, ...` + `HTTP 400 Bad Request`). Stack is end-to-end functional after this fix.

### 5c — Lab pages: experiment knobs (the big UX pass)

Added a consistent `<details class="controls">` "⚙ Experiment knobs" fold-out to every lab so attendees can twist real settings. Pattern: preset prompt chips at top → controls collapsed by default → main Run + output below.

| Lab | New controls |
|---|---|
| **1 · Brain** | Preset prompts (default / terse / creative / explain like I'm 5 / trivia). **Model dropdown** (live from `/api/ollama/v1/models` — qwen3 + smollm2, plus anything else `ollama pull`-ed). **Temperature / top-p** sliders with live value display. **Max tokens**. **System prompt** textarea (empty default — try "You are a grumpy pirate."). Stream toggle (kept). |
| **2 · Ears** | **Language hint** dropdown (auto / en / es / fr / de / it / ja / zh). **Sampling temperature** slider (passed as `temperature` form field). **Translate-to-English** checkbox (switches endpoint to `/v1/audio/translations`). Recent-runs history (last 5 with audio length / decode / RTF / transcript). |
| **3 · Voice** | Preset text chips (tiny / medium / long-form / staccato). **Voice A + Voice B** dropdowns. **Speed** slider (0.5-2.0). **A/B compare** button — synthesizes the same phrase in both voices and plays them back-to-back. |
| **4 · Nervous System** | **Brain dropdown** alongside the existing personality dropdown — swaps via `/v1/swap kind=brain`. Preset question chips (default / deep / how-to / opinionated). |
| **5 · Hands** | **Max rounds** slider (1-8). **Force-tool checkbox** — prepends "Use browser.search or wiki.search to research this before answering. Question: …" to the user message. Workaround for the known qwen3:4b tool-routing reluctance on confident-feeling questions ("who is the current US president?" — see the small-model trigger-map limitations in `configs/catalog.yml`'s `default` personality). |
| **6 · Whole body** | **Brain + Voice dropdowns** that swap inline via `/v1/swap`. **Text-input mode toggle** — skip mic + STT, type a message instead. Full pipeline becomes exercisable without a microphone (useful for SSH-attached attendees or any noisy environment). |

Shared additions:
- `_shared.css` — new `.controls`, `.controls-grid`, `.slider-row`, `.check-row`, `.compare-grid`, `.history` widget styles. Also **promoted `.preset` out of Lab 5's inline `<style>` block into `_shared.css`** so chips in Labs 1, 3, 4 render as clickable dashed-border pills (they were rendering as plain text before — a real bug, not just cosmetic).
- `_shared.js` — new helpers: `listOllamaModels()` (returns `[{name}]` for the dropdown), `fillSelect(el, options)`, `bindSlider(sliderEl, valEl, fmt)` for the live-value display pattern.

### 5d — Lab 1 had a missing Run button (intra-session regression)

While restructuring Lab 1's input area in 5c, I removed the action row containing `<button id="go">Run</button>` and `<button id="clear">` and forgot to put them back. JS handlers still expected them so clicks errored silently. Restored. Caught immediately, but worth flagging because the **same restructuring pattern in Labs 2-6 did NOT lose their buttons** — only Lab 1 was affected.

### 5e — STT exit 132 (final whitewater) — same upstream regression as Session 4

The `:main-vulkan` upstream regression first noted in Session 4 deepened. Even with `--no-gpu --no-flash-attn` flags passed to `whisper-server`, the new build still exits 132 within 0.2 s of startup if Vulkan device probing finds any GPU. The Blackwell `deploy: !reset null` overlay (to truly clear GPU passthrough) helped — `ggml_vulkan: No devices found.` then no crash — but the rebuild path is fragile because the upstream tag keeps moving.

**Permanent workaround (already from Session 4): retag the bundled `workshop-mvp-spec-stt:latest` as `nodeava-workshop-stt:latest` at setup time and don't rebuild stt at install time.** That's what's in `setup.sh` step 4 now. Verified to work this session.

Entrypoint patch from this session: `stt-service/entrypoint.sh` honors `USE_GPU=0` (passes `--no-gpu --no-flash-attn` to whisper-server). Inert with the bundled image but a safety net if a future kit pack rebuilds stt from a fixed upstream.

`08-up-stack.sh` Blackwell overlay now uses `deploy: !reset null` (Compose 2.24+ extension) to clear stt's GPU reservation. Was previously `devices: []` which doesn't actually replace the list (compose merge appends instead). Same trick applied to tts for symmetry.

## Session 5 — Files modified beyond Sessions 1-4

| File | What changed |
|---|---|
| `source/nodeava-workshop/docker-compose.yml` | `frontend` service: added `extra_hosts: ["host.docker.internal:host-gateway"]` so the new `/api/ollama/` nginx route can resolve the host's Ollama. |
| `source/nodeava-workshop/frontend/nginx.conf` | New `location /api/ollama/` block → `http://host.docker.internal:11434/`. Bypasses orchestrator entirely. Used by Lab 1 only. |
| `source/nodeava-workshop/frontend/public/lab/_shared.css` | Added: `.controls`/`.controls-body`, `.controls-grid`, `.slider-row`, `.check-row`, `.compare-grid`, `.history`, **`.preset`** (promoted from Lab 5 inline). |
| `source/nodeava-workshop/frontend/public/lab/_shared.js` | Added: `listOllamaModels()`, `fillSelect()`, `bindSlider()`. New `ollama` preflight probe. |
| `source/nodeava-workshop/frontend/public/lab/01-llm.html` | Routes to `/api/ollama/`; passes `model` in body; preset chips; experiment knobs panel; Run/Clear restored after the intra-session regression. |
| `source/nodeava-workshop/frontend/public/lab/02-stt.html` | Language hint + sampling-temp + translate-to-English + run-history. |
| `source/nodeava-workshop/frontend/public/lab/03-tts.html` | Speed slider + voice A/B compare. |
| `source/nodeava-workshop/frontend/public/lab/04-orchestrator.html` | Brain dropdown swap + preset prompts. |
| `source/nodeava-workshop/frontend/public/lab/05-tools.html` | Max-rounds slider + force-tool checkbox. Inline `.preset` CSS removed (moved to `_shared.css`). |
| `source/nodeava-workshop/frontend/public/lab/06-pipeline.html` | Brain + Voice dropdowns + text-input mode (extracted Stages 2+3 into `runLlmAndTts(transcript, tPipeStart, recDur)` so the typed-message path skips STT). |
| `source/nodeava-workshop/frontend/src/tts/TTSManager.js` | `_voiceReady` promise + first-utterance await; defensive `setVoice()` with kokoro-id regex. |
| `source/nodeava-workshop/scripts/install/08-up-stack.sh` | Blackwell overlay now uses `deploy: !reset null` instead of `devices: []` to actually clear GPU passthrough. Applies to both tts and stt. |
| `source/nodeava-workshop/stt-service/entrypoint.sh` | Honors `USE_GPU=0` env → passes `--no-gpu --no-flash-attn` to whisper-server. Safety net only — current flow uses the bundled image. |

## Session 5 — Pedagogy / workshop-day notes for the other-machine agent

- The pedagogical bet shifted: **install.sh stays the existing 9-step wizard** (no big phased-staging refactor). The labs themselves are where attendees learn, by twisting knobs. Discussed this twice; ended up here.
- Lab pages are **served by the frontend container** so they need it running before the labs are usable. With the Session 4 retag fix, frontend comes up cleanly from the bundled image — no rebuild on Blackwell, no risk of the upstream regression chain.
- The `.preset` chips silently rendered as plain text in Labs 1, 3, 4 for ~30 minutes after the knobs PR landed (caught only because user noticed). Likely worth adding a smoke check that loads each lab page and asserts certain CSS classes are styled — would have caught this.
- Lab 1's "raw LLM" vs Lab 4's "orchestrator" distinction is now real: they hit different endpoints. Numbers from Lab 1 are bare Ollama; numbers from Lab 4 include the personality prefill and agentic-loop overhead.

## Session 2 — How to retry the Blackwell GPU TTS rebuild correctly

The failed attempt produced a 45 GB image that crashed on startup. If you want to try again on a different machine:

1. **Don't** start from the deleted `docker/kokoro-blackwell/Dockerfile` recipe — it was incomplete.
2. Clone upstream Kokoro-FastAPI: `git clone --branch v0.2.4 https://github.com/remsky/Kokoro-FastAPI.git`
3. Edit the Dockerfile to swap the PyTorch base image. The default uses PyTorch <2.6 which has no sm_120 kernels. Try `nvidia/cuda:12.8.0-devel-ubuntu22.04` and `pip install torch==2.6.0+cu128 --index-url https://download.pytorch.org/whl/cu128` (or PyTorch nightly with `--index-url https://download.pytorch.org/whl/nightly/cu128`).
4. `docker build -t kokoro-fastapi-blackwell:nightly .` from the **full** repo dir (NOT just a subdir COPY — that's what broke the previous attempt; the Kokoro entrypoint references files like `download_model.py` at repo root).
5. Smoke test: `docker run --rm --gpus all -p 8880:8880 kokoro-fastapi-blackwell:nightly`. Should print `Loading TTS model and voice packs...` followed by Uvicorn ready, NOT `RuntimeError: Warmup failed: ...` or `python: can't open file`.
6. With the image present locally, `08-up-stack.sh` will auto-detect it on next `./install.sh` run and write the right `docker-compose.blackwell-tts.yml` overlay.
