#!/usr/bin/env python3
"""동기화는 격리 worktree만 수정하며 두 대상 검사 후 복사한다."""
import json
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/sync-get.sh"
FILES = {"index.html", "app.js", "styles.css", "steps.json", "steps.schema.json"}

class SyncGetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.tmp.name).resolve()
        self.targets = []
        for name, remote in [("homepage", "wave-homepage"), ("blog", "kylechoi-blog")]:
            repo = self.root / (name + "-repo")
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "README.md").write_text("fixture\n")
            def git(*args):
                return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)
            git("add", "README.md")
            git("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "fixture")
            git("remote", "add", "origin", "https://github.com/greatson79/" + remote + ".git")
            git("update-ref", "refs/remotes/origin/main", "HEAD")
            target = self.root / (name + "-worktree")
            git("worktree", "add", "--detach", str(target), "origin/main")
            self.targets.append(target)

    def tearDown(self):
        self.tmp.cleanup()

    def run_sync(self, targets=None):
        return subprocess.run(["bash", str(SCRIPT), "v0.1.3", *map(str, targets or self.targets)], capture_output=True, text=True)

    def test_copies_tagged_files_with_subpath_safe_urls(self):
        result = self.run_sync()
        self.assertEqual(result.returncode, 0, result.stderr)
        for target in self.targets:
            folder = target / "public/get"
            self.assertEqual({p.name for p in folder.iterdir()}, FILES)
            html = (folder / "index.html").read_text()
            self.assertEqual(html.count('<base href="/get/">'), 1)
            self.assertIn('content="v0.1.3"', html)
            self.assertIn('LIGHT / v0.1.3', html)
            app = (folder / "app.js").read_text()
            self.assertNotIn('../steps.json', app)
            self.assertIn('["./steps.json"]', app)
            self.assertEqual(len(json.loads((folder / "steps.json").read_text())["steps"]), 10)
        self.assertEqual((self.targets[0] / "public/get/index.html").read_bytes(), (self.targets[1] / "public/get/index.html").read_bytes())

    def test_dirty_second_target_is_rejected_before_first_write(self):
        (self.targets[1] / "draft.txt").write_text("not approved")
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DIRTY_WORKTREE", result.stderr)
        self.assertFalse((self.targets[0] / "public").exists())

    def commit_second_fixture(self):
        target = self.targets[1]
        for args in [("add", "."), ("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "commit", "-qm", "shape fixture"), ("update-ref", "refs/remotes/origin/main", "HEAD")]:
            subprocess.run(["git", "-C", str(target), *args], check=True, capture_output=True)

    def test_file_instead_of_public_is_rejected_before_first_write(self):
        (self.targets[1] / "public").write_text("tracked file")
        self.commit_second_fixture()
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.targets[0] / "public").exists())
        self.assertIn("DESTINATION_TYPE_MISMATCH", result.stderr)

    def test_directory_instead_of_asset_is_rejected_before_first_write(self):
        folder = self.targets[1] / "public/get/index.html"
        folder.mkdir(parents=True)
        (folder / "tracked.txt").write_text("tracked directory")
        self.commit_second_fixture()
        result = self.run_sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.targets[0] / "public").exists())
        self.assertIn("DESTINATION_TYPE_MISMATCH", result.stderr)

    def test_original_checkout_is_rejected(self):
        result = self.run_sync([self.root / "homepage-repo", self.targets[1]])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("ISOLATED_WORKTREE_REQUIRED", result.stderr)
        self.assertFalse((self.targets[1] / "public").exists())

if __name__ == "__main__":
    unittest.main(verbosity=2)
