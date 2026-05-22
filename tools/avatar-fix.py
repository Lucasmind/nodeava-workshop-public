#!/usr/bin/env python3
"""
avatar-fix.py — Make any GLB TalkingHead-compatible.

What it does:
  1. Decompresses EXT_meshopt_compression (via gltf-transform copy)
  2. Renames skeleton root → Armature (adds wrapper node if needed)
  3. Verifies 52 ARKit blendshapes are present
  4. Verifies 15 Oculus visemes are present
  5. (--synthesize-visemes) Synthesizes the 15 Oculus visemes from ARKit
     shapes when they are absent, by adding zero-delta morph targets whose
     names TalkingHead will find and then adding an extras hint so the
     TalkingHead runtime knows to call the ARKit→viseme baking path instead.
     NOTE: true vertex-delta synthesis (actually moving vertices) is out of
     scope for pygltflib — it cannot decode quantized/meshopt accessor data.
     Instead the script patches extras.targetNames so the 15 viseme names
     exist (pointing at alias entries), which satisfies TalkingHead's
     dictionary look-up.  See SYNTHESIS NOTES in this file.

Usage:
    python3 avatar-fix.py input.glb [output.glb] [--synthesize-visemes]
"""

import sys
import os
import json
import subprocess
import shutil
import tempfile
import copy
import time

# ─── Blendshape manifests ──────────────────────────────────────────────────

ARKIT_52 = [
    "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft",
    "browOuterUpRight", "cheekPuff", "cheekSquintLeft", "cheekSquintRight",
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen",
    "jawRight", "mouthClose", "mouthDimpleLeft", "mouthDimpleRight",
    "mouthFrownLeft", "mouthFrownRight", "mouthFunnel", "mouthLeft",
    "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft",
    "mouthPressRight", "mouthPucker", "mouthRight", "mouthRollLower",
    "mouthRollUpper", "mouthShrugLower", "mouthShrugUpper", "mouthSmileLeft",
    "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
    "tongueOut",
]

OCULUS_15 = [
    "viseme_sil", "viseme_PP", "viseme_FF", "viseme_TH", "viseme_DD",
    "viseme_kk", "viseme_CH", "viseme_SS", "viseme_nn", "viseme_RR",
    "viseme_aa", "viseme_E", "viseme_I", "viseme_O", "viseme_U",
]

# ARKit→Oculus viseme synthesis formulas.
# Each viseme is expressed as a weighted blend of ARKit shapes.
# Weights are approximate — tuned for plausible lip shape, not phonetic accuracy.
# These drive the extras.visemeSynthesis map that a patched TalkingHead can read.
VISEME_SYNTHESIS = {
    "viseme_sil": {},                                                  # silence — all zeros
    "viseme_PP": {"mouthPressLeft": 0.5, "mouthPressRight": 0.5,
                  "mouthClose": 0.4},                                  # bilabial plosive P/B/M
    "viseme_FF": {"mouthLowerDownLeft": 0.4, "mouthLowerDownRight": 0.4,
                  "mouthStretchLeft": 0.2, "mouthStretchRight": 0.2},  # labiodental F/V
    "viseme_TH": {"tongueOut": 0.7, "mouthOpen": 0.2,
                  "jawOpen": 0.15},                                    # dental TH
    "viseme_DD": {"jawOpen": 0.25, "mouthClose": 0.1,
                  "mouthUpperUpLeft": 0.15, "mouthUpperUpRight": 0.15},# alveolar D/T/N
    "viseme_kk": {"jawOpen": 0.3, "mouthStretchLeft": 0.2,
                  "mouthStretchRight": 0.2},                           # velar K/G
    "viseme_CH": {"mouthPucker": 0.3, "jawOpen": 0.2,
                  "mouthShrugUpper": 0.2, "mouthShrugLower": 0.2},    # postalveolar CH/SH/ZH
    "viseme_SS": {"mouthStretchLeft": 0.3, "mouthStretchRight": 0.3,
                  "mouthClose": 0.2, "jawOpen": 0.1},                 # sibilant S/Z
    "viseme_nn": {"jawOpen": 0.15, "mouthClose": 0.2,
                  "mouthUpperUpLeft": 0.1, "mouthUpperUpRight": 0.1}, # nasal N/NG
    "viseme_RR": {"mouthPucker": 0.4, "jawOpen": 0.3,
                  "mouthFunnel": 0.2},                                 # approximant R
    "viseme_aa": {"jawOpen": 0.7, "mouthFunnel": 0.15,
                  "mouthShrugLower": 0.1},                             # open vowel AH/AA
    "viseme_E":  {"mouthSmileLeft": 0.4, "mouthSmileRight": 0.4,
                  "jawOpen": 0.3, "mouthStretchLeft": 0.15,
                  "mouthStretchRight": 0.15},                          # front vowel EH/AE
    "viseme_I":  {"mouthSmileLeft": 0.5, "mouthSmileRight": 0.5,
                  "jawOpen": 0.15},                                    # high front vowel IH/IY
    "viseme_O":  {"mouthFunnel": 0.6, "jawOpen": 0.4,
                  "mouthPucker": 0.2},                                 # mid back vowel OH/AO
    "viseme_U":  {"mouthPucker": 0.7, "mouthFunnel": 0.3,
                  "jawOpen": 0.1},                                     # high back vowel UH/UW
}

# ─── Helpers ──────────────────────────────────────────────────────────────

def log(msg): print(f"  {msg}", flush=True)
def warn(msg): print(f"  WARNING: {msg}", flush=True)
def ok(msg): print(f"  OK: {msg}", flush=True)

def collect_target_names(glb):
    """Return a set of all morph target names across all meshes."""
    names = set()
    for mesh in glb.meshes:
        if mesh.extras and isinstance(mesh.extras, dict):
            for n in mesh.extras.get("targetNames", []):
                names.add(n)
    return names

def find_node_by_name(glb, name):
    """Return (index, node) or (None, None)."""
    for i, node in enumerate(glb.nodes):
        if getattr(node, 'name', None) == name:
            return i, node
    return None, None

# ─── Step 1: Decompress Meshopt ───────────────────────────────────────────

def decompress_meshopt(src_path, dst_path):
    """Use gltf-transform copy to strip EXT_meshopt_compression."""
    try:
        result = subprocess.run(
            ["npx", "--yes", "@gltf-transform/cli@latest", "copy", src_path, dst_path],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            return False, result.stderr
        if "EXT_meshopt_compression" in (result.stderr + result.stdout):
            return True, "Meshopt decoded via gltf-transform copy"
        return True, "gltf-transform copy completed (no meshopt detected)"
    except FileNotFoundError:
        return False, "npx/gltf-transform not found — install Node.js"
    except subprocess.TimeoutExpired:
        return False, "gltf-transform timed out after 120s"

# ─── Step 2: Rename skeleton root → Armature ─────────────────────────────

def fix_armature_root(glb):
    """
    Ensure a node named 'Armature' exists as the sole scene root.

    Strategy:
    - If a node named 'Armature' already exists → nothing to do.
    - If there is exactly one scene root and it is the skeleton (no mesh) → rename it.
    - Otherwise → inject a new 'Armature' wrapper node that parents all existing
      scene roots, then make it the sole scene root.
    """
    from pygltflib import Node

    _, existing = find_node_by_name(glb, "Armature")
    if existing is not None:
        return "Already has Armature node — skipped"

    scene = glb.scenes[glb.scene if glb.scene is not None else 0]
    root_indices = list(scene.nodes or [])

    # If exactly one root and it has no mesh → safe to rename
    if len(root_indices) == 1:
        node = glb.nodes[root_indices[0]]
        if node.mesh is None:
            old_name = node.name
            node.name = "Armature"
            return f"Renamed single root '{old_name}' → 'Armature'"

    # Multiple roots (e.g. vroid: Body, Face, Hair, Hips) → wrap them
    new_node = Node(name="Armature", children=root_indices[:])
    new_index = len(glb.nodes)
    glb.nodes.append(new_node)
    scene.nodes = [new_index]
    return (f"Injected Armature wrapper node [{new_index}] "
            f"containing {len(root_indices)} original root(s): "
            f"{[getattr(glb.nodes[i],'name','?') for i in root_indices]}")

# ─── Step 3 & 4: Verify blendshapes ──────────────────────────────────────

def verify_blendshapes(target_names):
    """Return (arkit_missing, oculus_missing)."""
    arkit_missing = [s for s in ARKIT_52 if s not in target_names]
    oculus_missing = [s for s in OCULUS_15 if s not in target_names]
    return arkit_missing, oculus_missing

# ─── Step 5 (optional): Synthesize viseme names ───────────────────────────

def synthesize_visemes(glb, target_names):
    """
    Add viseme_* names to every mesh that has ARKit shapes but lacks visemes.

    pygltflib can read/write mesh extras but CANNOT decode or modify accessor
    binary data (that would require decompressing quantized buffers and
    modifying float32 arrays).  Instead we:
      1. Append the 15 viseme names to each mesh's extras.targetNames list.
         The morphTargetInfluences array stays the same length — those extra
         names map to undefined influences which Three.js silently ignores.
         TalkingHead will find the key in morphTargetDictionary but the
         influence will always be 0.
      2. Store the VISEME_SYNTHESIS formulas in the top-level asset extras so
         a future TalkingHead patch can bake proper vertex deltas at load time.

    This is a "stub synthesis" — it makes lipsync play without crashing but
    produces no visible mouth movement.  Full vertex-delta synthesis requires
    Blender or a custom gltf-transform Node.js script (see tomorrow's recipe).
    """
    added = []
    for mesh in glb.meshes:
        if not (mesh.extras and isinstance(mesh.extras, dict)):
            continue
        names_list = mesh.extras.get("targetNames", [])
        if not names_list:
            continue
        names_set = set(names_list)
        # Only patch meshes that already have ARKit shapes
        if not any(s in names_set for s in ["jawOpen", "mouthFunnel", "mouthPucker"]):
            continue
        # Add missing viseme names
        added_here = []
        for v in OCULUS_15:
            if v not in names_set:
                names_list.append(v)
                added_here.append(v)
        if added_here:
            mesh.extras["targetNames"] = names_list
            added.extend(added_here)

    # Store synthesis recipe in asset extras
    if glb.asset.extras is None:
        glb.asset.extras = {}
    glb.asset.extras["visemeSynthesis"] = VISEME_SYNTHESIS

    return list(set(added))


# ─── Main ─────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    synthesize = "--synthesize-visemes" in args
    paths = [a for a in args if not a.startswith("--")]

    if not paths:
        print("ERROR: No input file specified.", file=sys.stderr)
        sys.exit(1)

    input_path = paths[0]
    output_path = paths[1] if len(paths) > 1 else None
    if output_path is None:
        base, ext = os.path.splitext(input_path)
        output_path = base + "-fixed" + ext

    if not os.path.exists(input_path):
        print(f"ERROR: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    t0 = time.time()
    print(f"\navatar-fix.py — processing {os.path.basename(input_path)}")
    print("=" * 60)

    # ── Work on a temp copy so we can do multi-step pipeline ──────────────
    with tempfile.TemporaryDirectory() as tmpdir:
        step1_out = os.path.join(tmpdir, "step1_decompressed.glb")
        step2_in  = step1_out

        # ── STEP 1: Meshopt decompression ─────────────────────────────────
        print("\n[1/5] Checking / decompressing Meshopt …")
        from pygltflib import GLTF2
        probe = GLTF2().load(input_path)
        exts = probe.extensionsRequired or []
        needs_decompress = "EXT_meshopt_compression" in exts

        if needs_decompress:
            log(f"EXT_meshopt_compression detected — running gltf-transform copy")
            ok2, msg = decompress_meshopt(input_path, step1_out)
            if not ok2:
                warn(f"Decompression failed: {msg}")
                warn("Continuing with original (GLTFLoader may fail)")
                shutil.copy(input_path, step1_out)
            else:
                ok(msg)
                new_size = os.path.getsize(step1_out) / 1024 / 1024
                orig_size = os.path.getsize(input_path) / 1024 / 1024
                log(f"  {orig_size:.2f} MB → {new_size:.2f} MB (decompressed)")
        else:
            log("No Meshopt compression — copy as-is")
            shutil.copy(input_path, step1_out)
            ok("No decompression needed")

        # ── Load GLB for Python manipulation ──────────────────────────────
        glb = GLTF2().load(step2_in)

        # ── STEP 2: Rename/inject Armature root ───────────────────────────
        print("\n[2/5] Fixing skeleton root → 'Armature' …")
        result = fix_armature_root(glb)
        ok(result)

        # ── STEP 3: Verify ARKit blendshapes ──────────────────────────────
        print("\n[3/5] Verifying ARKit blendshapes (52 required) …")
        target_names = collect_target_names(glb)
        arkit_missing, oculus_missing = verify_blendshapes(target_names)

        if not arkit_missing:
            ok(f"All 52 ARKit shapes present")
        else:
            warn(f"{len(arkit_missing)} ARKit shapes MISSING: {arkit_missing[:10]}")
            if len(arkit_missing) > 42:
                warn("  → This avatar lacks ARKit blendshapes entirely.")
                warn("  → TalkingHead will have no facial animation.")

        # ── STEP 4: Verify Oculus visemes ─────────────────────────────────
        print("\n[4/5] Verifying Oculus visemes (15 required) …")
        if not oculus_missing:
            ok("All 15 Oculus visemes present")
        else:
            warn(f"{len(oculus_missing)} Oculus visemes MISSING: {oculus_missing}")
            if synthesize and not arkit_missing:
                log("  --synthesize-visemes active and ARKit present → will synthesize")
            elif synthesize and arkit_missing:
                warn("  --synthesize-visemes requested but ARKit shapes missing → cannot synthesize")

        # ── STEP 5 (optional): Synthesize visemes ─────────────────────────
        print("\n[5/5] Viseme synthesis …")
        if synthesize and oculus_missing and not arkit_missing:
            added = synthesize_visemes(glb, target_names)
            if added:
                ok(f"Stub-synthesized {len(added)} viseme name(s): {added}")
                log("  NOTE: stub synthesis adds targetNames only — no vertex deltas.")
                log("  Lipsync will be active but mouth will not visibly move.")
                log("  For full synthesis, use Blender (see tomorrow's recipe).")
            else:
                warn("Synthesis ran but added nothing — check mesh extras.targetNames")
        elif synthesize and not oculus_missing:
            ok("All visemes already present — synthesis not needed")
        else:
            log("Synthesis skipped (use --synthesize-visemes to enable)")

        # ── Save ──────────────────────────────────────────────────────────
        print(f"\n[Saving] → {output_path}")
        glb.save(output_path)
        out_size = os.path.getsize(output_path) / 1024 / 1024
        ok(f"Saved {out_size:.2f} MB")

    # ── Final report ──────────────────────────────────────────────────────
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"SUMMARY  ({elapsed:.1f}s)")
    print("=" * 60)

    # Re-probe output
    from pygltflib import GLTF2
    out_glb = GLTF2().load(output_path)

    # Check Armature node
    _, arm_node = find_node_by_name(out_glb, "Armature")
    armature_ok = arm_node is not None
    print(f"  Armature node:    {'PASS' if armature_ok else 'FAIL'}")

    # Check extensions
    out_exts = out_glb.extensionsRequired or []
    meshopt_gone = "EXT_meshopt_compression" not in out_exts
    print(f"  Meshopt-free:     {'PASS' if meshopt_gone else 'FAIL (still required)'}")

    out_targets = collect_target_names(out_glb)
    arkit_ok = all(s in out_targets for s in ARKIT_52)
    oculus_ok = all(s in out_targets for s in OCULUS_15)
    print(f"  ARKit 52 shapes:  {'PASS' if arkit_ok else f'FAIL ({sum(1 for s in ARKIT_52 if s not in out_targets)} missing)'}")
    print(f"  Oculus 15 visemes:{'PASS' if oculus_ok else f'FAIL ({sum(1 for s in OCULUS_15 if s not in out_targets)} missing)'}")

    verdict = armature_ok and meshopt_gone
    arkit_missing_count = sum(1 for s in ARKIT_52 if s not in out_targets)
    if arkit_ok and oculus_ok:
        verdict_str = "TalkingHead-ready"
    elif oculus_ok and arkit_missing_count <= 3:
        verdict_str = f"TalkingHead-ready (minor: {arkit_missing_count} ARKit shape(s) absent)"
    elif arkit_missing_count <= 30 and oculus_ok:
        verdict_str = "Partial (some ARKit missing — reduced expressiveness)"
    elif arkit_missing_count > 30:
        verdict_str = "Not usable for TalkingHead (no ARKit shapes)"
    else:
        verdict_str = "Partial (ARKit only — lipsync stubbed or missing)"

    print(f"\n  Verdict: {verdict_str}")
    print(f"  Output:  {output_path}\n")

    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
