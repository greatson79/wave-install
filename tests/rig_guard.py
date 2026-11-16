"""Fail-closed external-program guard for EVERY installer test (INCIDENT 11/16 23:29: a unit test reached the real
`claude auth login` and opened the owner's browser; review r1 11/17: a test compiled a native sleeper with `cc` and ran it).

Importing this module (each test file does) does three things on POSIX hosts:
 1. Stubs: claude, codex, open, osascript, launchctl, brew, security, defaults, killall, pkill, tart, sudo record the call in
    <root>/stub-calls.log and exit 97 (never run the real program); curl is allowed only for file:// and loopback URLs;
    the process probes ps / lsof / pgrep record the call and print an EMPTY table (exit 0 / 1 / 1 = "nothing found").
 2. Confined PATH for every child: only rig directories (temp dirs, the repo checkout, the stub dir) and ONE allowlist
    directory (<root>/allow-bin) of symlinks to the explicit ALLOW_TOOLS below. Every other directory (/usr/bin, /bin,
    /opt/homebrew, ~/.local/bin, ...) is dropped, so a script can only reach an allowlisted tool, a stub or a fixture by name.
    `ps`, `kill`(binary), `cc`, `sleep`-as-a-daemon etc. are simply not there. Tests that need a working fake put their own
    fake dir first on PATH, which still wins.
 3. Wraps subprocess.Popen: the program about to start must be (a) an allowlisted top-level program (ALLOW_TOP, the
    interpreters/tools the tests drive directly) or (b) a fixture SCRIPT inside the rig (text file starting with "#!" whose
    interpreter is itself allowlisted). Anything else — `cc`, `/bin/sleep`, `tail`, a native binary copied into a temp dir —
    raises RuntimeError and the child never starts.
Not covered (honest limit): an absolute path written INSIDE a shell script (e.g. /usr/libexec/PlistBuddy) is not
intercepted; only names (via the confined PATH) and the programs Python starts directly are.
WAVE_TEST_ROOT (this rig's root) is exported to every child.
"""
import atexit, os, shutil, stat, subprocess, sys, tempfile

GUARDED = ("claude", "codex", "open", "osascript", "launchctl", "brew", "security", "defaults", "killall", "pkill", "tart", "sudo", "curl",
           "ps", "lsof", "pgrep")
# Probe stubs: record the call and answer "no such process / nothing open" (an empty rig), never the host's real table.
EMPTY_PROBES = {"ps": 0, "lsof": 1, "pgrep": 1}
# Programs a test may start DIRECTLY (argv[0]); fixture scripts in the rig are checked separately.
ALLOW_TOP = ("bash", "sh", "python3", "pwsh", "git", "shasum", "tar",
             "uname", "file")  # Python's own platform.processor()/platform.platform() run `uname -p` / `file <python>` (read-only)
# Tools scripts may call BY NAME (symlinked into allow-bin). Explicit list — growing it needs a reason in the commit.
ALLOW_TOOLS = ("bash", "sh", "env", "python3", "perl", "cat", "grep", "egrep", "sed", "awk", "tr", "cut", "head", "tail",
               "sort", "uniq", "wc", "mkdir", "rmdir", "rm", "mv", "cp", "ln", "chmod", "touch", "date", "basename",
               "dirname", "printf", "echo", "test", "expr", "id", "uname", "mktemp", "find", "xargs", "tee", "sleep",
               "shasum", "tar", "gzip", "gunzip", "ditto", "git", "stat", "readlink", "realpath", "diff", "cmp", "ls",
               "od", "xxd", "file", "plutil", "sw_vers", "true", "false", "seq", "dd", "base64", "unzip", "zip", "iconv",
               "nl", "comm", "paste", "fold", "rev", "pwd", "whoami", "hostname", "getconf", "locale", "sha256sum",
               "md5", "cksum", "split", "join", "tput", "stty", "which",
               "zsh",  # zsh: bootstrap.sh:956 verifies its PATH hook with `zsh -f` (no rc files) on a rig file
               "df")   # df: bootstrap's required-command check (read-only disk free)
ACTIVE = os.name == "posix"
ROOT = STUBS = LOG = FAKE_CLAUDE = NO_CLAUDE = ALLOW_BIN = None
REPO = os.path.realpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
_SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def _rig_roots():
    return {os.path.realpath(tempfile.gettempdir()), os.path.realpath("/private/tmp"), REPO, os.path.realpath(ROOT)}


def _under(path, roots):
    return any(path == r or path.startswith(r + os.sep) for r in roots)


def _inside_rig(path):
    """The REAL target lives in the rig (a symlink from /tmp to /bin/x is NOT inside; /var/folders -> /private/var/folders is)."""
    return _under(os.path.realpath(path), _rig_roots())


def check_env(env):
    """Raise before exec if any guarded program would resolve to a real (non-rig) binary."""
    for name in GUARDED:
        found = shutil.which(name, path=env.get("PATH", ""))
        if found and not _inside_rig(found):
            raise RuntimeError(f"rig_guard: '{name}' resolves to REAL {found} — refusing to start the process")


def _fix_path(env):
    """Confine PATH: keep rig dirs only, ensure the stub dir, end with the allowlist dir."""
    env = dict(env)
    parts = [p for p in env.get("PATH", "").split(os.pathsep) if p and p != ALLOW_BIN and _inside_rig(p)]
    if STUBS not in parts and NO_CLAUDE not in parts:
        parts.append(STUBS)
    parts.append(ALLOW_BIN)
    env["PATH"] = os.pathsep.join(parts)
    env.setdefault("WAVE_TEST_ROOT", ROOT)
    return env


def _shebang_interpreter(path):
    try:
        with open(path, "rb") as f:
            head = f.read(256)
    except OSError:
        return None
    if not head.startswith(b"#!"):
        return None
    words = head[2:].split(b"\n", 1)[0].decode("utf-8", "replace").split()
    if not words:
        return None
    if os.path.basename(words[0]) == "env" and len(words) > 1:
        return words[1]
    return os.path.basename(words[0])


def check_program(args, env, executable=None, shell=False):
    """Raise unless the program about to start is allowlisted (top-level tool) or an allowlisted-interpreter rig script."""
    if shell:
        prog = "sh"
    elif executable:
        prog = os.fspath(executable)
    else:
        prog = os.fspath(args if isinstance(args, (str, bytes, os.PathLike)) else args[0])
        prog = prog.decode() if isinstance(prog, bytes) else prog
    if os.path.realpath(prog) == os.path.realpath(sys.executable):
        return
    resolved = prog if os.sep in prog else shutil.which(prog, path=env.get("PATH", ""))
    if resolved is None:
        raise RuntimeError(f"rig_guard: '{prog}' is not on the confined PATH (not in the fixture allowlist) — refusing")
    if os.path.dirname(os.path.abspath(resolved)) == ALLOW_BIN:
        if os.path.basename(resolved) in ALLOW_TOP:
            return
        raise RuntimeError(f"rig_guard: '{prog}' is an allowlisted script tool but not a test entry program — refusing")
    if _inside_rig(resolved):
        interp = _shebang_interpreter(resolved)
        if interp is not None and (interp in ALLOW_TOOLS or os.path.realpath(interp) == os.path.realpath(sys.executable)):
            return
        raise RuntimeError(f"rig_guard: '{resolved}' is not a fixture script with an allowlisted interpreter — refusing")
    raise RuntimeError(f"rig_guard: '{prog}' resolves to {resolved}, not in the fixture allowlist — refusing to start the process")


def _stub(name):
    deny = (f'echo "{name} $*" >> "{LOG}"\n'
            f'echo "rig_guard: stubbed {name} (real program is never run by tests)" >&2\nexit 97\n')
    if name in EMPTY_PROBES:
        body = f'echo "{name} $*" >> "{LOG}"\nexit {EMPTY_PROBES[name]}\n'
    elif name == "curl":
        body = ('for a in "$@"; do case "$a" in http://127.0.0.1*|http://localhost*|https://127.0.0.1*|https://localhost*) ;;\n'
                '  http://*|https://*|ftp://*) ' + deny.replace("\n", "; ").rstrip("; ") + ' ;; esac; done\nexec /usr/bin/curl "$@"\n')
    else:
        body = deny
    path = os.path.join(STUBS, name)
    with open(path, "w") as f:
        f.write("#!/bin/sh\n" + body)
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def with_fake_claude(env):
    """For tests that need an already-logged-in claude: `auth status`/`--version` succeed, `auth login` is recorded and REFUSED (exit 99)."""
    env = dict(env)
    if FAKE_CLAUDE is None:  # non-POSIX: guard inactive
        return env
    env["PATH"] = FAKE_CLAUDE + os.pathsep + env.get("PATH", "")
    return env


def _install():
    global ROOT, STUBS, LOG, FAKE_CLAUDE, NO_CLAUDE, ALLOW_BIN
    ROOT = tempfile.mkdtemp(prefix="wave-test-root-", dir="/private/tmp")
    STUBS = os.path.join(ROOT, "stubs"); os.mkdir(STUBS); LOG = os.path.join(ROOT, "stub-calls.log")
    for name in GUARDED:
        _stub(name)
    ALLOW_BIN = os.path.join(ROOT, "allow-bin"); os.mkdir(ALLOW_BIN)
    for name in ALLOW_TOOLS:
        real = sys.executable if name == "python3" else shutil.which(name, path=_SYSTEM_PATH)
        if real and name not in GUARDED:
            os.symlink(real, os.path.join(ALLOW_BIN, name))
    # same stubs minus claude, for tests that assert "claude is NOT installed" (a claude stub would make `command -v claude` succeed);
    # a real claude is still unreachable: the confined PATH has no system dir.
    NO_CLAUDE = os.path.join(ROOT, "stubs-no-claude"); shutil.copytree(STUBS, NO_CLAUDE); os.remove(os.path.join(NO_CLAUDE, "claude"))
    FAKE_CLAUDE = os.path.join(ROOT, "fake-claude"); os.mkdir(FAKE_CLAUDE)
    fake = os.path.join(FAKE_CLAUDE, "claude")
    with open(fake, "w") as f:
        f.write('#!/bin/sh\ncase "$1 $2" in "auth status") echo \'{"loggedIn":true}\'; exit 0;; "auth login") echo "claude $*" >> "%s"; exit 99;; esac\n'
                'case "$1" in --version|-v) echo "2.1.278 (Claude Code)"; exit 0;; esac\necho "claude $*" >> "%s"; exit 98\n' % (LOG, LOG))
    os.chmod(fake, 0o755)
    atexit.register(shutil.rmtree, ROOT, True)
    os.environ.update(_fix_path(os.environ))
    original = subprocess.Popen.__init__

    def guarded_init(self, args, *a, **kw):
        env = _fix_path(kw["env"] if kw.get("env") is not None else os.environ)
        check_env(env)
        check_program(args, env, kw.get("executable"), kw.get("shell", False))
        kw["env"] = env
        original(self, args, *a, **kw)

    subprocess.Popen.__init__ = guarded_init


if ACTIVE and ROOT is None:
    _install()
