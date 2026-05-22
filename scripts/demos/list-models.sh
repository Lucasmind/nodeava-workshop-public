#!/bin/bash
# Print the catalog. Highlights unavailable items in yellow.
set -euo pipefail
DEMOS="$(cd "$(dirname "$0")" && pwd)"
. "$DEMOS/_audio.sh"

curl -fsS "$ORCH_URL/v1/catalog" > /tmp/_nodeava_catalog.json
python3 - /tmp/_nodeava_catalog.json << 'PEOF'
import json, sys
with open(sys.argv[1]) as f:
    d = json.load(f)
RESET="\033[0m"; YELLOW="\033[33m"; GREEN="\033[32m"
for section in ("brains","voices","avatars","personalities"):
    print(f"\n=== {section} ===")
    for item in d.get(section, []):
        avail = item.get("available", True)
        color = GREEN if avail else YELLOW
        mark = "✓" if avail else "✗"
        reason = "" if avail else f"  ({item.get('reason','unavailable')})"
        print(f"  {color}{mark} {item['id']:25s}{RESET} {item['label']}{reason}")
PEOF
