# NodeAva Workshop — Run of Show

**Length:** 3 hours
**Format:** Hands-on. Attendees install on their own laptop, then we explore each component layer-by-layer using the labs at `localhost:3000/lab/`.

---

## Pre-workshop checklist (the night before)

- [ ] Every attendee's USB key built from latest `pack-usb.sh` (or duplicated from the master Workshop key)
- [ ] USB contains `kokoro-blackwell.tar.gz` only if any attendee has RTX 50-series; otherwise that 13 GB is dead weight
- [ ] Print one A5 cheat sheet per attendee with the lab URLs and shell-fallback commands
- [ ] Spare USB keys for the inevitable "mine doesn't mount" — at least 2
- [ ] Set up a clearly-visible projector terminal showing `htop` + `nvidia-smi --watch` on the instructor laptop so the room can see GPU activity during demos
- [ ] Confirm conference wifi is unblocked for `download.docker.com` and `ollama.com` (the offline path works without it, but online is faster)
- [ ] `./install.sh` and every lab page tested end-to-end on the instructor laptop, fresh boot

---

## Time map

| Time    | Segment                                | Slide(s) | Lab          |
|---------|----------------------------------------|---------|--------------|
| 0:00    | Welcome + framing                      | 1–3     | —            |
| 0:10    | Component map (the anatomy)            | 4       | —            |
| 0:15    | Each organ (perception → embodiment)   | 5–10    | —            |
| 0:30    | **Plug in USB & start `setup.sh`**     | 11      | (background) |
| 0:35    | Environment check + while installer runs: tour-of-the-room talk | 12 | — |
| 0:55    | **Lab 1 — The Brain (LLM)**            | 13      | `lab/01`     |
| 1:15    | **Lab 2 — The Ears (STT)**             | 15–16   | `lab/02`     |
| 1:30    | ☕ Break                                |         |              |
| 1:40    | **Lab 3 — The Voice (TTS)**            | 14      | `lab/03`     |
| 1:55    | **Lab 4 — The Nervous System (Orchestrator + personality)** | 24–25 | `lab/04` |
| 2:15    | **Lab 5 — The Hands (Tools)**          | 28–30   | `lab/05`     |
| 2:40    | **Lab 6 — The Whole Body (Pipeline)**  | 19–23   | `lab/06`     |
| 2:55    | Wrap-up, take-home, Q&A                | 35–38   | —            |

---

## Segment 1 — Welcome and framing (0:00–0:10)

**Slides 1–3.**
Open with the goal: *by the end of this workshop you will have a running digital human on your own laptop, and you'll know what every layer is doing.* Frame the workshop as a guided tour, not a polished vendor demo.

The deliberate distinction: a digital human is **not** an LLM with a face. It's a loop — perception → cognition → expression → embodiment — timed tightly enough to feel like presence. The avatar is the last 10%; the timing is the other 90%.

**Don't:** play a recorded demo here. Hold the live reveal for Lab 6.

---

## Segment 2 — The component map (0:10–0:15)

**Slide 4.**
Walk the diagram. Map every component to a body part: ear/perception, brain/cognition, memory/knowledge, mouth/voice, face/embodiment, nerve/timing. *Then* say: "Now that we understand the organism, we are going to test the organs one at a time."

This is your re-orientation slide for the next 2 hours.

---

## Segment 3 — Component deep-dives (0:15–0:30)

**Slides 5–10 — one slide per organ.** ~2 min each.

Don't go deep on any one thing here; this is just naming and locating. The labs are where the depth happens.

The one bit of depth to plant: **streaming**. The labs will keep coming back to it. Drop the seed: "Modern AI services emit tokens one at a time. The art is connecting them downstream — chunk by sentence, hand to TTS, hand to lip sync — before the user notices the wait."

---

## Segment 4 — Start the install (0:30–0:35)

**Slide 11.**
*Everyone plug in your USB now.* Walk the room.

```bash
# Mac/Linux
cd /Volumes/Workshop    # or /media/$USER/Workshop on Linux
./setup.sh

# Windows
# Double-click setup.bat (it hands off to WSL2)
```

While installs run, keep talking. The runtime is ~5–10 min on a fast laptop; up to 20 min on a slow one. Build in 20 min of talk-time for the worst case.

**Fallback if the USB won't mount or setup fails:** point them at `https://github.com/Lucasmind/nodeava-workshop-public` and `git clone`.

---

## Segment 5 — While the installer runs (0:35–0:55)

**Slide 12** (environment check) — quickly walk through the preflight checks the installer runs. *This is where we catch problems before they hit during the labs.*

Then **stretch slide 11's intro** into a tour-of-the-room talk:
- Why we run Ollama on the host, not in Docker — direct GPU access, native binaries, mature
- Why we run Whisper and Kokoro in Docker — easier to manage CUDA dependencies per service
- Why we run nginx as a frontend even though Vite is right there — single origin, no CORS in attendee browsers, prod-shaped
- Why we *don't* run llama.cpp anymore — Ollama subsumed it as a model server

Goal here: kill the dead time, give the install something to land into.

By 0:55, everyone should have `localhost:3000` rendering. If not, peel off the slower laptops with a co-runner; keep the room moving.

---

## Segment 6 — Lab 1: The Brain (0:55–1:15)

**Slide 13.** Lab page: **`http://localhost:3000/lab/01-llm.html`**

The flow:
1. Open the lab page. Type a short prompt. Click Run.
2. Watch tokens stream. Read the chips: TTFT, total, tok/s.
3. Run the same prompt twice. Why is the second run faster? *(Ollama keeps the model loaded in VRAM after the first call — this is "residency". The dashboard shows it as the GPU/SPLIT/CPU chip.)*
4. Toggle stream off. Run again. Notice that you wait the full total time before any text appears. *This is why streaming matters — perceived latency vs total latency are different problems.*

**Teach moment:** "The model is 4 billion parameters. On Ampere+ NVIDIA hardware that fits in ~3 GB of VRAM at int4 quantization. Without the GPU, this would take 10–30× longer."

**Common surprise:** a 4B model is good enough for the demo but it stumbles on tool use; we'll see that in Lab 5.

---

## Segment 7 — Lab 2: The Ears (1:15–1:30)

**Slides 15–16.** Lab page: **`http://localhost:3000/lab/02-stt.html`**

The flow:
1. Click Record. Say one sentence. Click Stop.
2. Read the chips: audio length vs decode time → RTF (real-time factor).
3. Try a longer recording — RTF stays roughly constant, not linear. *The model amortizes setup cost across longer audio.*
4. Mute your mic, try recording silence. Whisper returns an empty (or hallucinated) transcript. *This is why endpointing — detecting silence to know when the user is done — is a separate problem from transcription.*

**Teach moment:** the `base.en` Whisper variant is 74 MB. The full-size English model is 1.5 GB. The base model trades accuracy for speed; in our pipeline, accuracy matters less than RTF because we can ask the user to repeat, but we cannot ask them to wait.

---

## Break (1:30–1:40)

Coffee. Bathroom. Keep the projector showing `nvidia-smi --watch`.

---

## Segment 8 — Lab 3: The Voice (1:40–1:55)

**Slide 14.** Lab page: **`http://localhost:3000/lab/03-tts.html`**

The flow:
1. Type a sentence. Click Speak.
2. Read the chips: first-audio latency, RTF, word count.
3. Watch the word boxes light up in sync with playback. *This is where lip sync starts.*
4. Try a long paragraph. RTF stays under 1. *That's the budget we have for chunking into sentences and starting playback before the full paragraph is synthesized.*
5. Switch voices. Same model weights, same engine; only the voice embedding changes.

**Teach moment:** Kokoro is 82 million parameters — smaller than most LLM token embeddings. The voice is encoded as a separate small tensor file (a "voice pack"). Custom voices are a few minutes of audio + a small training run; we link the docs in the take-home.

If anyone has a Blackwell laptop on the CPU TTS fallback, this is where the latency penalty shows up: 2–5 s/sentence instead of <0.5 s. Acknowledge it; explain the workaround in Slide 32.5.

---

## Segment 9 — Lab 4: The Nervous System (1:55–2:15)

**Slides 24–25.** Lab page: **`http://localhost:3000/lab/04-orchestrator.html`**

The flow:
1. Show the current state. Read the active personality's system prompt aloud.
2. Send a message — e.g., "Tell me one interesting fact about clocks." Watch the reply.
3. Swap personality (try `dry-historian`). Send the *same* message. Read the new reply.
4. Repeat with another personality (`improv-comic` or `tutor`).

**Teach moment — the centerpiece of the workshop:** the model is the same bytes. The temperature is the same. Only the system prompt changes. The personality *is* the program. This is what people miss when they treat LLMs as black boxes: the system prompt is where the most expressive engineering happens.

Tease Lab 5: "Now imagine the personality can also tell the model when to reach for a tool."

---

## Segment 10 — Lab 5: The Hands (2:15–2:40)

**Slides 28–30.** Lab page: **`http://localhost:3000/lab/05-tools.html`**

The flow:
1. Both toggles **off**. Ask "What is NodeAva?" — the model guesses based on training data (likely wrong; it's after the knowledge cutoff for some models).
2. Turn **wiki on**. Ask the same question. Watch the rounds panel: the model emits `wiki.search`, the orchestrator runs it, results come back, the model produces a grounded answer.
3. Turn wiki off, **web search on**. Ask a current-events question.
4. Both on. Ask something that needs both ("Compare NodeAva's design to UNEEQ"). Watch the model decide which tool to use first.

**Teach moment:** small models stumble on tool use. Watch for:
- Model emits a tool name with a typo (`wiki.serach` instead of `wiki.search`)
- Model calls the same tool 3× in a row with slightly different args
- Model gets the tool result back and ignores it

Slide 32.5 documents these failure modes — they're a feature of small instruction-tuned models, not a bug in the system. Bigger models (Sonnet, GPT-4, Claude Opus) handle this cleanly. *That's the trade: local-and-free vs cloud-and-correct.*

Watch the round counter when things go wrong — the loop will spin up to 8 rounds before giving up.

---

## Segment 11 — Lab 6: The Whole Body (2:40–2:55)

**Slides 19–23.** Lab page: **`http://localhost:3000/lab/06-pipeline.html`**

The flow:
1. Click Record. Ask a question out loud. Click Stop.
2. Watch the 4 stage chips light up in sequence: STT → LLM → TTS → total.
3. Listen to the reply.

**Teach moment — the latency budget:**
- STT: ~200 ms
- LLM TTFT: ~500 ms
- LLM full reply: ~1500 ms
- TTS: ~600 ms
- **Total: ~2.5–3 s end-to-end**

That feels conversational. Above ~4 seconds it starts feeling like a walkie-talkie. Above ~7 seconds people start asking "is it broken?". The lab is naive — it waits for each stage to finish before starting the next. The real app (`localhost:3000`) overlaps them: LLM streams tokens, TTS starts on the first sentence boundary, audio plays while subsequent sentences synthesize. That's how the dashboard's Lab 6 → main-app jump feels real-time.

Finish with: "Now click `Take the full app for a spin →` and meet Ava."

---

## Segment 12 — Wrap-up (2:55–3:00)

**Slides 35–38.**
- What changes in production (slide 35)
- DIY vs managed (slide 36)
- The takeaway promise (slide 37): you walk away with a working digital human, the source, your own custom personality saved in `state/custom-personality.json`, and the knowledge to swap any layer.
- Final beat (slide 38).

Hand out the public-mirror URL. Thank them. Stay 15 minutes for the curious.

---

## Service control during the labs

Each lab only needs a subset of the stack. To bring services up piecewise (useful for the install demo):

```bash
# Lab 1 (LLM only — orchestrator + Ollama on host)
docker compose up -d --no-deps orchestrator

# Lab 2 (add STT)
docker compose up -d --no-deps stt

# Lab 3 (add TTS)
docker compose up -d --no-deps tts

# Lab 4+ (add frontend if not already up; --no-deps skips the depends_on healthcheck wait)
docker compose up -d --no-deps frontend

# Or just bring everything up:
./install.sh
```

`--no-deps` is critical: without it, `up frontend` will wait for `stt`/`tts` healthchecks, which is the wrong demo flow.

To restart a single service mid-workshop (e.g., when a personality save needs a reload):

```bash
docker compose restart orchestrator
```

---

## Cheat sheet for attendees (one page, printable)

```
NodeAva Workshop — quick reference

Dashboard:   http://localhost:3000/
Labs:        http://localhost:3000/lab/

Lab 1   Brain (LLM)              /lab/01-llm.html
Lab 2   Ears (STT)               /lab/02-stt.html
Lab 3   Voice (TTS)              /lab/03-tts.html
Lab 4   Nervous System (orch.)   /lab/04-orchestrator.html
Lab 5   Hands (tools)            /lab/05-tools.html
Lab 6   Whole body (pipeline)    /lab/06-pipeline.html

CLI tests (if web UI is being slow):
  bash scripts/demos/test-llm.sh --fixture
  bash scripts/demos/test-tts.sh --fixture
  bash scripts/demos/test-stt.sh --fixture
  bash scripts/demos/test-pipeline.sh

Reset everything:
  ./install.sh --full-reset

Uninstall:
  sudo /Volumes/Workshop/uninstall-docker-ollama.sh
```

---

## Failure-mode playbook

| Symptom                                       | What to do                                                           |
|-----------------------------------------------|----------------------------------------------------------------------|
| `localhost:3000` says "Dashboard offline"     | `docker compose ps` — likely `orchestrator` not up. `restart` it.    |
| Mic button does nothing                       | Browser blocked mic — click the URL-bar mic icon, allow, refresh.    |
| TTS audio cuts off mid-sentence               | First-play autoplay block — click the audio control's play button.   |
| Whisper returns empty transcripts             | Mic not capturing — check OS audio input device.                     |
| **STT container crash-loops, exit 132**       | **See "STT fallback" below — known upstream regression in `:main-vulkan`.** |
| Lab 5 tool call spins for 20+ sec             | Small-model tool failure — kill the request, ask a simpler question. |
| Blackwell laptop, TTS very slow               | Expected — CPU TTS fallback. ~2-5 s/sentence is normal.              |
| Multiple attendees on same wifi → DNS fails   | Use the offline path: `./setup.sh --offline`                         |
| Firefox: "WebGL2 restricted on this system"   | NVIDIA driver/userspace mismatch — open Chrome instead, or reload the NVIDIA module. Labs don't need WebGL2; main dashboard does. |

### STT fallback — known good image

`stt-service/Dockerfile` builds from `ghcr.io/ggml-org/whisper.cpp:main-vulkan` — a **moving tag**. Between the USB build date (2026-05-16) and now, upstream has shipped a regression where `whisper-server` exits 132 within 0.2s of startup whenever Vulkan probing finds any device. The bundled image on the USB pre-dates the regression and is the known-good copy.

The kit handles this automatically: `setup.sh` step 4 retags `workshop-mvp-spec-stt:latest` → `nodeava-workshop-stt:latest` so compose finds the named image already loaded and doesn't rebuild.

**If an attendee's stack still ends up with the broken upstream build** (e.g., someone re-ran `docker compose build stt` manually, or used a kit older than the Session 4 fix), pull the published known-good image:

```bash
# Authenticate once (token needs read:packages):
gh auth login -s read:packages    # if gh installed
# OR: create a classic PAT at github.com/settings/tokens with read:packages
gh auth token | docker login ghcr.io -u <github-username> --password-stdin

# Pull and retag:
docker pull ghcr.io/lucasmind/nodeava-workshop/whisper-stt:known-good
docker tag  ghcr.io/lucasmind/nodeava-workshop/whisper-stt:known-good \
            nodeava-workshop-stt:latest

# Force recreate with the known-good image:
docker compose up -d --no-build --force-recreate stt
docker compose logs stt | grep -E "listening|whisper_backend"
# Expect: "whisper server listening at http://0.0.0.0:8080"
```

The image is on the private `Lucasmind/nodeava-workshop` repo. Three tags point at the same image bytes (digest `sha256:de0f4ebc6d7381be74783d7c390afd068dc47aa0e68ed8b4f1a92df55d21053f`):

- `:known-good` — floating tag, always points at the latest known-good build
- `:known-good-2026-05-16` — date-stamped, immutable reference
- `:latest` — floating, in case anyone uses bare `:latest`

---

## Post-workshop

- [ ] Push the public-mirror update (squashed commit of today's branch)
- [ ] Collect contact emails for the take-home repo URL
- [ ] Capture the feedback form responses
- [ ] Write the post-mortem before bed: what worked, what was rushed, what to cut next time
