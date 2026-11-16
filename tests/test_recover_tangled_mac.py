"""0.3.6 C10 — the one-line installer recovers a "tangled" Mac (states a-f of 기준_..._ADDENDUM_C10).

Everything runs on an injected HOME / app roots under a private temp tree (11/7 rule: never the real /Applications,
~/.cys, launchd or a live cysd). launchctl is a recording fake. The "upstream daemon" is NOT a real process: bootstrap's
process probes go through the injected seam (WAVE_RECOVER_PS / WAVE_RECOVER_KILL, honoured only on injected roots), which
here reads/edits a fake process table file. No compiler, no background process, no real kill (review r1, Noah + Zen).
"""
try:
    import rig_guard  # noqa: F401 -- fail-closed external-program guard (11/16 incident)
except ImportError:  # run as tests.<module>
    from tests import rig_guard  # noqa: F401
import hashlib, json, os, plistlib, shutil, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY_ID, WAVE_ID = "com.cysjavis.terminal", "com.waveainetworks.wave-terminal"
FOREIGN = "/Applications/cys.app"


def tree_hashes(*dirs):
    out = {}
    for d in dirs:
        for p in sorted(Path(d).rglob("*")):
            if p.is_file() and not p.is_symlink():
                out[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


FIRST_FAKE_PID = 100001  # above the macOS pid limit (99998): can never name a real process


class FakeProc:
    """One row of the fake process table (what `ps -axo pid=,comm=` would print)."""
    def __init__(self, pid, exe): self.pid, self.exe = pid, exe


class Rig:
    def __init__(self, td):
        self.home = Path(td) / "home"; self.apps = self.home / "Applications"; self.la = self.home / "Library/LaunchAgents"
        self.wave = self.home / ".wavetest"; self.calls = Path(td) / "launchctl.calls"
        for d in (self.apps, self.la, self.wave, self.home / ".cys", self.home / ".local/state/cys"): d.mkdir(parents=True)
        self.procs = []
        fake = Path(td) / "fake-launchctl"; fake.write_text(f'#!/bin/sh\necho "$@" >> "{self.calls}"\nexit 0\n'); fake.chmod(0o755)
        self.launchctl = fake
        # process-table seam: fake `ps` prints the table; fake `kill -TERM <pid>` records the call and drops that row
        self.table = Path(td) / "proc-table"; self.table.write_text(""); self.kills = Path(td) / "kill.calls"
        self.fake_ps = Path(td) / "fake-ps"; self.fake_ps.write_text(f'#!/bin/sh\ncat "{self.table}"\n'); self.fake_ps.chmod(0o755)
        self.fake_kill = Path(td) / "fake-kill"
        self.fake_kill.write_text(f'#!/bin/sh\necho "$*" >> "{self.kills}"\ngrep -v "^$2 " "{self.table}" > "{self.table}.new"; mv "{self.table}.new" "{self.table}"\n')
        self.fake_kill.chmod(0o755)
        # department records that must stay byte-identical
        (self.home / ".cys/depts.json").write_text('{"depts":["dev","ministry"]}\n')
        (self.home / ".local/state/cys/seat-1.json").write_text('{"seat":1,"role":"master"}\n')
        self.records = (self.home / ".cys", self.home / ".local/state/cys")
        self.lib = Path(td) / "lib.sh"; self.lib.write_text((ROOT / "bootstrap.sh").read_text().rsplit('\nmain "$@"', 1)[0])

    def bundle(self, path, bundle_id, status=None, daemon=False):
        path = Path(path); (path / "Contents/MacOS").mkdir(parents=True)
        (path / "Contents/Info.plist").write_bytes(plistlib.dumps({"CFBundleIdentifier": bundle_id, "CFBundleExecutable": "cys-app", "CFBundleShortVersionString": "9.9.9"}))
        cys = path / "Contents/MacOS/cys"
        cys.write_text('#!/bin/sh\ncase "$1" in status) cat "%s" ;; *) echo cys 9.9.9 ;; esac\n' % (path.parent.parent / "legacy-status.json"))
        cys.chmod(0o755)
        if status is not None: (path.parent.parent / "legacy-status.json").write_text(json.dumps(status))
        daemon_exe = path / "Contents/MacOS/fakedaemon"; daemon_exe.write_text("placeholder: never executed\n")
        if daemon:  # a row in the fake process table, not a process
            p = FakeProc(FIRST_FAKE_PID + len(self.procs), daemon_exe); self.procs.append(p)
            with open(self.table, "a") as f: f.write(f"{p.pid} {p.exe}\n")
        return path

    def plist(self, label, program):
        p = self.la / f"{label}.plist"; p.write_bytes(plistlib.dumps({"Label": label, "ProgramArguments": [str(program), "--daemon"], "RunAtLoad": True})); return p

    def pack(self, foreign):
        d = self.home / ".cys/pack/bin"; d.mkdir(parents=True, exist_ok=True)
        (d / "javis_preflight.py").write_text("cand = '%s'\n" % FOREIGN if foreign else "cand = 'wave'\n")
        (d / "javis_phoenix_harness.py").write_text("x = 1\n")
        (self.home / ".cys/pack/.pack-version").write_text("0.14.56\n" if foreign else "0.3.5\n")
        (self.home / ".cys/pack/user-edited.md").write_text("my own pack note\n")

    def run(self, fn="recover_tangled_mac"):
        env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.wave), WAVE_RECOVER_APP_ROOTS=str(self.apps),
                   WAVE_RECOVER_LAUNCHCTL=str(self.launchctl), WAVE_RECOVER_PS=str(self.fake_ps), WAVE_RECOVER_KILL=str(self.fake_kill),
                   PATH="/usr/bin:/bin:/usr/sbin:/sbin")
        r = subprocess.run(["bash", "-c", f'source "$1"; {fn}', "rig", str(self.lib)], env=env, capture_output=True, text=True, timeout=60)
        return r

    def alive(self, p): return any(l.split(" ", 1)[0] == str(p.pid) for l in self.table.read_text().splitlines())

    def close(self): pass  # nothing real was started


class Base(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.mkdtemp(prefix="c10-rig-", dir="/private/tmp"); self.rig = Rig(self._td)
        self.addCleanup(self.rig.close); self.addCleanup(shutil.rmtree, self._td, True)

    def assertRecordsSame(self, before):
        self.assertEqual(before, tree_hashes(*self.rig.records, ) if False else {k: v for k, v in tree_hashes(*self.rig.records).items() if "/pack/" not in k})

    def rec_before(self):
        return {k: v for k, v in tree_hashes(*self.rig.records).items() if "/pack/" not in k}

    def backups(self): return list((self.rig.wave / "backups").glob("*")) if (self.rig.wave / "backups").exists() else []


class StateA_LegacyDaemonHoldsSocket(Base):
    def test_a_no_seats_daemon_stopped_app_moved_records_same(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []}, daemon=True)
        wave = self.rig.bundle(self.rig.apps / "Wave Terminal.app", WAVE_ID)
        before = self.rec_before(); wave_before = tree_hashes(wave)
        r = self.rig.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(legacy.exists(), "leftover cys.app must leave the app folder")
        self.assertTrue(list((self.rig.wave / "backups").rglob("cys.app/Contents/Info.plist")), "moved to archive, never deleted")
        self.assertFalse(self.rig.alive(self.rig.procs[0]), "upstream cysd must be stopped")
        self.assertEqual(before, self.rec_before())
        self.assertEqual(wave_before, tree_hashes(wave), "our own bundle is untouched")
        self.assertIn("정리했습니다", r.stderr)
        self.assertEqual(self.rig.kills.read_text().split(), ["-TERM", str(self.rig.procs[0].pid)], "TERM through the seam, only that pid")

    def test_a_with_live_seats_stops_and_changes_nothing(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": [{"surface_ref": "surface:1", "role": "master", "exited": False}]}, daemon=True)
        self.rig.plist("com.cysjavis.cysd", legacy / "Contents/MacOS/cysd")
        snap = tree_hashes(self.rig.home); r = self.rig.run()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("아무것도 바꾸지 않았습니다", r.stderr)
        self.assertTrue(self.rig.alive(self.rig.procs[0]), "a daemon serving seats is never stopped")
        self.assertTrue(legacy.exists())
        self.assertEqual(snap, tree_hashes(self.rig.home))
        self.assertFalse(self.rig.calls.exists(), "no launchctl call before safety is proven")

    def test_a_unreadable_status_is_unprovable_so_stop(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status=None, daemon=True)
        (self.rig.home / "legacy-status.json").write_text("not json")
        snap = tree_hashes(self.rig.home); r = self.rig.run()
        self.assertNotEqual(r.returncode, 0); self.assertIn("아무것도 바꾸지 않았습니다", r.stderr)
        self.assertTrue(self.rig.alive(self.rig.procs[0])); self.assertEqual(snap, tree_hashes(self.rig.home))


class StateB_PackOverwritten(Base):
    def test_b_foreign_pack_backed_up_never_deleted(self):
        self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []})  # the original app that overwrote the pack is still here
        self.rig.pack(foreign=True)
        before = self.rec_before(); packsnap = tree_hashes(self.rig.home / ".cys/pack")
        r = self.rig.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        saved = list((self.rig.wave / "backups").glob("recovery-*/pack"))
        self.assertEqual(len(saved), 1, r.stderr)
        got = {str(p.relative_to(saved[0])): hashlib.sha256(p.read_bytes()).hexdigest() for p in saved[0].rglob("*") if p.is_file()}
        want = {str(Path(k).relative_to(self.rig.home / ".cys/pack")): v for k, v in packsnap.items()}
        self.assertEqual(got, want, "every pack file (incl. user-edited) saved byte-identical")
        self.assertEqual(packsnap, tree_hashes(self.rig.home / ".cys/pack"), "the installer step itself never deletes/overwrites the live pack")
        self.assertEqual(before, self.rec_before())

    def test_b_foreign_fingerprint_without_leftover_app_is_not_touched(self):
        # real-shape lesson (this Mac): a pack that mentions /Applications/cys.app but no leftover original app = not proof of an overwrite
        self.rig.pack(foreign=True); snap = tree_hashes(self.rig.home)
        r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(snap, tree_hashes(self.rig.home)); self.assertIn("그대로 둡니다", r.stderr)

    def test_b_wave_pack_is_left_alone(self):
        self.rig.pack(foreign=False); r = self.rig.run()
        self.assertEqual(r.returncode, 0); self.assertEqual(self.backups(), [])
        self.assertNotIn("원본 cys", r.stderr)

    def test_b_s06_forces_wave_pack_only_when_foreign(self):
        # step_s06 helper decides: foreign fingerprint -> init-pack --force after backup; clean pack -> plain init-pack
        self.rig.pack(foreign=True)
        cli = self.rig.wave / "bin/cys"; cli.parent.mkdir(parents=True)
        cli.write_text('#!/bin/sh\necho "$@" >> "%s/cys.args"\ncase "$1" in pack-manifest) echo \'{"files":{"directives/MASTER_DIRECTIVE.md":"x"}}\';; esac\n' % self.rig.wave); cli.chmod(0o755)
        (self.rig.home / ".cys/pack/directives").mkdir(); (self.rig.home / ".cys/pack/directives/MASTER_DIRECTIVE.md").write_text("m")
        env = dict(os.environ, HOME=str(self.rig.home), WAVE_HOME=str(self.rig.wave), PATH="/usr/bin:/bin:/usr/sbin:/sbin")
        subprocess.run(["bash", "-c", 'source "$1"; RECOVER_FOREIGN_PACK=1; SCRIPT_DIR="$2"; step_s06', "x", str(self.rig.lib), str(ROOT)], env=env, capture_output=True, text=True, timeout=60)
        args = (self.rig.wave / "cys.args").read_text()
        self.assertIn("init-pack --force", args)
        self.assertTrue(list((self.rig.wave / "backups").glob("recovery-*/pack/bin/javis_preflight.py")), "backup exists before the forced init")
        (self.rig.wave / "cys.args").unlink()
        subprocess.run(["bash", "-c", 'source "$1"; SCRIPT_DIR="$2"; step_s06', "x", str(self.rig.lib), str(ROOT)], env=env, capture_output=True, text=True, timeout=60)
        self.assertNotIn("--force", (self.rig.wave / "cys.args").read_text(), "no --force unless the recovery step saw the leftover original app")


class StateC_DeptMovedAndWaveAppParked(Base):
    def test_c_depts_on_cys_daemon_stops_changes_nothing(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": [{"surface_ref": "surface:3", "role": "worker", "exited": False}, {"surface_ref": "surface:4", "role": "cso", "exited": True}]}, daemon=True)
        parked = self.rig.bundle(self.rig.wave / "backups/agent-parked/Wave Terminal.app", WAVE_ID)
        snap = tree_hashes(self.rig.home); r = self.rig.run()
        self.assertNotEqual(r.returncode, 0); self.assertIn("아무것도 바꾸지 않았습니다", r.stderr)
        self.assertEqual(snap, tree_hashes(self.rig.home)); self.assertTrue(self.rig.alive(self.rig.procs[0]))
        self.assertTrue(parked.exists(), "nothing restored while unsafe")

    def test_c_no_seats_removes_legacy_and_restores_parked_wave_exact_match(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []}, daemon=True)
        parked = self.rig.bundle(self.rig.wave / "backups/agent-parked/Wave Terminal.app", WAVE_ID)
        impostor = self.rig.bundle(self.rig.wave / "backups/agent-parked2/Wave Terminal.app", "com.example.other")
        keep = tree_hashes(parked); before = self.rec_before()
        r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr)
        restored = self.rig.apps / "Wave Terminal.app"
        self.assertTrue(restored.exists()); self.assertEqual(tree_hashes(restored), {str(restored / Path(k).relative_to(parked)): v for k, v in keep.items()})
        self.assertTrue(impostor.exists(), "other bundle id is never taken")
        self.assertFalse(legacy.exists()); self.assertEqual(before, self.rec_before())
        self.assertIn("Wave Terminal 앱을 제자리로", r.stderr)

    def test_c_existing_wave_app_is_not_replaced_by_parked_copy(self):
        self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []})
        cur = self.rig.bundle(self.rig.apps / "Wave Terminal.app", WAVE_ID); self.rig.bundle(self.rig.wave / "backups/p/Wave Terminal.app", WAVE_ID)
        snap = tree_hashes(cur); r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr); self.assertEqual(snap, tree_hashes(cur))


class StateD_TwoPlists(Base):
    def test_d_plist_into_legacy_removed_waved_plist_kept(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []})
        wave = self.rig.bundle(self.rig.apps / "Wave Terminal.app", WAVE_ID)
        cysd = self.rig.plist("com.cysjavis.cysd", legacy / "Contents/MacOS/cysd")
        waved = self.rig.plist("com.waveainetworks.waved", wave / "Contents/MacOS/waved"); wsnap = waved.read_bytes()
        r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(cysd.exists()); self.assertEqual(wsnap, waved.read_bytes())
        calls = self.rig.calls.read_text(); self.assertIn("bootout", calls); self.assertIn("com.cysjavis.cysd", calls); self.assertNotIn("waveainetworks", calls)
        self.assertTrue(list((self.rig.wave / "backups").rglob("com.cysjavis.cysd.plist")), "plist archived")

    def test_d_cysd_plist_pointing_into_wave_is_left_to_the_rename_migration(self):
        wave = self.rig.bundle(self.rig.apps / "Wave Terminal.app", WAVE_ID)
        p = self.rig.plist("com.cysjavis.cysd", wave / "Contents/MacOS/cysd"); snap = p.read_bytes()
        r = self.rig.run(); self.assertEqual(r.returncode, 0); self.assertEqual(snap, p.read_bytes()); self.assertFalse(self.rig.calls.exists())

    def test_name_cys_alone_never_removes(self):
        other = self.rig.bundle(self.rig.apps / "cys.app", "com.example.notes", status={"surfaces": []})
        snap = tree_hashes(other); r = self.rig.run(); self.assertEqual(r.returncode, 0); self.assertEqual(snap, tree_hashes(other))


class StateE_HalfRecovered(Base):
    def test_e_app_in_trash_daemon_still_runs_no_seats(self):
        trash = self.rig.home / ".Trash"; trash.mkdir()
        legacy = self.rig.bundle(trash / "cys-c10trash.app", LEGACY_ID, status={"surfaces": []}, daemon=True)
        cysd = self.rig.plist("com.cysjavis.cysd", Path("/Applications/cys-c10trash.app/Contents/MacOS/cysd"))  # app left its place
        self.rig.pack(foreign=True); before = self.rec_before()
        r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(self.rig.alive(self.rig.procs[0]), "daemon of a trashed legacy bundle is stopped")
        self.assertTrue(legacy.exists(), "the user's Trash content is never touched")
        self.assertFalse(cysd.exists()); self.assertEqual(before, self.rec_before())
        self.assertEqual(len(list((self.rig.wave / "backups").glob("recovery-*"))), 1)

    def test_e_trashed_daemon_with_seats_stops(self):
        trash = self.rig.home / ".Trash"; trash.mkdir()
        self.rig.bundle(trash / "cys.app", LEGACY_ID, status={"surfaces": [{"surface_ref": "surface:1", "role": "master", "exited": False}]}, daemon=True)
        snap = tree_hashes(self.rig.home); r = self.rig.run()
        self.assertNotEqual(r.returncode, 0); self.assertEqual(snap, tree_hashes(self.rig.home)); self.assertTrue(self.rig.alive(self.rig.procs[0]))


class StateF_AplusBplusD(Base):
    def test_f_combined_order_and_records(self):
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []}, daemon=True)
        wave = self.rig.bundle(self.rig.apps / "Wave Terminal.app", WAVE_ID)
        cysd = self.rig.plist("com.cysjavis.cysd", legacy / "Contents/MacOS/cysd"); self.rig.plist("com.waveainetworks.waved", wave / "Contents/MacOS/waved")
        self.rig.pack(foreign=True); before = self.rec_before(); packsnap = tree_hashes(self.rig.home / ".cys/pack")
        r = self.rig.run(); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(legacy.exists()); self.assertFalse(cysd.exists()); self.assertFalse(self.rig.alive(self.rig.procs[0]))
        self.assertEqual(before, self.rec_before()); self.assertEqual(packsnap, tree_hashes(self.rig.home / ".cys/pack"))
        # evidence: hash list before/after saved next to the backup
        lists = list((self.rig.wave / "backups").glob("recovery-*/records-*.sha256"))
        self.assertGreaterEqual(len(lists), 2, "records hash list before + after is written")
        # order in the log: safety proof -> backup -> stop -> remove
        order = [r.stderr.find(k) for k in ("기록 확인", "백업", "중지", "옮겼습니다")]
        self.assertTrue(all(o >= 0 for o in order), r.stderr); self.assertEqual(order, sorted(order), r.stderr)

    def test_idempotent_second_run_is_silent_noop(self):
        self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, status={"surfaces": []}); self.rig.pack(foreign=False)
        self.assertEqual(self.rig.run().returncode, 0); n = len(self.backups())
        r = self.rig.run(); self.assertEqual(r.returncode, 0); self.assertEqual(len(self.backups()), n)

    def test_process_seam_is_ignored_when_not_injected(self):
        # production (WAVE_HOME = ~/.wave): WAVE_RECOVER_PS/KILL are ignored -> plain `ps`/`kill`. Under rig_guard the real
        # `ps` is not on the confined PATH, so it can only fail here — it must never read the fake table.
        legacy = self.rig.bundle(self.rig.apps / "cys.app", LEGACY_ID, daemon=True)
        env = dict(os.environ, HOME=str(self.rig.home), WAVE_HOME=str(self.rig.home / ".wave"),
                   WAVE_RECOVER_PS=str(self.rig.fake_ps), WAVE_RECOVER_KILL=str(self.rig.fake_kill))
        r = subprocess.run(["bash", "-c", 'source "$1"; recover_pids_under "$2"', "x", str(self.rig.lib), str(legacy)], env=env, capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), "", r.stderr)
        self.assertFalse(self.rig.kills.exists())

    def test_real_paths_refused_when_not_injected(self):
        # production roots are only /Applications and ~/Applications; the override env is ignored unless WAVE_HOME is not the default
        env = dict(os.environ, HOME=str(self.rig.home), WAVE_HOME=str(self.rig.home / ".wave"), WAVE_RECOVER_APP_ROOTS="/etc", WAVE_RECOVER_LAUNCHCTL="/bin/false")
        out = subprocess.run(["bash", "-c", 'source "$1"; recover_roots', "x", str(self.rig.lib)], env=env, capture_output=True, text=True).stdout
        self.assertNotIn("/etc", out); self.assertIn("/Applications", out)


if __name__ == "__main__":
    unittest.main()
