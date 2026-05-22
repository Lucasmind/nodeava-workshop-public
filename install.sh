#!/usr/bin/env bash
# Top-level entrypoint for the NodeAva workshop installer wizard.
# The real script lives at scripts/install.sh; this stub keeps the
# documented `./install.sh` UX working from the project root.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec "$HERE/scripts/install.sh" "$@"
