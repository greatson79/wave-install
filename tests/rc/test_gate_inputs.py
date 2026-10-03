"""판정 입력 보호 — 표에 FAIL 이 있으면 실패 · 다른 잡 증거가 섞이면 감지. 실행: python3 -m unittest tests.rc.test_gate_inputs"""
import hashlib, json, os, pathlib, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_gate_table, check_evidence_mix
OFFICIAL1 = pathlib.Path("/Users/kylechoi/Desktop/Ai_works/개발본부/_round/evidence/rc4-official1-37138057562")

class GateTable(unittest.TestCase):
    def table(self, rows):
        d = tempfile.mkdtemp(); p = os.path.join(d, "t.json"); json.dump(rows, open(p, "w")); return p
    def test_fail_anywhere_fails(self): self.assertEqual(check_gate_table.judge(self.table([{"id": "G3", "mac": ["PASS", "x"], "win": ["FAIL", "해시"]}]))[0], 1)
    def test_unmeasured_is_not_a_failure(self): self.assertEqual(check_gate_table.judge(self.table([{"id": "G9", "common": ["미측정", "x"]}, {"id": "G1", "win": ["PASS", "x"]}]))[0], 0)
    def test_unreadable_table_fails(self): self.assertEqual(check_gate_table.judge("/nonexistent/t.json")[0], 1)
    def test_official1_table_is_caught(self):   # 정식 1회차 실제 표(윈 G3·G4 FAIL)가 실패로 잡힌다 — 증거가 있을 때만
        f = OFFICIAL1 / "rc-gate-table-37138057562/gate-result.json"
        if f.is_file(): rc, msg = check_gate_table.judge(str(f)); self.assertEqual(rc, 1); self.assertIn("G3 win", msg); self.assertIn("G4 win", msg)

class EvidenceMix(unittest.TestCase):
    def write(self, d, rel, data): p = pathlib.Path(d, rel); p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(data); return p
    def doc(self, d, rel, raws): self.write(d, rel, json.dumps({"raw": [{"path": n, "sha256": hashlib.sha256(b).hexdigest()} for n, b in raws]}).encode())
    def test_consistent_passes(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "win/hook_master.out", b"A"); self.doc(d, "win/G3_inject.json", [("hook_master.out", b"A")]); self.assertEqual(check_evidence_mix.judge(d)[0], 0)
    def test_mixed_hash_fails(self):   # win-gates 의 hook 파일 + 다른 잡의 문서 = 정식 1회차 증상
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "win/hook_master.out", b"gates"); self.doc(d, "win/G3_inject.json", [("hook_master.out", b"nonhome")])
            rc, msg = check_evidence_mix.judge(d); self.assertEqual(rc, 1); self.assertIn("해시 불일치", msg)
    def test_identity_from_another_job_is_caught(self):
        with tempfile.TemporaryDirectory() as d:
            self.write(d, "identity.json", json.dumps({"profile": "C:\\Users\\waverc2"}).encode())
            self.write(d, "win/G4_status.json", json.dumps({"surfaces": [{"role": "master", "cwd": "C:\\Users\\waverc1"}]}).encode())
            rc, msg = check_evidence_mix.judge(d); self.assertEqual(rc, 1); self.assertIn("identity.json", msg)
            self.write(d, "identity.json", json.dumps({"profile": "c:\\users\\waverc1\\"}).encode()); self.assertEqual(check_evidence_mix.judge(d)[0], 0)
    def test_foreign_folders_fail(self):
        for sub in ("win/noboot", "mac/noboot", "win/nonhome"):
            with tempfile.TemporaryDirectory() as d:
                self.write(d, sub + "/x", b"x"); self.assertEqual(check_evidence_mix.judge(d)[0], 1, sub)
    def test_official1_all_merged_is_caught_and_the_six_set_is_clean(self):
        if not OFFICIAL1.is_dir(): self.skipTest("증거 없음")
        import shutil
        def merge(names):
            m = tempfile.mkdtemp()
            for n in names: shutil.copytree(OFFICIAL1 / ("rc-evidence-%s-37138057562" % n), m, dirs_exist_ok=True)
            return m
        mixed = merge(["mac", "mac-g5", "mac-noboot", "win-ctrlc", "win-gates", "win-kr", "win-noboot", "win-nonhome", "win-upgrade", "freeze"])
        shutil.copy2(OFFICIAL1 / "rc-evidence-win-gates-37138057562/win/hook_master.out", mixed + "/win/hook_master.out")   # 실제 CI 의 섞임 순서
        self.assertEqual(check_evidence_mix.judge(mixed)[0], 1)
        self.assertEqual(check_evidence_mix.judge(merge(["mac", "mac-g5", "freeze", "win-upgrade", "win-kr", "win-gates"]))[0], 0)   # 워크플로의 내려받기 순서(win-gates 마지막)

if __name__ == "__main__": unittest.main()
