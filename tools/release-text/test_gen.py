import json, pathlib, subprocess, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gen

M = json.loads((gen.HERE / "manifest.json").read_text(encoding="utf-8"))


class T(unittest.TestCase):
    def test_cross_place_equal(self):
        self.assertEqual(gen.check_cross(gen.render(M), M), [])

    def test_mutation_detected(self):
        parts = gen.render(M)
        parts["get"] = parts["get"].replace("install-wave.sh", "install-wave2.sh", 1)
        self.assertTrue(gen.check_cross(parts, M))

    def test_reinstall_mutation_detected(self):
        for kind in ("readme", "get", "screen"):
            parts = gen.render(M)
            parts[kind] = parts[kind].replace(" -Reinstall", " -ReInstall", 1)
            self.assertTrue(gen.check_cross(parts, M), kind)

    def test_out_is_fresh(self):
        self.assertEqual(gen.check(M), [])

    def test_version_follows_manifest(self):
        m2 = json.loads(json.dumps(M)); m2["installer"]["tag"] = "v9.9.9"
        self.assertIn("v9.9.9/bootstrap.sh", gen.render(m2)["readme"])
        self.assertNotIn("v0.2.3", gen.render(m2)["screen"])

    def test_cli_check_exit(self):
        r = subprocess.run([sys.executable, str(gen.HERE / "gen.py"), "--check"], capture_output=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == "__main__":
    unittest.main()
