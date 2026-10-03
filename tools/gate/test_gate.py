import hashlib, json, pathlib, shutil, sys, tempfile, unittest
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import gate


def put(base, name, doc, raw=True):
    base.mkdir(parents=True, exist_ok=True)
    if raw:
        (base / (name + ".raw")).write_text("raw of " + name)
        doc["raw"] = [{"path": name + ".raw", "sha256": hashlib.sha256(("raw of " + name).encode()).hexdigest()}]
    (base / name).write_text(json.dumps(doc), encoding="utf-8")


SCAN_FILES = {"boot-last.json": "{}", "bootstrap.out": "ok", "hook_master.out": "MASTER 지침"}


def g4_scan_targets(b):
    """G4 raw 에 부트·첫 출력 검사 대상(boot-last.json·bootstrap 출력·훅 stdout)을 해시와 함께 넣는다."""
    doc = json.loads((b / "G4_boot.json").read_text())
    for n, c in SCAN_FILES.items():
        (b / n).write_text(c, encoding="utf-8")
        doc["raw"].append({"path": n, "sha256": hashlib.sha256(c.encode()).hexdigest()})
    (b / "G4_boot.json").write_text(json.dumps(doc), encoding="utf-8")


def os_set(b):
    put(b, "G1_state.json", {"status": "complete", "required_steps_passed": True, "steps": {"S%02d" % i: {"status": "passed"} for i in range(10)}}, raw=False)
    put(b, "G2_preflight.json", {"checks": [{"id": "C20", "status": "WARN"}, {"id": "C01", "status": "PASS"}]}, raw=False)
    put(b, "G3_inject.json", {"new_file_count": 0, "roles": {r: {"injected_sha256": "a" * 64, "pack_sha256": "a" * 64, "injected_bytes": 30000, "pack_bytes": 30000} for r in ("master", "cso", "worker")}})
    put(b, "G4_boot.json", {"steps": [{"n": n, "exit": 0} for n in range(1, 6)], "seats": [{"role": r, "alive": True} for r in ("master", "cso", "worker")],
                            "trust": {"config": "~/.cys/claude/.claude.json", "hasCompletedOnboarding": True, "cwds": {"/Users/u": {"/Users/u": True}}, "remoteControlAtStartup": True}})
    g4_scan_targets(b)
    for g, extra in (("G5", ("G5_meta.json", {"from_version": "0.2.3"})), ("G6", ("G6_claude_untouched.json", {"before_sha256": "x", "after_sha256": "x"}))):
        s = b / g
        shutil.copy(b / "G2_preflight.json", s / "G2_preflight.json") if s.mkdir() is None else None
        for n in ("G3_inject.json", "G4_boot.json", *SCAN_FILES):
            shutil.copy(b / n, s / n)
            for f in b.glob(n + ".raw"): shutil.copy(f, s / f.name)
        put(s, extra[0], dict(extra[1]))
    put(b / "G5", "G7b_schedule_freeze.json", {"baseline_sha256": "a" * 64, "current_sha256": "a" * 64})
    put(b, "H1_help_landing.json", {"landed_s": 42, "dashboard_listed": True})
    put(b, "H2_answer_shown.json", {"shown_s": 90})
    put(b, "H3_mask.json", {"planted": ["t"], "found_in": {"ledger": 0, "dashboard": 0, "sheet": 0, "drive": 0}})
    put(b, "H4_failopen.json", {"server_blocked": True, "step10_ok": True})


def make_all(root):
    for o in ("mac", "win"): os_set(root / o)
    c = root / "common"
    c.mkdir(parents=True, exist_ok=True)
    (c / "warn_allowlist.json").write_text(json.dumps({"mac": ["C20"], "win": ["C20"]}))
    put(c, "G7_text.json", {"gen_check_exit": 0, "license_files": ["LICENSES/jarvis-install-MIT.txt", "LICENSE"]})
    put(c, "G8_review.json", {"verdicts": {"zen": {"verdict": "ACCEPT", "blocking": 0}, "noah": {"verdict": "ACCEPT", "blocking": 0}}})
    put(c, "H5_dashboard_ledger.json", {"ledger_count": 3, "dashboard_count": 3, "status_match": True})
    ids = ["i%d" % i for i in range(30)]
    put(c, "H6_concurrency.json", {"concurrent": 30, "submitted_ids": ids, "received_ids": ids, "quota_errors": 0})
    real = c / "real"
    for i, o in enumerate(("win", "mac")):
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

    def test_d1_tag_on_c20_warn_and_g3_ignores_20kb(self):
        r = {x["id"]: x for x in gate.judge(self.d)}
        self.assertIn("D1 잠정", r["G2"]["mac"][1])
        self.assertEqual(r["G3"]["mac"][0], gate.PASS)  # 30000B 주입이어도 원본 일치면 PASS

    def test_g3_rejects_hollow_or_partial_evidence(self):
        def g3(doc):
            (self.d / "mac" / "G3_inject.json").write_text(json.dumps(doc))
            # raw 해시 목록은 put() 이 만든 것을 유지
            return gate.g3(self.d / "mac")[0]
        good = json.loads((self.d / "mac" / "G3_inject.json").read_text())
        raw = good["raw"]
        h = lambda **kw: dict(good, raw=raw, **kw)
        self.assertEqual(g3(h(roles={"master": {}})), gate.FAIL)  # None==None 통과 금지
        self.assertEqual(g3(h(roles={r: v for r, v in good["roles"].items() if r != "cso"})), gate.FAIL)
        bad = {r: dict(v) for r, v in good["roles"].items()}; bad["worker"]["injected_sha256"] = "b" * 64
        self.assertEqual(g3(h(roles=bad)), gate.FAIL)
        bad = {r: dict(v) for r, v in good["roles"].items()}; bad["master"]["pack_bytes"] = 1
        self.assertEqual(g3(h(roles=bad)), gate.FAIL)
        bad = {r: dict(v) for r, v in good["roles"].items()}; bad["cso"]["pack_sha256"] = bad["cso"]["injected_sha256"] = "xyz"
        self.assertEqual(g3(h(roles=bad)), gate.FAIL)
        self.assertEqual(g3(h(new_file_count=1)), gate.FAIL)
        self.assertEqual(g3(good), gate.PASS)

    def test_g4_fails_when_boot_output_asks_user_to_install_or_approve(self):
        b = self.d / "mac"
        (b / "hook_master.out").write_text("선택 도구를 설치할까요?", encoding="utf-8")
        doc = json.loads((b / "G4_boot.json").read_text())
        for r in doc["raw"]:
            if r["path"] == "hook_master.out": r["sha256"] = hashlib.sha256("선택 도구를 설치할까요?".encode()).hexdigest()
        (b / "G4_boot.json").write_text(json.dumps(doc))
        v = gate.g4(b)
        self.assertEqual(v[0], gate.FAIL); self.assertIn("설치할까요", v[1])

    def test_g4_first_run_gate_keys(self):
        b = self.d / "mac"; doc = json.loads((b / "G4_boot.json").read_text())
        def run(trust):
            d2 = dict(doc); d2.pop("trust")
            if trust is not None: d2["trust"] = trust
            (b / "G4_boot.json").write_text(json.dumps(d2)); return gate.g4(b)
        self.assertEqual(run(None)[0], gate.NA)
        self.assertEqual(run({"hasCompletedOnboarding": False, "cwds": {"/Users/u": {"/Users/u": True}}})[0], gate.FAIL)
        v = run({"hasCompletedOnboarding": True, "cwds": {"C:\\Users\\u": {"C:\\Users\\u": True, "C:/Users/u": False}}})
        self.assertEqual(v[0], gate.FAIL); self.assertIn("C:/Users/u 신뢰", v[1])
        self.assertEqual(run({"hasCompletedOnboarding": True, "cwds": {}})[0], gate.FAIL)
        ok = {"hasCompletedOnboarding": True, "cwds": {"/Users/u": {"/Users/u": True}}, "remoteControlAtStartup": True}
        self.assertEqual(run(ok)[0], gate.PASS)
        for rc in (None, False):  # remoteControlAtStartup 누락·false = FAIL
            v = run(dict(ok, remoteControlAtStartup=rc) if rc is not None else {k: v for k, v in ok.items() if k != "remoteControlAtStartup"})
            self.assertEqual(v[0], gate.FAIL); self.assertIn("remoteControlAtStartup", v[1])

    def test_g4_unmeasured_without_scan_targets(self):
        b = self.d / "mac"; doc = json.loads((b / "G4_boot.json").read_text())
        doc["raw"] = [r for r in doc["raw"] if r["path"] != "bootstrap.out"]; (b / "G4_boot.json").write_text(json.dumps(doc))
        self.assertEqual(gate.g4(b)[0], gate.NA)

    def test_g2_full_ids_upgrade_only_and_blocker(self):
        c = self.d / "common"; b = self.d / "mac"
        (c / "warn_allowlist.json").write_text(json.dumps({"mac": ["C13.claude-md"], "upgrade_only": {"mac": ["C62.pack-heal-ledger"]}}))
        def run(folder, ids):
            (folder / "G2_preflight.json").write_text(json.dumps({"checks": [{"id": i, "status": "WARN"} for i in ids]}))
            return gate.g2(folder, c)
        self.assertEqual(run(b, ["C13.claude-md"])[0], gate.PASS)
        self.assertEqual(run(b, ["C20"])[0], gate.FAIL)  # 짧은 ID 는 전체 ID 와 다르다
        self.assertEqual(run(b, ["C62.pack-heal-ledger"])[0], gate.FAIL)  # 업그레이드 경로 밖에서는 불허
        self.assertEqual(run(b / "G5", ["C62.pack-heal-ledger"])[0], gate.PASS)
        v = run(b, ["C60.gate-wiring"]); self.assertEqual(v[0], gate.FAIL); self.assertIn("릴리스 차단", v[1])

    def test_g5_requires_zero_new_files_after_upgrade(self):
        b = self.d / "mac"; f = b / "G5" / "G3_inject.json"; doc = json.loads(f.read_text()); doc["new_file_count"] = 2
        f.write_text(json.dumps(doc)); v = gate.g5(b, self.d / "common")
        self.assertEqual(v[0], gate.FAIL)

    def test_g7b_schedule_freeze(self):
        b = self.d / "mac"; f = b / "G5" / "G7b_schedule_freeze.json"
        def put7(doc):
            (b / "G5" / "x.raw").write_text("raw")
            doc["raw"] = [{"path": "x.raw", "sha256": hashlib.sha256(b"raw").hexdigest()}]; f.write_text(json.dumps(doc))
            return gate.g7b(b)
        a, c = "a" * 64, "b" * 64
        self.assertEqual(put7({"baseline_sha256": a, "current_sha256": a})[0], gate.PASS)
        self.assertEqual(put7({"baseline_sha256": a, "current_sha256": c})[0], gate.FAIL)
        v = put7({"baseline_sha256": a, "baseline_sha256_lf": c, "baseline_crlf": 5, "current_sha256": c, "current_sha256_lf": c}); self.assertEqual(v[0], gate.FAIL); self.assertIn("줄바꿈", v[1])
        v = put7({"baseline_sha256": a, "current_sha256": a, "baseline_ref": "fa4c12b8", "current_ref": "83c86da3abc", "installed_current_sha256": c}); self.assertEqual(v[0], gate.PASS); self.assertIn("fa4c12b8 → 83c86da3", v[1])  # 설치본 sha 가 달라도 판정 무관
        self.assertEqual(put7({"baseline_sha256": "x", "current_sha256": a})[0], gate.FAIL)
        f.unlink(); self.assertEqual(gate.g7b(b)[0], gate.NA)

    def test_g1_ci_scope(self):
        f = self.d / "mac" / "G1_state.json"; d = json.loads(f.read_text())
        for k in ("S02", "S07"): d["steps"][k] = {"status": "failed"}
        d["steps"]["S08"] = {"status": "pending"}; f.write_text(json.dumps(d))
        self.assertEqual(gate.g1(self.d / "mac")[0], gate.PASS)  # 사람 단계는 CI 판정에서 제외(통과 선언 아님)
        d["steps"]["S04"] = {"status": "failed"}; f.write_text(json.dumps(d))
        self.assertEqual(gate.g1(self.d / "mac")[0], gate.FAIL)

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
        (self.d / "common" / "real" / "d1.json").unlink()
        self.assertEqual(verdicts(self.d)["G9common"], gate.NA)

    def test_g5_subfolder_regate(self):
        (self.d / "win" / "G5" / "G4_boot.json").write_text(json.dumps({"steps": [{"n": 1, "exit": 2}], "raw": []}))
        self.assertIn(verdicts(self.d)["G5win"], (gate.NA, gate.FAIL))
        self.assertNotEqual(verdicts(self.d)["G5win"], gate.PASS)

    def test_h6_concurrency(self):
        f = self.d / "common" / "H6_concurrency.json"
        d = json.loads(f.read_text()); base = dict(d)
        d["quota_errors"] = 2; f.write_text(json.dumps(d))
        self.assertEqual(verdicts(self.d)["H6common"], gate.FAIL)
        d = dict(base); d["received_ids"] = d["received_ids"][:-1]; f.write_text(json.dumps(d))
        self.assertEqual(verdicts(self.d)["H6common"], gate.FAIL)
        d = dict(base); d["concurrent"] = 10; f.write_text(json.dumps(d))
        self.assertEqual(verdicts(self.d)["H6common"], gate.NA)
        d = dict(base); del d["quota_errors"]; f.write_text(json.dumps(d))
        self.assertEqual(verdicts(self.d)["H6common"], gate.NA)

    def test_h3_needs_sheet_and_drive(self):
        f = self.d / "mac" / "H3_mask.json"
        d = json.loads(f.read_text()); del d["found_in"]["drive"]; f.write_text(json.dumps(d))
        self.assertEqual(verdicts(self.d)["H3mac"], gate.FAIL)

    def test_empty_root_all_unmeasured(self):
        e = pathlib.Path(tempfile.mkdtemp())
        self.assertEqual(set(verdicts(e).values()), {gate.NA}); shutil.rmtree(e)


if __name__ == "__main__":
    unittest.main()
