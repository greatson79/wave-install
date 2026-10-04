"""RC 드라이버가 수강생 실제 명령을 따라가는지 고정한다(신호 3회차 실패 2건의 RED→GREEN).
 맥 G6: 짧은 한 줄은 install-wave.sh 를 남기지 않는다 → 옛 재설치 명령(bash $HOME/install-wave.sh --reinstall)은 127.
        게시된 재설치 명령(steps.json reinstall.command)을 시험 서버 주소로 바꿔 치면 정상 동작해야 한다.
 윈 G5: 옛 v0.2.3 설치 줄을 README 에서 찾던 드라이버는 줄이 없어 빈 명령을 실행했다 → 고정 문자열로.
실행: python3 -m unittest tests.rc.test_driver_lines"""
import json, os, pathlib, re, shutil, socket, subprocess, sys, tempfile, time, unittest
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import install_lines


def assemble(osn, base, tmp):
    asset = tmp / ("Wave Terminal_0.2.0_aarch64.dmg" if osn == "mac" else "Wave Terminal_0.2.0_x64-setup.exe"); asset.write_bytes(b"x")
    out = tmp / ("rel-" + osn)
    r = subprocess.run([sys.executable, str(HERE / "rc_release.py"), "--os", osn, "--asset", str(asset), "--base", base, "--out", str(out), "--cdhash", "abc", "--repo", str(ROOT)],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stderr
    return out, json.loads((out / "rc-release.json").read_text(encoding="utf-8"))


class Assembly(unittest.TestCase):
    def test_reinstall_line_is_the_published_command_with_local_address(self):
        steps = json.loads((ROOT / "steps.json").read_text(encoding="utf-8"))["reinstall"]["command"]
        with tempfile.TemporaryDirectory() as d:
            for osn, key in (("mac", "macos"), ("win", "windows")):
                _, rc = assemble(osn, "https://127.0.0.1:8443/", pathlib.Path(d))
                want = re.sub(r"https://github\.com/greatson79/wave-install/releases/download/[^/\"' ]+/", "https://127.0.0.1:8443/", steps[key])
                self.assertEqual(rc["reinstall_line"], want)
                self.assertIn("127.0.0.1:8443", rc["reinstall_line"]); self.assertNotIn("github.com", rc["reinstall_line"])
        self.assertIn("--reinstall", steps["macos"]); self.assertIn("-Reinstall", steps["windows"])


@unittest.skipUnless(shutil.which("openssl") and shutil.which("curl"), "openssl/curl 없음")
class MacG6(unittest.TestCase):
    def test_old_reinstall_command_is_127_and_published_one_works(self):
        with tempfile.TemporaryDirectory() as d:
            tmp = pathlib.Path(d)
            s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close()
            base = "https://127.0.0.1:%d/" % port
            rel, rc = assemble("mac", base, tmp)
            (rel / "bootstrap.sh").write_text('#!/bin/bash\necho "ARGS:$*" >> "$HOME/ran.txt"\n')  # 설치기 자리에 인자 기록 stub(진짜 설치기는 실행하지 않는다)
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-keyout", d + "/k.pem", "-out", d + "/c.pem", "-days", "1", "-subj", "/CN=127.0.0.1",
                            "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True)
            srv = subprocess.Popen([sys.executable, str(HERE / "serve_https.py"), str(rel), str(port), d + "/c.pem", d + "/k.pem"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for _ in range(50):
                    try: socket.create_connection(("127.0.0.1", port), 0.2).close(); break
                    except OSError: time.sleep(0.1)
                home = tmp / "home"; home.mkdir()
                env = dict(os.environ, HOME=str(home), CURL_CA_BUNDLE=d + "/c.pem")
                run = lambda line: subprocess.run(["bash", "-c", 'cd "$HOME" && ' + line], capture_output=True, text=True, env=env, timeout=60)
                first = run(rc["one_line"])  # 짧은 한 줄 첫 설치
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertFalse((home / "install-wave.sh").exists())  # 짧은 한 줄은 파일을 남기지 않는다
                red = run('bash "$HOME/install-wave.sh" --reinstall')  # 신호 3회차의 옛 G6 명령
                self.assertEqual(red.returncode, 127); self.assertIn("No such file", red.stderr)
                green = run(rc["reinstall_line"])  # 게시된 재설치 명령
                self.assertEqual(green.returncode, 0, green.stderr)
                self.assertTrue((home / "install-wave.sh").exists())
                self.assertIn("ARGS:--reinstall", (home / "ran.txt").read_text())
            finally:
                srv.terminate(); srv.wait(10)


class Drivers(unittest.TestCase):
    def test_no_driver_reads_readme_prose(self):
        for f in list(HERE.glob("*.sh")) + list(HERE.glob("*.ps1")):
            self.assertNotIn("README.md", f.read_text(encoding="utf-8-sig"), f.name)

    def test_mac_run_g6_uses_published_reinstall_not_a_saved_file(self):
        t = (HERE / "mac-run.sh").read_text(encoding="utf-8")
        self.assertIn('["reinstall_line"]', t); self.assertIn("$REINSTALL", t); self.assertNotIn("install-wave.sh", t)

    def test_win_g5_old_line_is_the_fixed_v023_command(self):
        t = (HERE / "win-child.ps1").read_text(encoding="utf-8-sig")
        m = re.search(r"(?m)^    \$old = '(.*)'\r?$", t); self.assertTrue(m)
        old = m.group(1).replace("''", "'")
        self.assertTrue(old.startswith("powershell -NoProfile")); self.assertIn("/releases/download/v0.2.3/bootstrap.ps1", old)
        self.assertIn("install-wave.ps1", old); self.assertNotIn("-Reinstall", old)

    @unittest.skipUnless(os.path.exists(os.environ.get("PWSH", "/tmp/wave-v024-pwsh/pwsh")), "pwsh 없음")
    def test_win_child_parses(self):
        pw = os.environ.get("PWSH", "/tmp/wave-v024-pwsh/pwsh")
        r = subprocess.run([pw, "-NoProfile", "-Command", '$e=$null;$t=$null;[void][System.Management.Automation.Language.Parser]::ParseFile($env:WC,[ref]$t,[ref]$e); $e.Count'], capture_output=True, text=True, env=dict(os.environ, WC=str(HERE / "win-child.ps1")))
        self.assertEqual(r.stdout.strip(), "0", r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
