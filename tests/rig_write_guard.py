# Body of the write-confining wrappers that rig_guard puts in <root>/allow-bin for every WRITE-CAPABLE allowlisted tool
# (review r2, Noah). rig_guard prepends three constants (TOOL, REAL, ROOTS) and writes the result as an executable
# `#!<python> -I` script named after the tool. Before exec'ing the real tool it resolves every operand the tool can
# write/delete (incl. -t/-o/-f/-C/-d/of= targets) with realpath -m semantics (non-strict: missing parts are fine) against the
# caller's cwd, and refuses with exit 126 + "rig_guard: write outside rig refused: <path>" unless it is under ROOTS.
# Read-only tools are never wrapped (plain symlinks). Not covered: shell redirections (`> file`) and arbitrary writes made
# by general interpreters (bash/sh/zsh/python3/perl -e/awk) — those cannot be seen from argv.
import os
import sys

ARGS = sys.argv[1:]
SAFE = ("/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty")


def resolve(p):
    return os.path.realpath(os.path.join(os.getcwd(), os.path.expanduser(p)))


def inside(p):
    if p == "-":
        return True
    r = resolve(p)
    if r in SAFE or r.startswith("/dev/fd/"):
        return True
    return any(r == root or r.startswith(root + os.sep) for root in ROOTS)  # noqa: F821 (prepended)


def split(args, valued=()):
    """POSIX-ish split: options (with their value for `valued` flags) vs operands; `--` ends options."""
    opts, ops, i, end = [], [], 0, False
    while i < len(args):
        a = args[i]
        if end or a == "-" or not a.startswith("-"):
            ops.append(a)
        elif a == "--":
            end = True
        elif a in valued and i + 1 < len(args):
            opts.append((a, args[i + 1])); i += 1
        elif "=" in a and a.split("=", 1)[0] in valued:
            opts.append(tuple(a.split("=", 1)))
        else:
            opts.append((a, None))
        i += 1
    return opts, ops


def vals(opts, *names):
    return [v for k, v in opts if k in names and v is not None]


def has(opts, *names):
    return any(k in names for k, _ in opts)


def targets(tool, args):
    cwd = "."
    if tool in ("rm", "rmdir", "mkdir", "touch", "tee", "gzip", "gunzip", "mv"):
        opts, ops = split(args, ("-m", "-t", "-r", "-d", "-S"))
        out = vals(opts, "-t") + ops
        if tool == "touch":
            out = ops  # -r/-t/-d values are a reference file / a time, not written
        return out
    if tool in ("cp", "ditto", "ln"):
        opts, ops = split(args, ("-t", "--arch", "--bom"))
        if vals(opts, "-t"):
            return vals(opts, "-t")
        if tool == "ln" and len(ops) == 1:
            return [cwd]
        return ops[-1:]  # sources are only read (ln -s: the link text is not a write)
    if tool == "chmod":
        _, ops = split(args)
        return ops[1:]
    if tool == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    if tool == "tar":
        first = args[0] if args else ""
        letters = first.lstrip("-") if first and not first.startswith("--") else ""
        flags = set(letters) | {a.lstrip("-") for a in args if a.startswith("-") and not a.startswith("--") and len(a) == 2}
        archive, directory = [], []
        for i, a in enumerate(args):
            if a.startswith("--file="): archive.append(a.split("=", 1)[1])
            if a.startswith("--directory="): directory.append(a.split("=", 1)[1])
            if a in ("-C", "--directory", "-f", "--file") and i + 1 < len(args):
                (directory if a in ("-C", "--directory") else archive).append(args[i + 1])
        if letters and "f" in letters and not first.startswith("--"):  # bundled `czf archive` / `-czf archive`
            if len(args) > 1: archive.append(args[1])
        out = []
        if flags & set("cru") or any(a in ("--create", "--append", "--update") for a in args):
            out += [a for a in archive if a != "-"]
        if "x" in flags or "--extract" in args:
            out += directory or [cwd]
        return out
    if tool == "unzip":
        opts, ops = split(args, ("-d", "-x"))
        if has(opts, "-l", "-t", "-v", "-Z", "-p"):
            return []
        return vals(opts, "-d") or [cwd]
    if tool == "zip":
        _, ops = split(args, ("-b", "-n", "-t", "-tt", "-x", "-i"))
        return ops[:1]
    if tool == "split":
        _, ops = split(args, ("-a", "-b", "-l", "-n", "-p"))
        return ops[1:2] or [cwd]
    if tool == "mktemp":
        opts, ops = split(args, ("-p", "-t"))
        out = vals(opts, "-p") + [os.path.dirname(t) or cwd for t in ops if "/" in t]
        if not vals(opts, "-p") and not any("/" in t for t in ops):
            out.append(os.environ.get("TMPDIR") or "/tmp")
        return out
    if tool == "sed":
        opts, ops = split(args, ("-i", "-e", "-f"))
        if not any(k.startswith("-i") or k == "--in-place" for k, _ in opts):
            return []
        return ops if has(opts, "-e", "-f") else ops[1:]
    if tool == "perl":
        opts, ops = split(args, ("-e", "-E", "-I", "-M"))
        if not any(k.startswith("-i") or (k.startswith("-") and "i" in k[1:] and not k.startswith("--")) for k, _ in opts):
            return []
        return ops if has(opts, "-e", "-E") else ops[1:]
    if tool == "sort":
        opts, _ = split(args, ("-o", "-k", "-t", "-T", "-S"))
        return vals(opts, "-o", "-T")
    if tool == "uniq":
        _, ops = split(args, ("-f", "-s"))
        return ops[1:2]
    if tool == "xxd":
        _, ops = split(args, ("-c", "-g", "-l", "-s", "-o", "-n"))
        return ops[1:2]
    if tool == "base64":
        opts, _ = split(args, ("-o", "-i", "-b", "--output", "--input"))
        return vals(opts, "-o", "--output")
    if tool == "plutil":
        opts, ops = split(args, ("-o", "-convert", "-e", "-s", "-r"))
        if vals(opts, "-o"):
            return vals(opts, "-o")
        if any(a in ("-convert", "-replace", "-insert", "-remove") for a in args):
            return ops[-1:]
        return []
    if tool == "file":
        return [cwd] if "-C" in args else []
    if tool == "find":
        if not any(a in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint") for a in args):
            return []
        starts = []
        for a in args:
            if a.startswith("-") or a in ("(", "!"):
                break
            starts.append(a)
        return starts or [cwd]
    if tool == "git":
        if "config" in args and ("--global" in args or "--system" in args):
            return [os.path.expanduser("~/.gitconfig") if "--global" in args else "/etc/gitconfig"]
        out = [cwd]
        for i, a in enumerate(args):
            if a == "-C" and i + 1 < len(args): out.append(args[i + 1])
            if a.startswith(("--git-dir=", "--work-tree=")): out.append(a.split("=", 1)[1])
        return out
    return []


for t in targets(TOOL, ARGS):  # noqa: F821 (prepended)
    if not inside(t):
        line = "rig_guard: write outside rig refused: %s" % resolve(t)
        sys.stderr.write(line + "\n")
        try:  # R4 ADD (Theo): the refusal is also recorded so the running test FAILS (checked after every test by rig_guard)
            with open(REFUSALS, "a") as f:  # noqa: F821 (prepended)
                f.write("%s %s %s\n" % (TOOL, line, " ".join(ARGS)))  # noqa: F821
        except OSError:
            pass
        sys.exit(126)
os.execv(REAL, [TOOL] + ARGS)  # noqa: F821 (prepended)
