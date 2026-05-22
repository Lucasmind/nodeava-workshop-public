# Mac Tester Runbook — NodeAva Workshop Kit

You are the Apple Silicon test pilot. Two goals:

1. **Verify the workshop kit installs and runs cleanly on macOS** (Apple Silicon).
2. **Build arm64 Docker images** so we can include them on the workshop USB sticks for other Mac attendees.

Time budget: about **45–60 minutes total**. About 20 min of the install is unattended.

---

## What you need

- A Mac with **Apple Silicon** (M1 / M2 / M3 / M4). Intel Macs work too but we'd rather you on Apple Silicon since that's the harder case.
- **Docker Desktop** for Mac — install from <https://docker.com/products/docker-desktop>. Accept the EULA, let it run once.
- **Homebrew** (probably already there): `brew --version` should print something.
- **About 15 GB of free disk** for the stack + models.
- A working **internet connection** for the first run (this will be cached for USB later).

---

## Part 1 — Install + verify the kit (~25 min)

### 1. Clone

```bash
git clone https://github.com/Lucasmind/nodeava-workshop-public.git ~/nodeava-workshop
cd ~/nodeava-workshop
```

### 2. Run the installer wizard

```bash
./install.sh
```

The wizard will walk you through 9 steps interactively:

1. Welcome banner
2. **Preflight** — platform / GPU / Docker / disk / network / ports. Should detect "macOS" automatically.
3. Inventory (first run: pick **Reset** since it's a fresh install)
4. LLM backend — **press Enter for the default (Ollama)**
5. Ollama install — script handles `brew install ollama` if missing
6. Pull models — downloads `qwen3:4b-instruct` (2.5 GB) and `smollm2:360m` (725 MB). This is the slow step on first run.
7. Build orchestrator container
8. Bring up the stack (`docker compose up -d orchestrator tts stt searxng frontend`)
9. Smoke verify — three probes ending in `✓ All smoke checks passed.`

Expected wall time on first run: **15–20 minutes** (models are the bottleneck).

### 3. Open the browser

```
http://localhost:3000
```

On first load you should see a **7-step spotlight walkthrough** auto-start. Take the tour.

### 4. Verify the main features (~5 min)

| Test | Expected |
|---|---|
| Type "Hello" in the chat box and press Send | Ava responds verbally + the FlowDiagram in the drawer lights up |
| Speak via the 🎤 Mic button (hold mic icon, talk, click again to stop) | Same — STT → LLM → TTS → avatar |
| Open the drawer (`]` key or top-right button) | See Brain / Voice / Avatar / Personality selectors |
| Click the **avatar selector** | 8 options (Ava default + Riley + Mike + Marcus + Devon + Alex + Maya + Aria) |
| Swap to "Mike (photoreal M, MIT)" | Avatar reloads as a male photoreal character |
| Click **Benchmark** button (in BENCHMARK section) | 3 rows appear after ~30s with TTFT / Tok/s / E2E numbers |
| Ask "What ports does NodeAva use?" | Avatar says "Let me look that up" (or sibling), then answers with wiki data |
| Toggle web search ON, ask "What's the latest news about SpaceX?" | Avatar says "Let me search the web for that", calls browser tool, answers |
| Click "✎ Edit personality" | Modal opens with the active personality's prompt prefilled |

If any of these fail, capture a screenshot + the contents of `docker logs nodeava-orch` and send them my way — **don't try to fix it yourself**. We'd rather have a clean failure report than a debugged-but-untraceable one.

### 5. Report back what worked

Quick summary to me:
- Which tests passed / failed
- Approximate timings (first-token latency, first-audio latency)
- Anything that surprised you (UI weirdness, terminal output that looked off)
- Your Mac specs (model + RAM) for context

---

## Part 2 — Build arm64 Docker images for the workshop USB (~15 min)

Other Apple Silicon attendees will want pre-built arm64 images on the USB stick so they don't need to wait for Docker pulls on workshop wifi. You're the build machine for those.

### 1. Make sure buildx is enabled

```bash
docker buildx ls
```

You should see at least one builder. If `default` is missing the `linux/arm64` platform, create a buildx builder:

```bash
docker buildx create --name nodeava-builder --use
docker buildx inspect --bootstrap
```

### 2. Stage a build output directory

```bash
mkdir -p ~/nodeava-arm64-images
cd ~/nodeava-workshop
```

### 3. Build + save the three local images for arm64

We need arm64 versions of the three images we BUILD locally (the others are pulled from upstream registries which already publish arm64 manifests).

```bash
# nodeava-orch (FastAPI + wiki-compiler)
docker buildx build \
  --platform linux/arm64 \
  --tag nodeava-orch:latest-arm64 \
  --load \
  ./services/orchestrator
docker save -o ~/nodeava-arm64-images/nodeava-orch.tar nodeava-orch:latest-arm64

# frontend (nginx + built Vite assets)
docker buildx build \
  --platform linux/arm64 \
  --tag workshop-mvp-spec-frontend:latest-arm64 \
  --load \
  ./frontend
docker save -o ~/nodeava-arm64-images/frontend.tar workshop-mvp-spec-frontend:latest-arm64

# stt (Vulkan whisper.cpp — this one is finicky cross-arch)
docker buildx build \
  --platform linux/arm64 \
  --tag workshop-mvp-spec-stt:latest-arm64 \
  --load \
  -f stt-service/Dockerfile \
  ./stt-service
docker save -o ~/nodeava-arm64-images/stt.tar workshop-mvp-spec-stt:latest-arm64
```

**If the stt build fails** (whisper.cpp + Vulkan on arm64 is the most likely sore spot): skip it. Apple Silicon Macs run Whisper **natively via Metal** anyway — `scripts/start-mac.sh` handles this. We may not need arm64 STT in Docker at all. Just note the failure in your report.

### 4. Pull-and-save the upstream images for arm64

These already have arm64 manifests on Docker Hub / GHCR. Just pull-with-platform + save:

```bash
# Kokoro TTS — note: on Mac you wouldn't actually use this (Mac uses native MPS Kokoro
# via scripts/start-mac.sh). But Linux/WSL2 attendees with arm64 (rare but possible)
# would. So bundle it anyway.
docker pull --platform linux/arm64 ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4 || \
  docker pull --platform linux/arm64 ghcr.io/remsky/kokoro-fastapi-cpu:latest
docker save -o ~/nodeava-arm64-images/kokoro-tts.tar ghcr.io/remsky/kokoro-fastapi-gpu:v0.2.4 2>/dev/null || \
  docker save -o ~/nodeava-arm64-images/kokoro-tts.tar ghcr.io/remsky/kokoro-fastapi-cpu:latest

# SearXNG
docker pull --platform linux/arm64 searxng/searxng:latest
docker save -o ~/nodeava-arm64-images/searxng.tar searxng/searxng:latest
```

### 5. Verify + tarball

```bash
ls -lh ~/nodeava-arm64-images/
```

You should see 4–5 `.tar` files, total ~6 GB.

Tarball them up:

```bash
cd ~
tar czf nodeava-arm64-images-$(date +%Y%m%d).tar.gz nodeava-arm64-images/
ls -lh nodeava-arm64-images-*.tar.gz
```

### 6. Send the tarball back to me

Pick whatever works for you:

- **WeTransfer / Dropbox / Drive** — easiest, send me the link
- **iCloud Drive** with a share link
- **`rsync` to my server** (if you've got SSH access, ping me and I'll send credentials)
- **scp / ssh into my machine** (same)

Whatever channel, the receiving end is: a 6 GB tarball that goes into `dist/usb-stage-arm64/docker-images/arm64/` on my build machine.

---

## Part 3 — Optional but useful

If you have spare time:

- **Test the native Mac path**: run `bash scripts/setup-mac.sh` then `bash scripts/start-mac.sh`. This is the non-Docker path where Whisper + Kokoro run via Homebrew + native MPS GPU. Faster than Docker on Apple Silicon. Confirm the same 8-avatar gallery + benchmark + personality editor + tool fillers work via this path.
- **Try the avatar-fix script**: `tools/avatar-fix.sh path/to/some.glb` on a VRoid or random GLB you find. Report whether it produces a TalkingHead-loadable file.
- **Try the personality CLI**: `echo "You are a pirate. End every sentence with Arr!" > /tmp/pirate.txt && scripts/demos/personality-set.sh /tmp/pirate.txt`. Then chat with Ava and confirm the persona.

---

## What I'm specifically watching for

- **Anything that errors on macOS but works on Linux** — these are the cross-platform bugs we need to fix before Friday.
- **Permissions friction** — Gatekeeper on the bootstrap scripts, microphone permissions in the browser, Docker Desktop EULA hassles.
- **Path assumptions** — the install scripts use `$HOME/.ollama` but Mac Ollama puts models in `~/Library/Application Support/Ollama/`. If that's broken on macOS, tell me.

---

## Help / panic line

If you hit something that's clearly broken and not your fault, capture:

```bash
docker compose logs --tail=200 > /tmp/nodeava-logs.txt
docker ps -a > /tmp/nodeava-containers.txt
docker version > /tmp/docker-version.txt
ollama --version > /tmp/ollama-version.txt
uname -a > /tmp/system.txt
```

…and send all of those plus a screenshot. I'd rather have 5 minutes of diagnostics than 3 hours of you trying to figure it out.

Thanks for testing this — you're the proof that the Mac path actually works.
