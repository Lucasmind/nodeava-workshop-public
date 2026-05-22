# Cloning a voice for NodeAva

NodeAva uses [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI) for
text-to-speech. Voices are `.pt` tensor files (PyTorch state dicts holding
the conditioning embeddings the synthesizer uses to shape speech). Cloning a
voice means producing one of those tensors from a reference audio clip.

## What you need

- **A reference audio sample.** 5–10 seconds of clean, single-speaker speech.
  No music, no background noise, no clipping. WAV or FLAC, mono, 24 kHz.
- **A machine with a GPU.** Kokoro's voice-cloning script runs on CPU but
  takes 10–20× longer than a CUDA / Metal / ROCm GPU.
- **Disk space.** ~5 GB for the Kokoro base model + a few hundred KB per
  cloned voice.

## Step-by-step

### 1. Record a reference clip

Use Audacity or any recorder. Speak naturally for ~8 seconds. Avoid breaths
at the start and end. Save as `myvoice.wav` (mono, 24000 Hz, 16-bit PCM).

Quick check from a terminal:

```bash
ffprobe -hide_banner myvoice.wav 2>&1 | grep -E 'Duration|Stream'
```

You want something like `Duration: 00:00:08.50`, `Stream #0:0: Audio: pcm_s16le, 24000 Hz, mono`.

### 2. Run Kokoro's voice-clone script

The script lives in the upstream Kokoro repository (not bundled here).
Clone it once:

```bash
git clone https://github.com/hexgrad/kokoro.git ~/.nodeava/kokoro-tools
cd ~/.nodeava/kokoro-tools
pip install -r requirements.txt
```

Then clone:

```bash
python scripts/clone_voice.py \
  --input  /path/to/myvoice.wav \
  --output /path/to/myvoice.pt \
  --device cuda   # or mps for Apple Silicon, cpu as a last resort
```

This produces a `.pt` file (~200 KB).

### 3. Drop the voice into NodeAva's Kokoro container

NodeAva's Kokoro-FastAPI container mounts a voices directory. Find it:

```bash
docker inspect nodeava-tts | python3 -c "
import json, sys
m = json.load(sys.stdin)[0]['Mounts']
for x in m:
    if 'voices' in x.get('Destination', ''):
        print(x['Source'], '->', x['Destination'])
"
```

Copy your file to the source path:

```bash
cp myvoice.pt /path/from/inspect/myvoice.pt
docker restart nodeava-tts
```

### 4. Register the voice in NodeAva's catalog

Edit `configs/catalog.yml`. Add an entry under `voices:`:

```yaml
voices:
  # ...existing entries...
  - id: myvoice
    label: "My Cloned Voice"
    kokoro_voice: myvoice    # matches the filename without .pt
```

Restart the orchestrator so it re-reads the catalog:

```bash
docker restart nodeava-orch
```

### 5. Verify

```bash
curl -s http://localhost:8082/v1/catalog | python3 -c "
import json, sys
print([v['id'] for v in json.load(sys.stdin)['voices']])
"
```

You should see `myvoice` in the list. Open the dashboard, open the drawer,
and your voice appears in the Voice selector. Click it; the next thing Ava
says will use it.

## Troubleshooting

- **"Voice not found" from Kokoro.** The filename inside the container must
  match `kokoro_voice` exactly (no `.pt` suffix). The container path is
  typically `/app/voices/<name>.pt`.
- **Robotic / mechanical output.** Reference clip was too short, too noisy,
  or had multiple speakers. Re-record with a single clean sample.
- **Mouth doesn't match.** Word timestamps depend on the language model, not
  the voice; verify Kokoro's `language` is set correctly.

## A note on practicality for workshops

Cloning a voice is a 5-minute task once you've done it once. For a workshop
context, attendees usually find it more fun to **pick** a voice from the
preset gallery (Bella, Nova, Fenrir, Emma, George) than to fight a microphone
during a 3-hour session. Keep this doc as a take-home — try it the evening
after the workshop.
