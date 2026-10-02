import hashlib, json, pathlib, shutil, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gate


def put(base, name, doc, raw=True):
    base.mkdir(parents=True, exist_ok=True)
    if raw:
        (base / (name + ".raw")).write_text("raw of " + name)
        doc["raw"] = [{"path": name + ".raw", "sha256": hashlib.sha256(("raw of " + name).encode()).hexdigest()}]
    (base / name).write_text(json.dumps(doc), encoding="utf-8")


def os_set(b):
    put(b, "G1_state.json", {"status": "completed", "required_steps_passed": True, "steps": {"S%02d" % i: {"status": "completed"} for i in range(10)}}, raw=False)
    put(b, "G2_preflight.json", {"checks": [{"id": "C20", "status": "WARN"}, {"id": "C01", "status": "PASS"}]}, raw=False)
    put(b, "G3_inject.json", {"new_file_count": 0, "roles": {"master": {"injected_sha256": "a", "pack_sha256": "a", "injected_bytes": 30000}}})
    put(b, "G4_boot.json", {"steps": [{"n": n, "exit": 0} for n in range(1, 6)], "seats": [{"role": r, "alive": True} for r in ("master", "cso", "worker")]})
    for g, extra in (("G5", ("G5_meta.json", {"from_version": "0.2.3"})), ("G6", ("G6_claude_untouched.json", {"before_sha256": "x", "after_sha256": "x"}))):
        s = b / g
        shutil.copy(b / "G2_preflight.json", s / "G2_preflight.json") if s.mkdir() is None else None
        for n in ("G3_inject.json", "G4_boot.json"):
            shutil.copy(b / n, s / n)
            for f in b.glob(n + ".raw"): shutil.copy(f, s / f.name)
        put(s, extra[0], dict(extra[1]))
    put(b, "H1_help_landing.json", {"landed_s": 42, "dashboard_listed": True})
    put(b, "H2_answer_shown.json", {"shown_s": 90})
    put(b, "H3_mask.json", {"planted": ["t"], "found_in": {"ledger": 0, "dashboard": 0, "supabase": 0}})
    put(b, "H4_failopen.json", {"server_blocked": True, "step10_ok": True})


def make_all(root):
    for o in ("mac", "win"): os_set(root / o)
    c = root / "common"
    c.mkdir(parents=True, exist_ok=True)
    (c / "warn_allowlist.json").write_text(json.dumps({"mac": ["C20"], "win": ["C20"]}))
    put(c, "G7_text.json", {"gen_check_exit": 0, "license_files": ["LICENSES/jarvis-install-MIT.txt", "LICENSE"]})
    put(c, "G8_review.json", {"verdicts": {"zen": {"verdict": "ACCEPT", "blocking": 0}, "noah": {"verdict": "ACCEPT", "blocking": 0}}})
    put(c, "H5_dashboard_ledger.json", {"ledger_count": 3, "dashboard_count": 3, "status_match": True})
    real = c / "real"
    for i, o in enumerate(("win", "win", "mac")):
        put(real, "d%d.json" % i, {"os": o, "seats": ["master", "cso", "worker"], "human_hands": {"login_approve": 1, "other": 0}})


def verdicts(root):
    return {r["id"] + k: v[0] for r in gate.judge(root) for k, v in r.items() if k in ("mac", "win", "common")}


class T(unittest.TestCase):
    def setUp(self):
        self.d = pathlib.Path(tempfile.mkdtemp()); make_all(self.d)

    def tearDown(self): shutil.rmtree(self.d)

    def test_all_pass_exit0(self):
        self.assertEqual(set(verdicts(self.d).values()), {gate.PASS})
        self.assertEqual(gate.main([str(self.d), "--json"]), 0)

    def test_missing_file_is_unmeasured_not_pass(self):
        (self.d / "mac" / "G3_inject.json").unlink()
        v = verdicts(self.d)
        self.assertEqual(v["G3mac"], gate.NA); self.assertEqual(v["G3win"], gate.PASS)
        self.assertEqual(gate.main([str(self.d), "--json"]), 1)

    def test_tampered_raw_is_fail(self):
        (self.d / "win" / "G4_boot.json.raw").write_text("changed")
        self.assertEqual(verdicts(self.d)["G4win"], gate.FAIL)

    def test_bad_values_fail(self):
        doc = json.loads((self.d / "mac" / "G4_boot.json").read_text()); doc["seats"].append({"role": "reviewer-codex", "alive": True})
        (self.d / "mac" / "G4_boot.json").write_text(json.dumps(doc))
        self.assertEqual(verdicts(self.d)["G4mac"], gate.FAIL)
        (self.d / "mac" / "G2_preflight.json").write_text(json.dumps({"checks": [{"id": "C21", "status": "FAIL"}]}))
        self.assertEqual(verdicts(self.d)["G2mac"], gate.FAIL)

    def test_new_warn_and_missing_allowlist(self):
        (self.d / "common" / "warn_allowlist.json").write_text(json.dumps({"mac": [], "win": ["C20"]}))
        v = verdicts(self.d); self.assertEqual((v["G2mac"], v["G2win"]), (gate.FAIL, gate.PASS))
        (self.d / "common" / "warn_allowlist.json").unlink()
        self.assertEqual(verdicts(self.d)["G2win"], gate.NA)

    def test_g9_needs_three_devices(self):
        (self.d / "common" / "real" / "d2.json").unlink()
        self.assertEqual(verdicts(self.d)["G9common"], gate.NA)

    def test_g5_subfolder_regate(self):
        (self.d / "win" / "G5" / "G4_boot.json").write_text(json.dumps({"steps": [{"n": 1, "exit": 2}], "raw": []}))
        self.assertIn(verdicts(self.d)["G5win"], (gate.NA, gate.FAIL))
        self.assertNotEqual(verdicts(self.d)["G5win"], gate.PASS)

    def test_empty_root_all_unmeasured(self):
        e = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(set(verdicts(e).values()), {gate.NA}); shutil.rmtree(e)


if __name__ == "__main__":
    unittest.main()
