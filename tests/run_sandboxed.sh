#!/bin/bash
# Run the installer suite inside the OS-level write sandbox tests/rig.sb (macOS sandbox-exec). Every child inherits it.
# Usage: bash tests/run_sandboxed.sh [extra `python3 -m unittest discover tests` args]
# The outside sentinel is created HERE, before entering the sandbox (inside, /private/var/tmp is not writable), and
# removed here afterwards; rig_guard checks it is byte-identical after every test.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd -P)"
command -v sandbox-exec >/dev/null || { echo "run_sandboxed: sandbox-exec not available (macOS only)" >&2; exit 2; }
TMP_REAL="$(python3 -c 'import os, tempfile; print(os.path.realpath(tempfile.gettempdir()))')"
OUTSIDE="$(mktemp -d /private/var/tmp/wave-rig-outside-XXXXXX)"
trap 'rm -rf "$OUTSIDE"' EXIT
mkdir "$OUTSIDE/keep-dir"; printf 'sentinel\n' > "$OUTSIDE/keep.txt"; printf 'inner\n' > "$OUTSIDE/keep-dir/inner.txt"
export WAVE_RIG_SANDBOX=1 WAVE_RIG_OUTSIDE="$OUTSIDE" PYTHONDONTWRITEBYTECODE=1
cd "$HERE/.."
rc=0
sandbox-exec -f "$HERE/rig.sb" -D TMPDIR_REAL="$TMP_REAL" -D REPO="$(pwd -P)" python3 -m unittest discover tests "$@" || rc=$?
exit "$rc"
