"""Fail-closed external-program guard for EVERY installer test (INCIDENT 11/16 23:29: a unit test reached the real
`claude auth login` and opened the owner's browser).

Importing this module (each test file does) does two things on POSIX hosts:
 1. Puts a stub directory in front of the system dirs on PATH. The stubs for claude, open, osascript, launchctl, brew,
    security, defaults, killall, pkill, tart, sudo record the call in <root>/stub-calls.log and exit 97 (never run the real
    program); curl is allowed only for file:// and loopback URLs. Tests that need a working fake put their own fake dir
    first on PATH, which still wins.
 2. Wraps subprocess.Popen: before ANY child starts, every guarded name must resolve to a path inside the rig (the stub dir
    or a temp dir). A PATH that would reach a real binary raises RuntimeError and the child is never started.
WAVE_TEST_ROOT (this rig's root) is exported to every child.
"""
import atexit, os, shutil, stat, subprocess, tempfile

GUARDED = ("claude", "open", "osascript", "launchctl", "brew", "security", "defaults", "killall", "pkill", "tart", "sudo", "curl")
_SYSTEM = ("/usr/", "/bin", "/sbin", "/opt/", "/System", "/Library", "/Applications")
ACTIVE = os.name == "posix"
ROOT = STUBS = LOG = FAKE_CLAUDE = NO_CLAUDE = None


def _inside_rig(path):
    real = os.path.realpath(path)
    roots = {os.path.realpath(tempfile.gettempdir()), os.path.realpath("/private/tmp"), os.path.realpath(STUBS)}  # (NO_CLAUDE lives under ROOT in /private/tmp)
    return any(real == r or real.startswith(r + os.sep) for r in roots)


def check_env(env):
    """Raise before exec if any guarded program would resolve to a real (non-rig) binary."""
    for name in GUARDED:
        found = shutil.which(name, path=env.get("PATH", ""))
        if found and not _inside_rig(found):
            raise RuntimeError(f"rig_guard: '{name}' resolves to REAL {found} — refusing to start the process")


def _fix_path(env):
    env = dict(env)
    parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    if STUBS not in parts and NO_CLAUDE not in parts:
        home_bin = os.path.join(os.path.expanduser("~"), ".local", "bin")
        at = next((i for i, p in enumerate(parts) if p.startswith(_SYSTEM) or p == home_bin or "homebrew" in p), len(parts))
        parts.insert(at, STUBS)
    env["PATH"] = os.pathsep.join(parts)
    env.setdefault("WAVE_TEST_ROOT", ROOT)
    return env


def _stub(name):
    deny = (f'echo "{name} $*" >> "{LOG}"\n'
            f'echo "rig_guard: stubbed {name} (real program is never run by tests)" >&2\nexit 97\n')
    if name == "curl":
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
    global ROOT, STUBS, LOG, FAKE_CLAUDE, NO_CLAUDE
    ROOT = tempfile.mkdtemp(prefix="wave-test-root-", dir="/private/tmp")
    STUBS = os.path.join(ROOT, "stubs"); os.mkdir(STUBS); LOG = os.path.join(ROOT, "stub-calls.log")
    for name in GUARDED:
        _stub(name)
    # same stubs minus claude, for tests that assert "claude is NOT installed" (a claude stub would make `command -v claude` succeed);
    # a real claude is still refused: check_env raises if one resolves outside the rig.
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
        kw["env"] = env
        original(self, args, *a, **kw)

    subprocess.Popen.__init__ = guarded_init


if ACTIVE and ROOT is None:
    _install()
