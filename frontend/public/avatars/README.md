# Avatar Models

NodeAva ships with eight pre-rigged avatars in `configs/catalog.yml`.
Workshop attendees swap among them from the dashboard's avatar selector.

| File | Style | License | Notes |
|------|-------|---------|-------|
| `default-avatar.glb` | Photoreal F (RPM brunette) | CC BY-NC 4.0 | 4.6 MB · bundled in `met4citizen/TalkingHead` |
| `rpm-female.glb` | Photoreal F (RPM) | **MIT** | 9.9 MB · `readyplayerme/visage` upstream |
| `rpm-male.glb` | Photoreal M (RPM) | **MIT** | 11 MB · `readyplayerme/visage` upstream |
| `rpm-male-casual.glb` | Photoreal M, casual + glasses, dark-skinned | RPM developer use | 3.5 MB · sourced from `OrPerets/sql-chatbot` repo |
| `rpm-male-smart.glb` | Photoreal M, smart-casual polo + glasses | RPM developer use | 3.1 MB · sourced from `Kshitijm7/digital-persona` repo |
| `avatarsdk-male.glb` | Photoreal M, suit-ready | AvatarSDK NC | 12 MB · MetaPerson Creator, bundled in `met4citizen/TalkingHead` |
| `avaturn.glb` | Photoreal F (Avaturn) | Avaturn NC | 14 MB |
| `mpfb.glb` | MakeHuman base F | **CC0** | 36 MB · fully-CC0 baseline |

See `LICENSES.md` for per-file attribution.

**Gender mix:** 4 male + 4 female. **Style:** all photoreal except mpfb (MakeHuman base).

## Adding your own avatar

TalkingHead requires GLB files with **all** of these:

- **15 Oculus visemes** (`viseme_aa`, `viseme_PP`, `viseme_sil`, …) — minimum for lip sync
- **52 ARKit blendshapes** — facial expressions (`jawOpen`, `mouthSmileLeft`, `browInnerUp`, etc.)
- **Skeleton root named `Armature`** with full RPM/Mixamo-style humanoid rig including:
  - Hips, Spine, Spine1, Neck, Head
  - **LeftEye + RightEye** (TalkingHead's animation system dereferences these)
  - LeftShoulder/Arm/ForeArm/Hand + RightShoulder/Arm/ForeArm/Hand
  - 30 finger bones (`LeftHandThumb1` through `RightHandPinky3`)
  - LeftUpLeg/Leg/Foot + RightUpLeg/Leg/Foot

This is the canonical Ready Player Me / Avaturn / Mixamo skeleton. Cartoon
characters from game-asset packs typically lack the eye bones and finger
articulation, which makes them incompatible without Blender retargeting
(JSON-patching can't add new joints to skinned meshes).

## Post-2026 avatar landscape

- **Ready Player Me** was discontinued January 2026 (Netflix acquisition).
  RPM's own `readyplayerme/visage` GitHub repo is **MIT-licensed** and the
  `github-pages` branch hosts pre-built `male.glb` / `female.glb` /
  `halfBody.glb` with the full blendshape set. Source for `rpm-male.glb`
  and `rpm-female.glb`.
- **RPM tutorial repos on GitHub** — many developers committed pre-generated
  RPM avatars to public repos (sql-chatbot, digital-persona, etc.). Still
  downloadable from `raw.githubusercontent.com` even though RPM's own CDN
  is dead. These are under RPM's original developer-use terms.
- **Avaturn** (hub.avaturn.me) — free Basic tier, signup required. Pick T2 body type.
- **AvatarSDK / MetaPerson Creator** — photoreal selfie-to-avatar service. NC.
- **VRoid Studio** — free, anime style. Default exports have only 5 visemes;
  HANA-Tool post-processing in Unity adds the 52 ARKit shapes. The previous
  `vroid.glb` was pulled from the gallery (outfit-inappropriate for the
  conference); the auto-fix script still handles VRoid models if needed.
- **Microsoft Rocketbox** (115 MIT avatars) — convertable via Blender +
  Mixamo + met4citizen's `rename-rocketbox-shapekeys.py`. ~45 min per avatar.

## Auto-fix script

`tools/avatar-fix.sh` takes any near-compatible GLB or VRM and produces a
TalkingHead-ready GLB in ~3 seconds. Handles:

- Skeleton root rename / injects `Armature` wrapper
- Meshopt decompression (`EXT_meshopt_compression` → uncompressed)
- VRC-style viseme rename (`blendShape1.vrc_v_aa` → `viseme_aa`)
- Verifies ARKit + Oculus blendshape presence; warns if missing

What it CANNOT fix (requires Blender):

- Missing eye bones — TalkingHead dereferences `LeftEye` and `RightEye`
- Missing finger curl bones
- Missing morph target binary data (only names can be renamed, not synthesized)

Usage:
```bash
./tools/avatar-fix.sh path/to/input.glb [path/to/output.glb] [--synthesize-visemes]
```

## How NodeAva loads avatars

Place your `.glb` in this directory, then add an entry to `configs/catalog.yml`:

```yaml
avatars:
  - id: yourname
    label: "Your Display Name"
    glb_path: /avatars/your-file.glb
    body: F   # or M (TalkingHead idle-pose weighting)
```

Restart the orchestrator (`docker compose restart orchestrator`) and the
avatar appears in the dashboard's selector automatically.

## Verifying a GLB has the required shapes

Run from the repo root:

```bash
python3 - <<'PY' frontend/public/avatars/your-file.glb
import struct, json, sys
path = sys.argv[1]
with open(path, 'rb') as f:
    f.read(12)
    jl, _ = struct.unpack('<II', f.read(8))
    j = json.loads(f.read(jl).rstrip(b'\x00').rstrip())
names = set()
for m in j.get('meshes', []):
    for n in m.get('extras', {}).get('targetNames', []):
        names.add(n)
    for p in m.get('primitives', []):
        for n in p.get('extras', {}).get('targetNames', []):
            names.add(n)
ARKIT  = {'jawOpen','mouthSmileLeft','eyeBlinkLeft','browInnerUp','cheekPuff','noseSneerLeft','tongueOut'}
OCULUS = {'viseme_sil','viseme_PP','viseme_aa','viseme_O','viseme_U','viseme_I','viseme_E'}
node_names = set(n.get('name','') for n in j.get('nodes',[]))
needed_bones = {'Armature','Hips','Head','LeftEye','RightEye','LeftHandThumb1','LeftHandPinky3'}
print(f"total morphs: {len(names)}")
print(f"ARKit sample: {len(ARKIT & names)}/{len(ARKIT)}")
print(f"Oculus sample: {len(OCULUS & names)}/{len(OCULUS)}")
print(f"required bones present: {needed_bones - (needed_bones - node_names)}")
print(f"missing bones: {needed_bones - node_names}")
PY
```
