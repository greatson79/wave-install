"""Proof that the guard works: stubs record and refuse, a PATH reaching a real binary is refused BEFORE exec."""
try:
    import rig_guard
except ImportError:
    from tests import rig_guard
import os, shutil, subprocess, unittest


@unittest.skipUnless(rig_guard.ACTIVE, "POSIX only")
class RigGuard(unittest.TestCase):
    def calls(self):
        if not os.path.exists(rig_guard.LOG):
            return ""
        with open(rig_guard.LOG) as f:
            return f.read()

    def test_every_guarded_name_resolves_to_a_stub_and_refuses(self):
        for name in rig_guard.GUARDED:
            if name == "curl" or name in rig_guard.EMPTY_PROBES:
                continue
            with self.subTest(name=name):
                r = subprocess.run(["sh", "-c", f"command -v {name}; {name} auth login"], capture_output=True, text=True)
                self.assertTrue(r.stdout.strip().startswith(rig_guard.STUBS), r.stdout)
                self.assertEqual(r.returncode, 97)
                self.assertIn(f"{name} auth login", self.calls())

    def test_process_probes_are_stubbed_with_an_empty_table(self):
        r = subprocess.run(["sh", "-c", "ps -axo pid=,comm=; echo ps=$?; lsof -nP -t +D /; echo lsof=$?; pgrep x; echo pgrep=$?"], capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), ["ps=0", "lsof=1", "pgrep=1"], "no host process row may appear")
        self.assertIn("ps -axo pid=,comm=", self.calls())

    def test_explicit_system_only_path_still_gets_the_stubs(self):
        r = subprocess.run(["sh", "-c", "claude auth login"], env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 97)

    def test_curl_real_hosts_refused_file_and_loopback_allowed(self):
        r = subprocess.run(["curl", "-fsS", "https://example.com/x"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 97)
        r = subprocess.run(["curl", "-fsS", "file:///nonexistent-c10"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 97, "file:// reaches real curl (which then fails on the missing file)")

    def test_planted_real_path_is_dropped_from_the_child_path(self):
        # a test-provided PATH with a real system dir ahead of the stubs: the system dir is removed before exec
        r = subprocess.run(["sh", "-c", 'echo "$PATH"; command -v open; command -v cc || echo NO-CC'],
                           env={"PATH": "/usr/bin:" + rig_guard.STUBS}, capture_output=True, text=True)
        path, open_at, cc_at = r.stdout.splitlines()
        self.assertNotIn("/usr/bin", path.split(os.pathsep))
        self.assertTrue(open_at.startswith(rig_guard.STUBS), open_at)
        self.assertEqual(cc_at, "NO-CC")

    # ---- review r1 (Noah + Zen): fail closed on EVERY executable outside the explicit fixture allowlist ----
    def assertRefused(self, *args, **kw):
        marker = os.path.join(rig_guard.ROOT, "child-ran")
        with self.assertRaises(RuntimeError) as cm:
            subprocess.run(*args, **kw)
        self.assertIn("rig_guard", str(cm.exception))
        self.assertFalse(os.path.exists(marker))
        return str(cm.exception)

    def test_negative_cc_is_refused_before_exec(self):
        print("NEGATIVE cc:", self.assertRefused(["cc", "--version"], capture_output=True))
        print("NEGATIVE /usr/bin/cc:", self.assertRefused(["/usr/bin/cc", "-o", "/private/tmp/x", "x.c"], capture_output=True))

    def test_negative_arbitrary_binaries_are_refused_before_exec(self):
        print("NEGATIVE /bin/sleep:", self.assertRefused(["/bin/sleep", "300"]))
        print("NEGATIVE executable=/bin/sleep:", self.assertRefused(["fake-cysd", "300"], executable="/bin/sleep"))
        print("NEGATIVE tail:", self.assertRefused(["tail", "-f", "/dev/null"]))
        copied = os.path.join(rig_guard.ROOT, "native-copy"); shutil.copy("/bin/echo", copied)  # a native binary INSIDE the rig
        print("NEGATIVE native binary in rig:", self.assertRefused([copied, "hi"], capture_output=True))
        link = os.path.join(rig_guard.ROOT, "link-to-sleep"); os.symlink("/bin/sleep", link)
        print("NEGATIVE symlink rig->/bin/sleep:", self.assertRefused([link, "1"]))
        bad = os.path.join(rig_guard.ROOT, "fixture-bad-interp"); open(bad, "w").write("#!/usr/bin/osascript\nx\n"); os.chmod(bad, 0o755)
        print("NEGATIVE script with non-allowlisted interpreter:", self.assertRefused([bad]))

    def test_negative_inside_a_shell_unlisted_tools_are_not_found(self):
        r = subprocess.run(["bash", "-c", "cc --version; echo cc=$?; xcrun --version; echo xcrun=$?; nc -h; echo nc=$?"], capture_output=True, text=True)
        print("NEGATIVE in-shell:", r.stdout.strip().replace("\n", " "))
        self.assertIn("cc=127", r.stdout); self.assertIn("xcrun=127", r.stdout); self.assertIn("nc=127", r.stdout)

    def test_positive_fixture_script_with_allowlisted_interpreter_runs(self):
        ok = os.path.join(rig_guard.ROOT, "fixture-ok"); open(ok, "w").write("#!/bin/sh\necho fixture-ran\n"); os.chmod(ok, 0o755)
        self.assertEqual(subprocess.run([ok], capture_output=True, text=True).stdout.strip(), "fixture-ran")

    def test_check_env_unit(self):
        with self.assertRaises(RuntimeError):
            rig_guard.check_env({"PATH": "/usr/bin:/bin"})
        rig_guard.check_env({"PATH": rig_guard.STUBS + ":/usr/bin"})


if __name__ == "__main__":
    unittest.main()
