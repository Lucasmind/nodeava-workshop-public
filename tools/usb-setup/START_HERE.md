# NodeAva Workshop Kit — Start Here

Welcome. This USB contains everything you need to run a digital human on
your own laptop, fully offline. No internet, no cloud APIs.

## What you need

- A laptop running **macOS**, **Linux**, or **Windows 10/11 with WSL2**
- **8 GB of free RAM** (16 GB recommended)
- **8 GB of free disk space** for models + Docker images
- **A GPU** is strongly preferred (NVIDIA / AMD / Apple Silicon all work).
  CPU-only is technically possible but speech generation gets choppy.

## How long this takes

About **5–10 minutes** once you click through any installers.

## What we'll install

| Component | What it does |
|---|---|
| **Docker Desktop** | Runs the orchestrator, speech, and avatar services in containers |
| **Ollama** | Serves the local language model on your machine |
| **NodeAva kit** | The source repo, dropped into `~/nodeava-workshop/` |

If you already have Docker and Ollama, the script skips those steps.

---

## Step 1 — Plug in the USB stick

Open the USB drive in your file manager. You should see:

- `START_HERE.md`  ← this file
- `setup.sh` (Mac / Linux / WSL2)
- `setup.bat` (Windows native)
- `source/`
- `docker-images/`
- `ollama-models/`
- `whisper-models/`
- `installers/`
- `docs/troubleshooting.md`

## Step 2 — Run the bootstrap script

### macOS

1. Open **Terminal**
2. Drag the USB folder into the terminal window (or `cd` into it manually)
3. Run: `./setup.sh`
4. If you see "permission denied", first run: `chmod +x setup.sh` then re-run

### Linux (native Ubuntu / Fedora / etc.)

1. Open a terminal
2. `cd /run/media/$USER/<USB-name>` (path will vary by distro)
3. `./setup.sh`

### Windows + WSL2

**Recommended path:** double-click `setup.bat` in Windows Explorer.
That launcher checks WSL2 is installed, then runs `setup.sh` inside WSL2.

**Or directly from WSL2 if you prefer:**

1. Open a WSL2 terminal (e.g., Ubuntu)
2. `cd /mnt/d/` (replace `d` with your USB drive letter)
3. `./setup.sh`

---

## What the script does

The script walks you through 7 steps:

1. **Detect platform** — figures out what you're running on
2. **Docker** — checks Docker Desktop is installed and running; opens the
   installer from the USB if not
3. **Ollama** — same check + installer
4. **Load Docker images** — `docker load` the pre-built images from the
   USB (this is what saves the conference wifi)
5. **Stage Ollama models** — copies `qwen3:4b-instruct` and `smollm2:360m`
   into `~/.ollama/models/`
6. **Stage source tree** — copies the workshop kit to `~/nodeava-workshop/`
7. **Run the install wizard** — hands off to `./install.sh`, the
   9-step installer that brings up the stack and runs smoke verification

When it's done, open a browser:

> **<http://localhost:3000>**

A walkthrough overlay auto-starts on the first visit. Take the tour.

---

## If something goes wrong

See `docs/troubleshooting.md`. The common issues:

- **Docker Desktop needs the EULA accepted** — first launch only
- **WSL2 needs a reboot** — Windows installer asks for this
- **Ollama menubar app on Mac** — must be running for `localhost:11434` to work
- **Port 3000 is taken** — set `FRONTEND_PORT=3030` before running `./install.sh`

If you get really stuck, find the instructor or check the printed sheet at
the front of the room for the slack/discord URL.

---

## Re-running

The script is **idempotent** — running it twice in a row produces the
same end state. If `~/nodeava-workshop/` already exists, you'll be asked
whether to overwrite.

Want to wipe everything and start fresh? In `~/nodeava-workshop/`:

```bash
./install.sh --full-reset
```

That asks for confirmation, then resets containers + Ollama models + state.

---

## After the workshop

The kit is yours. You can:

- Take it home and keep tinkering
- Swap models in `configs/catalog.yml` and add your own avatars to `frontend/public/avatars/`
- Use `scripts/demos/personality-set.sh` to give Ava your own personality from the command line
- Read `docs/architecture-notes.md` on the USB for the technical map

Have fun.
