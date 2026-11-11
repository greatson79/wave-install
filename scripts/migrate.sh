#!/bin/bash
# Add-on migration for macOS; requires only the tools shipped with macOS.
set -euo pipefail
umask 077
shopt -s nullglob dotglob
DRY=0
case "${1-}" in '' ) ;; --dry-run) DRY=1 ;; *) echo 'Usage: migrate.sh [--dry-run]' >&2; exit 2 ;; esac
[ "$#" -le 1 ] || exit 2
SRC=${WAVE_MIGRATE_SRC:-$HOME/.claude}
ACCOUNT=${CYS_ACCOUNT_DIR:-$HOME/.cys/claude}
LOCAL=${CYS_LOCAL_DIR:-$HOME/.cys/local}
BASE=$HOME/.cys/backup
COPIED=0 CLASH=0 HOOKS=0 MCP=0
REPORT=''
LINES=()
fail() { echo "ERROR: $*" >&2; exit 1; }
log() {
    printf '%s\n' "$*"
    if [ -n "$REPORT" ]; then printf '%s\n' "$*" >> "$REPORT"; else LINES+=("$*"); fi
}
# Refuse symlink ancestors and ambiguous paths before creating even a backup.
validate() {
    local p=$1 mode=${2:-fail} part rest
    case "$p/" in /*) ;; *) fail "Absolute path required: $p" ;; esac
    case "$p/" in *'/../'*|*'/./'*|*'//'*) fail "Non-normalized path: $p" ;; esac
    [ "$p" != / ] || fail 'Filesystem root is not a migration directory'
    rest=${p#/}; part=''
    while [ -n "$rest" ]; do
        part="$part/${rest%%/*}"
        if [ -L "$part" ]; then
            if [ "$mode" = skip ]; then log "skipped symlink: $part"; return 1; fi
            fail "symlink path: $part"
        fi
        if [[ "$rest" != */* ]]; then break; fi
        rest=${rest#*/}
    done
}
contains() { [ "$1" = "$2" ] || [[ "$2" = "$1/"* ]]; }
for p in "$SRC" "$ACCOUNT" "$LOCAL" "$BASE"; do validate "$p"; done
roots=("$SRC" "$ACCOUNT" "$LOCAL" "$BASE")
for ((i=0; i<4; i++)); do
    for ((j=i+1; j<4; j++)); do
        if contains "${roots[i]}" "${roots[j]}" || contains "${roots[j]}" "${roots[i]}"; then fail 'Source, destinations and backup must be disjoint'; fi
    done
done
[ -d "$SRC" ] || fail "Source directory missing: $SRC"
for p in "$ACCOUNT" "$LOCAL" "$BASE"; do
    [ ! -e "$p" ] || [ -d "$p" ] || fail "Not a directory: $p"
done
# shortcut: assumes no concurrent writers, add locking before supporting live migration.
copy_tree() {
    local src=$1 dst=$2 memory=${3:-0} child
    if [ "$memory" = 1 ] && [[ "$src" = *.jsonl ]]; then log "skipped transcript: $src"; return; fi
    if [ -L "$src" ]; then log "skipped symlink: $src"; return; fi
    if [ -d "$src" ]; then
        if [ "$DRY" = 0 ]; then mkdir "$dst"; fi
        for child in "$src"/*; do copy_tree "$child" "$dst/${child##*/}" "$memory"; done
    elif [ -f "$src" ]; then
        if [ "$DRY" = 0 ]; then cp -p -n "$src" "$dst"; fi
    else log "skipped special file: $src"; fi
}
TS=$(date '+%Y%m%d-%H%M%S')
BACKUP="$BASE/migrate-$TS"
if [ "$DRY" = 1 ]; then
    log 'DRY RUN: no files will be written'
    log "planned backup: $BACKUP"
else
    mkdir -p "$BASE"
    # Same-second runs get a fresh timestamp; never reuse an existing backup.
    until mkdir "$BACKUP" 2>/dev/null; do
        [ -e "$BACKUP" ] || fail "Cannot create backup: $BACKUP"
        sleep 1
        TS=$(date '+%Y%m%d-%H%M%S'); BACKUP="$BASE/migrate-$TS"
    done
    log "backup: $BACKUP"
    [ ! -d "$ACCOUNT" ] || copy_tree "$ACCOUNT" "$BACKUP/claude"
    [ ! -d "$LOCAL" ] || copy_tree "$LOCAL" "$BACKUP/local"
    REPORT="$BACKUP/report.txt"
    printf '%s\n' "${LINES[@]}" > "$REPORT"
fi
item() {
    local src=$1 dst=$2 memory=${3:-0}
    if [ -L "$src" ]; then log "skipped symlink: $src"; return; fi
    validate "$dst" skip || return 0
    if [ -e "$dst" ]; then CLASH=$((CLASH+1)); log "skipped clash: $dst"; return; fi
    log "copy: $src -> $dst"
    if [ "$DRY" = 0 ]; then mkdir -p "${dst%/*}"; fi
    copy_tree "$src" "$dst" "$memory"
    COPIED=$((COPIED+1))
}
if [ -L "$SRC/CLAUDE.md" ]; then
    log "skipped symlink: $SRC/CLAUDE.md"
elif [ -f "$SRC/CLAUDE.md" ] && validate "$ACCOUNT/CLAUDE.md" skip; then
    HASH=$(shasum -a 256 "$SRC/CLAUDE.md"); HASH=${HASH%% *}
    if [ -f "$ACCOUNT/CLAUDE.md" ] && awk -v hash="$HASH" '
        !inside && /^<!-- migrated from ~\/.claude\/CLAUDE.md .* -->$/ { inside=1; matched=0 }
        inside && $0 == "<!-- source sha256: " hash " -->" { matched=1 }
        $0 == "<!-- end migrated -->" { if (inside && matched) found=1; inside=0 }
        END { exit !found }
    ' "$ACCOUNT/CLAUDE.md"; then
        log 'skipped identical migrated CLAUDE.md block'
    elif [ -e "$ACCOUNT/CLAUDE.md" ] && [ ! -f "$ACCOUNT/CLAUDE.md" ]; then
        CLASH=$((CLASH+1)); log 'skipped clash: CLAUDE.md is not a regular file'
    else
        log "append: $SRC/CLAUDE.md -> $ACCOUNT/CLAUDE.md (sha256 $HASH)"
        if [ "$DRY" = 0 ]; then
            mkdir -p "$ACCOUNT"
            { printf '\n<!-- migrated from ~/.claude/CLAUDE.md %s -->\n<!-- source sha256: %s -->\n' "$TS" "$HASH"
              cat "$SRC/CLAUDE.md"
              printf '\n<!-- end migrated -->\n'
            } >> "$ACCOUNT/CLAUDE.md"
        fi
        COPIED=$((COPIED+1))
    fi
fi
for category in skills agents commands projects; do
    dir="$SRC/$category"
    if [ -L "$dir" ]; then log "skipped symlink: $dir"; continue; fi
    [ -d "$dir" ] || continue
    for src in "$dir"/*; do
        name=${src##*/}
        if [ -L "$src" ]; then log "skipped symlink: $src"; continue; fi
        case "$category" in
            skills) [ ! -d "$src" ] || item "$src" "$LOCAL/skills/$name" ;;
            agents|commands) item "$src" "$ACCOUNT/$category/$name" ;;
            projects)
                if [ -L "$src/memory" ] || [ -d "$src/memory" ]; then
                    item "$src/memory" "$ACCOUNT/projects/$name/memory" 1
                fi ;;
        esac
    done
done
# Parse locally with macOS JavaScriptCore; output names only, never values/secrets.
for settings in "$SRC/settings.json" "$HOME/.claude.json"; do
    if [ -L "$settings" ]; then log "skipped symlink: $settings"; continue; fi
    [ -f "$settings" ] || continue
    if ! names=$(/usr/bin/osascript -l JavaScript - "$settings" <<'JS'
ObjC.import('Foundation');
function run(args) {
    var text = $.NSString.stringWithContentsOfFileEncodingError(args[0], $.NSUTF8StringEncoding, null);
    if (!text) throw Error('Cannot read settings');
    var data = JSON.parse(ObjC.unwrap(text)), lines = [];
    ['hooks', 'mcpServers'].forEach(function (group) {
        if (data[group] && typeof data[group] === 'object')
            Object.keys(data[group]).forEach(function (name) { lines.push(group + ': ' + JSON.stringify(name)); });
    });
    return lines.join('\n');
}
JS
    ); then fail "Cannot parse settings: $settings (backup: $BACKUP)"; fi
    while IFS= read -r line; do
        [ -n "$line" ] || continue
        case "$line" in hooks:*) HOOKS=$((HOOKS+1));; mcpServers:*) MCP=$((MCP+1));; esac
        log "listed $settings $line"
    done <<< "$names"
done
log "summary: copied $COPIED / skipped (clash) $CLASH / listed hooks $HOOKS + MCP $MCP / backup $BACKUP"
if [ "$DRY" = 1 ]; then log 'report: none (dry run)'; else log "report: $REPORT"; fi
