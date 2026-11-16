"""Proof that the guard works: stubs record and refuse, a PATH reaching a real binary is refused BEFORE exec."""
try:
    import rig_guard
except ImportError:
    from tests import rig_guard
import os, subprocess, unittest


@unittest.skipUnless(rig_guard.ACTIVE, "POSIX only")
class RigGuard(unittest.TestCase):
    def calls(self):
        if not os.path.exists(rig_guard.LOG):
            return ""
        with open(rig_guard.LOG) as f:
            return f.read()

    def test_every_guarded_name_resolves_to_a_stub_and_refuses(self):
        for name in rig_guard.GUARDED:
            if name == "curl":
                continue
            with self.subTest(name=name):
                r = subprocess.run(["sh", "-c", f"command -v {name}; {name} auth login"], capture_output=True, text=True)
                self.assertTrue(r.stdout.strip().startswith(rig_guard.STUBS), r.stdout)
                self.assertEqual(r.returncode, 97)
                self.assertIn(f"{name} auth login", self.calls())

    def test_explicit_system_only_path_still_gets_the_stubs(self):
        r = subprocess.run(["sh", "-c", "claude auth login"], env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
        self.assertEqual(r.returncode, 97)

    def test_curl_real_hosts_refused_file_and_loopback_allowed(self):
        r = subprocess.run(["curl", "-fsS", "https://example.com/x"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 97)
        r = subprocess.run(["curl", "-fsS", "file:///nonexistent-c10"], capture_output=True, text=True)
        self.assertNotEqual(r.returncode, 97, "file:// reaches real curl (which then fails on the missing file)")

    def test_planted_real_path_fails_before_the_process_starts(self):
        marker = os.path.join(rig_guard.ROOT, "must-not-exist")
        before = self.calls()
        with self.assertRaises(RuntimeError) as cm:
            subprocess.run(["sh", "-c", f"touch '{marker}'"], env={"PATH": "/usr/bin:" + rig_guard.STUBS})  # real /usr/bin/open ahead of the stub
        self.assertIn("REAL", str(cm.exception))
        self.assertFalse(os.path.exists(marker), "child must never have started")
        self.assertEqual(before, self.calls())

    def test_check_env_unit(self):
        with self.assertRaises(RuntimeError):
            rig_guard.check_env({"PATH": "/usr/bin:/bin"})
        rig_guard.check_env({"PATH": rig_guard.STUBS + ":/usr/bin"})


if __name__ == "__main__":
    unittest.main()
