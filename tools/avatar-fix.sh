#!/usr/bin/env bash
# =============================================================================
# avatar-fix.sh — Make any GLB TalkingHead-compatible
#
# Usage:
#   ./avatar-fix.sh input.glb [output.glb] [--synthesize-visemes]
#
# What it does:
#   1. Decompresses EXT_meshopt_compression (via gltf-transform copy)
#   2. Renames/injects Armature skeleton root node
#   3. Verifies 52 ARKit blendshapes are present
#   4. Verifies 15 Oculus visemes are present
#   5. (--synthesize-visemes) Stubs in the 15 viseme names from ARKit shapes
#      so TalkingHead doesn't throw "Blend shapes not found"
#
# Dependencies:
#   - python3 + pygltflib  (pip3 install pygltflib)
#   - Node.js + npx        (for gltf-transform meshopt decompression)
#
# Performance budget: typically < 15s per GLB
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/avatar-fix.py"

# ── Dependency checks ─────────────────────────────────────────────────────

check_deps() {
    local missing=()

    if ! command -v python3 &>/dev/null; then
        missing+=("python3")
    fi

    if ! python3 -c "import pygltflib" &>/dev/null 2>&1; then
        echo "[dep] pygltflib not found — attempting install..."
        if command -v pip3 &>/dev/null; then
            pip3 install pygltflib --break-system-packages 2>/dev/null \
                || pip3 install pygltflib 2>/dev/null \
                || { echo "ERROR: could not install pygltflib"; exit 1; }
        else
            missing+=("pygltflib (pip3 install pygltflib)")
        fi
    fi

    if ! command -v npx &>/dev/null; then
        echo "WARNING: npx not found — Meshopt decompression will be skipped"
        echo "         Install Node.js from https://nodejs.org if needed"
    fi

    if [[ ${#missing[@]} -gt 0 ]]; then
        echo "ERROR: Missing dependencies: ${missing[*]}"
        exit 1
    fi
}

# ── Entry point ───────────────────────────────────────────────────────────

if [[ $# -lt 1 || "$1" == "--help" || "$1" == "-h" ]]; then
    sed -n '2,20p' "$0"
    exit 0
fi

INPUT="$1"

if [[ ! -f "$INPUT" ]]; then
    echo "ERROR: Input file not found: $INPUT"
    exit 1
fi

check_deps

echo ""
echo "avatar-fix.sh → delegating to avatar-fix.py"
python3 "$PYTHON_SCRIPT" "$@"
