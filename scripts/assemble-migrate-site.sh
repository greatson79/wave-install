#!/bin/bash
# Assemble local site files only; publishing belongs to the release owner.
set -euo pipefail
[ "$#" -eq 1 ] || { echo 'Usage: assemble-migrate-site.sh OUTPUT_DIR' >&2; exit 2; }
SCRIPTS=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$1"
OUT=$(cd "$1" && pwd)
cp "$SCRIPTS/migrate.ps1" "$OUT/migrate.ps1"
cp "$SCRIPTS/migrate.sh" "$OUT/migrate.sh"
PIN=$(shasum -a 256 "$OUT/migrate.ps1"); PIN=${PIN%% *}
sed "s/__WAVE_MIGRATE_PS1_SHA256__/$PIN/g" "$SCRIPTS/migrate-start.ps1" > "$OUT/migrate"
(cd "$OUT" && shasum -a 256 migrate migrate.ps1 migrate.sh > SHA256SUMS-migrate)
