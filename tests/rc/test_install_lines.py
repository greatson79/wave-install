"""설치 한 줄은 기계 계약(scripts/ci/install-lines.json)에서만 읽는다 — README 를 바꿔도 러너는 안 깨지고, 계약이 어긋나면 실패한다.
시험 서버가 /mac·/win 을 릴리스 파일로 307 넘기는 모양(게시 서버와 동일)도 실제 https 로 확인한다. 실행: python3 -m unittest tests.rc.test_install_lines"""
import json, os, pathlib, shutil, socket, subprocess, sys, tempfile, time, unittest
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import install_lines

BASE = "https://127.0.0.1:8443/"
MAC = "curl -fsSL https://waveainetworks.com/mac | bash"
WIN = "irm https://waveainetworks.com/win | iex"


def tree(contract=None, readme="아무 문구\n"):
    d = pathlib.Path(tempfile.mkdtemp()); (d / "scripts/ci").mkdir(parents=True)
    c = json.loads((ROOT / install_lines.CONTRACT).read_text(encoding="utf-8")); c.update(contract or {})
    (d / install_lines.CONTRACT).write_text(json.dumps(c), encoding="utf-8"); (d / "README.md").write_text(readme, encoding="utf-8")
    return d


class Mapping(unittest.TestCase):
    def test_contract_has_the_two_student_lines(self):
        self.assertEqual(install_lines.contract_line(ROOT, "mac"), MAC)
        self.assertEqual(install_lines.contract_line(ROOT, "win"), WIN)

    def test_rc_line_differs_from_contract_only_by_address(self):
        self.assertEqual(install_lines.rc_one_line(ROOT, "mac", BASE), "curl -fsSL https://127.0.0.1:8443/mac | bash")
        self.assertEqual(install_lines.rc_one_line(ROOT, "win", BASE), "irm https://127.0.0.1:8443/win | iex")

    def test_rewriting_readme_does_not_change_the_runner_line(self):  # 변이: README 설치 절을 임의 문구로
        d = tree(readme="## 설치\n\n아무 말이나: `echo hello`\n")
        self.assertEqual(install_lines.contract_line(d, "mac"), MAC); self.assertEqual(install_lines.contract_line(d, "win"), WIN)

    def test_contract_drift_fails(self):
        for k, bad in (("mac", "curl -fsSL https://example.com/mac | bash"), ("mac", "wget https://waveainetworks.com/mac"),
                       ("win", "iex https://waveainetworks.com/win"), ("win", "irm https://waveainetworks.com/win | iex".replace("waveainetworks", "other")), ("win", None)):
            with self.assertRaises(SystemExit, msg=(k, bad)):
                install_lines.contract_line(tree({k: bad}), k)


@unittest.skipUnless(shutil.which("openssl") and shutil.which("curl"), "openssl/curl 없음")
class ServerRedirect(unittest.TestCase):
    def test_short_paths_redirect_to_release_files_over_https(self):
        with tempfile.TemporaryDirectory() as d:
            rel = pathlib.Path(d, "rel"); rel.mkdir()
            (rel / "bootstrap.sh").write_text("echo BOOTSTRAP_RAN\n"); (rel / "win-start.ps1").write_text("'WIN'\n")
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", d + "/k.pem", "-out", d + "/c.pem", "-days", "1", "-subj", "/CN=127.0.0.1",
                            "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
            s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
            srv = subprocess.Popen([sys.executable, str(HERE / "serve_https.py"), str(rel), str(port), d + "/c.pem", d + "/k.pem"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
                    except OSError: time.sleep(0.1)
                base = "https://127.0.0.1:%d/" % port
                r = subprocess.run(["bash", "-c", install_lines.rc_one_line(ROOT, "mac", base)], capture_output=True, text=True, env=dict(os.environ, CURL_CA_BUNDLE=d + "/c.pem"), timeout=60)
                self.assertEqual((r.returncode, r.stdout.strip()), (0, "BOOTSTRAP_RAN"), r.stderr)
                r = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code} %{redirect_url}", "--cacert", d + "/c.pem", base + "win"], capture_output=True, text=True, timeout=30)
                self.assertEqual(r.stdout, "307 " + base + "win-start.ps1")
            finally:
                srv.terminate(); srv.wait(10)


if __name__ == "__main__":
    unittest.main()
