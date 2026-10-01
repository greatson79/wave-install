#!/usr/bin/env python3
"""v0.2 한 줄 설치 회귀: tarball 자기획득 · S01 설치/업데이트 · S02 로그인 · S03 SHA256+codesign.
네트워크·실 ~/.claude 없이 격리 HOME + 가짜 claude/curl/hdiutil/codesign 스텁만 쓴다."""
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "bootstrap.sh"
SYSTEM_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Sandbox:
    def __init__(self, test):
        self.tmp = Path(tempfile.mkdtemp(prefix="wave-v02-test-"))
        test.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.stubs = self.tmp / "stubs"
        self.fake = self.tmp / "fake"
        for d in (self.home, self.stubs, self.fake):
            d.mkdir()
        self.env = dict(os.environ, HOME=str(self.home), WAVE_HOME=str(self.home / ".wave"),
                        PATH=f"{self.stubs}:{SYSTEM_PATH}", FAKE=str(self.fake))
        for k in ("WAVE_INSTALL_TARBALL_URL", "WAVE_INSTALL_TARBALL_SHA256"):
            self.env.pop(k, None)

    def stub(self, name, body):
        p = self.stubs / name
        p.write_text("#!/bin/bash\n" + body)
        p.chmod(0o755)

    def lib(self):
        src = BOOT.read_text()
        marker = '\nmain "$@"\n'
        assert src.count(marker) == 1
        p = self.tmp / "lib.sh"
        p.write_text(src.rsplit(marker, 1)[0] + "\n")
        return p

    def call(self, script, **extra):
        env = dict(self.env, **extra)
        return subprocess.run(["bash", "-c", 'source "$1"; STEPS_FILE="$2"; ' + script, "t", str(self.lib()),
                               str(ROOT / "steps.json")], env=env, text=True, capture_output=True)


class TarballSelfFetch(unittest.TestCase):
    def make_tarball(self, sb):
        top = sb.tmp / "wave-install-0.2.0"
        (top / "wave-pack").mkdir(parents=True)
        for name in ("bootstrap.sh", "steps.json", "install-state.json"):
            shutil.copy(ROOT / name, top / name)
        tgz = sb.tmp / "wave-install-0.2.0.tar.gz"
        with tarfile.open(tgz, "w:gz") as t:
            t.add(top, arcname="wave-install-0.2.0")
        return tgz

    def run_alone(self, sb, **extra):
        alone = sb.home / "install-wave.sh"  # curl 한 줄이 받는 파일 하나만 있는 상태
        shutil.copy(BOOT, alone)
        return subprocess.run(["bash", str(alone), "--dry-run"], env=dict(sb.env, **extra), text=True, capture_output=True)

    def test_downloads_verifies_extracts_and_reruns(self):
        sb = Sandbox(self)
        tgz = self.make_tarball(sb)
        r = self.run_alone(sb, WAVE_INSTALL_TARBALL_URL=f"file://{tgz}", WAVE_INSTALL_TARBALL_SHA256=sha(tgz))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(str(sb.home / ".wave/src/pack/steps.json"), r.stderr)  # 풀린 폴더에서 재실행됨
        self.assertTrue((sb.home / ".wave/src/pack/wave-pack").is_dir())

    def test_sha_mismatch_stops_before_extract(self):
        sb = Sandbox(self)
        tgz = self.make_tarball(sb)
        r = self.run_alone(sb, WAVE_INSTALL_TARBALL_URL=f"file://{tgz}", WAVE_INSTALL_TARBALL_SHA256="0" * 64)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SHA256 불일치", r.stderr)
        self.assertFalse((sb.home / ".wave/src/pack").exists())

    def test_unfilled_placeholder_stops(self):
        sb = Sandbox(self)
        r = self.run_alone(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("릴리스 때 채워지지 않음", r.stderr)

    def test_unsafe_path_in_tarball_rejected(self):
        sb = Sandbox(self)
        evil = sb.tmp / "evil.tar.gz"
        (sb.tmp / "x").write_text("x")
        with tarfile.open(evil, "w:gz") as t:
            t.add(sb.tmp / "x", arcname="top/../escape")
        r = self.run_alone(sb, WAVE_INSTALL_TARBALL_URL=f"file://{evil}", WAVE_INSTALL_TARBALL_SHA256=sha(evil))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("위험한 경로", r.stderr)


FAKE_CLAUDE = r'''
case "$1" in
  --version) cat "$FAKE/ver" 2>/dev/null || exit 1 ;;
  update) echo "$FAKE_UPDATE_TO" > "$FAKE/ver"; echo update >> "$FAKE/calls" ;;
  auth) case "$2" in
    status) [ -f "$FAKE/loggedin" ] ;;
    login) echo login >> "$FAKE/calls"; [ "$FAKE_LOGIN_OK" = 1 ] && touch "$FAKE/loggedin"; exit 0 ;;
  esac ;;
esac
'''


class ClaudeSteps(unittest.TestCase):
    def test_s01_missing_claude_is_installed_via_official_script(self):
        sb = Sandbox(self)
        installer = sb.tmp / "install.sh"
        installer.write_text(f'mkdir -p "$HOME/.local/bin"\ncp "{sb.tmp}/claude-real" "$HOME/.local/bin/claude"\n')
        (sb.tmp / "claude-real").write_text("#!/bin/bash\n" + FAKE_CLAUDE)
        (sb.tmp / "claude-real").chmod(0o755)
        (sb.fake / "ver").write_text("2.1.300\n")
        r = sb.call("step_s01; echo \"OBS=$STEP_OBSERVED\"", WAVE_CLAUDE_INSTALL_URL=f"file://{installer}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"installed": true', r.stdout)

    def test_s01_install_falls_back_to_direct_download(self):
        sb = Sandbox(self)
        base = sb.tmp / "dl"
        (base / "9.9.9" / "darwin-arm64").mkdir(parents=True)
        (base / "9.9.9" / "darwin-x64").mkdir(parents=True)
        (base / "stable").write_text("9.9.9")
        binary = "#!/bin/bash\n" + 'mkdir -p "$HOME/.local/bin"; cat > "$HOME/.local/bin/claude" <<\'EOF\'\n#!/bin/bash\n' + FAKE_CLAUDE + "EOF\nchmod +x \"$HOME/.local/bin/claude\"\n"
        for plat in ("darwin-arm64", "darwin-x64"):
            (base / "9.9.9" / plat / "claude").write_text(binary)
        digest = hashlib.sha256(binary.encode()).hexdigest()
        (base / "9.9.9" / "manifest.json").write_text(json.dumps(
            {"platforms": {p: {"checksum": digest} for p in ("darwin-arm64", "darwin-x64")}}))
        (sb.tmp / "bad.sh").write_text("exit 1\n")  # 공식 install.sh 실패
        (sb.fake / "ver").write_text("2.1.300\n")
        r = sb.call("step_s01", WAVE_CLAUDE_INSTALL_URL=f"file://{sb.tmp}/bad.sh",
                    WAVE_CLAUDE_DIRECT_BASE_URL=f"file://{base}")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("직접 받습니다", r.stderr)

    def _installed_claude(self, sb, version):
        sb.stub("claude", FAKE_CLAUDE)
        (sb.fake / "ver").write_text(version + "\n")

    def test_s01_old_version_runs_update_then_passes(self):
        sb = Sandbox(self)
        self._installed_claude(sb, "2.1.158")
        r = sb.call("step_s01; echo \"OBS=$STEP_OBSERVED\"", FAKE_UPDATE_TO="2.1.300")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((sb.fake / "calls").read_text().split(), ["update"])
        self.assertIn('"updated": true', r.stdout)

    def test_s01_update_that_does_not_help_stops(self):
        sb = Sandbox(self)
        self._installed_claude(sb, "2.1.158")
        r = sb.call("step_s01", FAKE_UPDATE_TO="2.1.158")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("claude update 후에도", r.stderr)

    def test_s01_current_version_does_not_update(self):
        sb = Sandbox(self)
        self._installed_claude(sb, "2.1.278")
        r = sb.call("step_s01")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((sb.fake / "calls").exists())

    def test_s02_not_logged_in_runs_login_then_rechecks(self):
        sb = Sandbox(self)
        sb.stub("claude", FAKE_CLAUDE)
        r = sb.call("step_s02", FAKE_LOGIN_OK="1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((sb.fake / "calls").read_text().split(), ["login"])
        self.assertTrue((sb.home / ".wave/auth/claude-authenticated").exists())

    def test_s02_login_not_completed_fails(self):
        sb = Sandbox(self)
        sb.stub("claude", FAKE_CLAUDE)
        r = sb.call("step_s02", FAKE_LOGIN_OK="0")
        self.assertNotEqual(r.returncode, 0)

    def test_s02_already_logged_in_skips_login(self):
        sb = Sandbox(self)
        sb.stub("claude", FAKE_CLAUDE)
        (sb.fake / "loggedin").write_text("")
        r = sb.call("step_s02")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse((sb.fake / "calls").exists())


class DownloadVerify(unittest.TestCase):
    def setup_download(self, sb, dmg_bytes=b"fake-dmg", pinned=None):
        dmg = sb.tmp / "asset.dmg"
        dmg.write_bytes(dmg_bytes)
        steps = json.loads((ROOT / "steps.json").read_text())
        for plat in ("macos_arm64", "macos_x64"):
            steps["release"]["sha256"][plat] = pinned or sha(dmg)
        steps["release"]["cdhash"] = {"macos_arm64": None, "macos_x64": None}  # 기본은 CDHash 미대조
        sb.steps = sb.tmp / "steps.json"
        sb.steps.write_text(json.dumps(steps))
        sb.stub("curl", 'out=""; while [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done\ncp "$FAKE/asset.dmg" "$out"\n')
        shutil.copy(dmg, sb.fake / "asset.dmg")
        sb.stub("hdiutil", 'if [ "$1" = attach ]; then while [ $# -gt 0 ]; do [ "$1" = -mountpoint ] && mp="$2"; shift; done; mkdir -p "$mp/Wave Terminal.app"; fi\n')
        sb.stub("codesign", 'case "$1" in --verify) exit "${FAKE_CODESIGN_RC:-0}" ;; -dvvv) echo "CDHash=abc123" >&2 ;; esac\n')
        sb.stub("uname", '[ "$1" = -m ] && echo arm64 || /usr/bin/uname "$@"\n')

    def run_s03(self, sb, **extra):
        return subprocess.run(["bash", "-c", 'source "$1"; STEPS_FILE="$2"; step_s03; echo "OBS=$STEP_OBSERVED"', "t",
                               str(sb.lib()), str(sb.steps)], env=dict(sb.env, **extra), text=True, capture_output=True)

    def test_pass_with_pinned_sha_and_codesign_without_minisign(self):
        sb = Sandbox(self)
        self.setup_download(sb)
        self.assertFalse(shutil.which("minisign", path=str(sb.stubs)))
        r = self.run_s03(sb)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"codesign_verified": true', r.stdout)

    def test_sha_mismatch_fails(self):
        sb = Sandbox(self)
        self.setup_download(sb, pinned="1" * 64)
        r = self.run_s03(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("SHA256 불일치", r.stderr)

    def test_codesign_failure_fails(self):
        sb = Sandbox(self)
        self.setup_download(sb)
        r = self.run_s03(sb, FAKE_CODESIGN_RC="1")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("codesign", r.stderr)

    def test_cdhash_pin_checked_when_set(self):
        sb = Sandbox(self)
        self.setup_download(sb)
        steps = json.loads(sb.steps.read_text())
        steps["release"]["cdhash"] = {"macos_arm64": "deadbeef", "macos_x64": "deadbeef"}
        sb.steps.write_text(json.dumps(steps))
        r = self.run_s03(sb)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("CDHash 불일치", r.stderr)
        steps["release"]["cdhash"] = {"macos_arm64": "abc123", "macos_x64": "abc123"}
        sb.steps.write_text(json.dumps(steps))
        self.assertEqual(self.run_s03(sb).returncode, 0)


if __name__ == "__main__":
    unittest.main()
