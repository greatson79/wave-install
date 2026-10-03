"""좌석 cwd 단정 — 실행: python3 -m unittest tests.rc.test_seat_cwd"""
import json, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import check_seat_cwd

HOME = "C:\\Users\\waverc1"

def seat(role, cwd=HOME, exited=False): return {"role": role, "cwd": cwd, "exited": exited}

class SeatCwd(unittest.TestCase):
    def run_case(self, surfaces, home=HOME, ident=False):
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "s.json"); json.dump({"surfaces": surfaces}, open(f, "w"))
            if ident: h = os.path.join(d, "identity.json"); open(h, "w", encoding="utf-8-sig").write(json.dumps({"profile": home}))
            else: h = home
            return check_seat_cwd.judge(h, [f])[0]
    def three(self, **kw): return [seat("master"), seat("cso"), seat("worker-1"), {"role": None, "cwd": "X:\\other", "exited": False}]
    def test_all_home_passes_and_identity_file_works(self):
        self.assertEqual(self.run_case(self.three()), 0); self.assertEqual(self.run_case(self.three(), ident=True), 0)
    def test_trailing_slash_and_case_are_not_a_difference(self): self.assertEqual(self.run_case([seat("master", HOME.lower() + "\\"), seat("cso"), seat("worker")]), 0)
    def test_any_seat_outside_home_fails(self): self.assertEqual(self.run_case([seat("master"), seat("cso", "D:\\a\\ev"), seat("worker")]), 1)
    def test_missing_role_or_empty_fails(self): self.assertEqual(self.run_case([seat("master"), seat("cso")]), 1); self.assertEqual(self.run_case([]), 1)
    def test_exited_seats_do_not_count(self): self.assertEqual(self.run_case([seat("master"), seat("cso"), seat("worker", exited=True)]), 1)
    def test_missing_evidence_fails(self): self.assertEqual(check_seat_cwd.judge(HOME, ["/nonexistent/x.json"])[0], 1)

if __name__ == "__main__": unittest.main()
