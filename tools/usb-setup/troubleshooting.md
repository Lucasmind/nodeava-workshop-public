# Troubleshooting

## Common issues during USB-based install

### "permission denied: ./setup.sh"

The execute bit didn't survive the USB filesystem. Run:

```bash
chmod +x setup.sh
./setup.sh
```

Or invoke explicitly:

```bash
bash setup.sh
```

---

### macOS: "setup.sh cannot be opened because it is from an unidentified developer"

Right-click the script in Finder → **Open** → confirm. Then run from a terminal as
normal. Or clear the quarantine flag:

```bash
xattr -d com.apple.quarantine setup.sh
```

---

### Docker Desktop installed but `docker info` fails

Docker Desktop has to be **running** (the whale icon in the menubar / system tray).
On first launch you'll need to accept the EULA. The script can't auto-accept.

---

### Windows: "WSL is not installed"

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Reboot when prompted, then run setup.bat again.

---

### WSL2: "Docker isn't reachable"

Two things to check:

1. Docker Desktop is running **on Windows** (whale icon)
2. In Docker Desktop → Settings → Resources → WSL Integration, the **Ubuntu**
   distro (or whichever you use) has integration enabled. Tick the toggle, then
   restart WSL: `wsl --shutdown` from PowerShell, then re-open your WSL terminal.

---

### "Ollama daemon not responding on :11434"

The Ollama installer doesn't auto-start the daemon. Launch it once:

- **macOS**: Open **Ollama.app** from Applications. It lives in the menubar.
- **Linux**: `ollama serve &` (or `sudo systemctl start ollama` if it created a service)
- **Windows**: Look for the Ollama icon in the system tray; if missing, re-run the installer

Verify with:

```bash
curl http://localhost:11434/api/tags
```

You should get JSON listing your models.

---

### `docker load` fails with "no space left on device"

Docker stores images in `/var/lib/docker/` (Linux) or inside the Docker Desktop VM
(Mac/Win). The pre-built images plus a few base layers add up to ~8 GB.

- **Mac/Win**: Docker Desktop → Settings → Resources → Disk image size. Bump it.
- **Linux**: free up space in `/var/lib/docker/` or move the docker root to a
  bigger disk (`/etc/docker/daemon.json` with `"data-root": "/path"`).

---

### Port 3000 is already in use

Something else is on port 3000 (often a Node dev server). Two options:

```bash
# Use a different port for the frontend
FRONTEND_PORT=3030 ./install.sh
```

Then open `http://localhost:3030` instead.

Or find and stop the conflicting process:

```bash
# Linux / WSL2 / Mac
lsof -iTCP:3000 -sTCP:LISTEN
sudo kill <PID>
```

---

### "Avatar object Hips not found" / "setMeshoptDecoder must be called…"

The shipped 8-avatar gallery works out of the box. If you're adding **your own**
avatar GLB and seeing these errors, the file is missing TalkingHead's required
rig (eye bones, finger bones, etc.) or uses Meshopt compression without the
decoder.

Run the auto-fix script:

```bash
cd ~/nodeava-workshop
./tools/avatar-fix.sh path/to/your-avatar.glb
```

It handles Meshopt decompression + Armature wrapper injection + VRC viseme
renaming. It can't add missing eye bones — those require Blender retargeting.

---

### Models aren't loading / Ollama says "model not found"

The USB pre-loads `qwen3:4b-instruct` and `smollm2:360m` into your Ollama
models folder. Verify they're visible:

```bash
ollama list
```

If they're missing, check that the USB copy step ran:

```bash
ls ~/.ollama/models/manifests/registry.ollama.ai/library/
```

You should see `qwen3/` and `smollm2/` folders. If they're empty, manually:

```bash
cp -R /run/media/$USER/<USB>/ollama-models/manifests/* ~/.ollama/models/manifests/
cp /run/media/$USER/<USB>/ollama-models/blobs/* ~/.ollama/models/blobs/
ollama list   # should now show both
```

---

### Browser opens to localhost:3000 but page is blank

Open browser DevTools (F12 / Cmd-Option-I) → Console tab.

- **Lots of red errors** mentioning fetch failures → the orchestrator container
  isn't running. Check: `docker ps | grep nodeava-orch`. If missing,
  `docker compose up -d orchestrator` from `~/nodeava-workshop/`.
- **"Cannot read properties of undefined (getWorldPosition)"** → the active avatar
  has a non-standard skeleton. Open the drawer → switch to "Ava (default)".
- **Page loads but the avatar is missing / blank** → graphics drivers issue.
  Try in a different browser (Chrome works best for WebGL).

---

### Microphone doesn't work

Browsers require the page be served over `https` or `localhost` for mic access
(both of which we satisfy). Check:

1. The browser prompted you to allow microphone access on first click → click Allow
2. Browser → Settings → Privacy and Security → Site Settings → Microphone → make
   sure `localhost:3000` (or 3030) isn't blocked

---

## Resetting and starting over

`install.sh` has built-in reset modes:

```bash
cd ~/nodeava-workshop

# Selective reset — pick what to wipe (containers / models / state)
./install.sh

# Wipe everything and start fresh
./install.sh --full-reset
```

---

## Asking for help

If you've checked the above and it still won't work, find the workshop
instructor — they have a printed runbook with backup paths. Don't burn time
in silence; the room moves fast.
