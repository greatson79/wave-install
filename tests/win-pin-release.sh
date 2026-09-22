#!/usr/bin/env bash
# No measurement means failure. --release-dir is only for local candidate/fixture checks.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
exec "${PYTHON:-python3}" "$root/tests/win-pin-check.py" "$@"
