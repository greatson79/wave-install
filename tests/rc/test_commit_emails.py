"""격리된 실제 git 저장소로 작성자/커미터 검사를 실행한다. 응답 mock 없음."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parent))
import check_commit_emails as check
GIT='/opt/homebrew/bin/git' if Path('/opt/homebrew/bin/git').is_file() else shutil.which('git')
GOOD='greatson79@gmail.com'

class Emails(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.repo=self.root/'repo';self.repo.mkdir()
        self.env=dict(os.environ, HOME=str(self.root), GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull)
        self.git('init','-q'); self.base=self.commit('old@example.invalid','old@example.invalid')
    def git(self,*args,env=None):
        return subprocess.check_output([GIT,'-C',str(self.repo),*args],env=env or self.env,text=True).strip()
    def commit(self,author=GOOD,committer=GOOD):
        env=dict(self.env,GIT_AUTHOR_NAME='RC test',GIT_COMMITTER_NAME='RC test',GIT_AUTHOR_EMAIL=author,GIT_COMMITTER_EMAIL=committer)
        self.git('-c','commit.gpgsign=false','commit','--allow-empty','-qm','recorded test commit',env=env)
        return self.git('rev-parse','HEAD')
    def judge(self,head):return check.judge(self.repo,self.base,head,git=GIT,env=self.env)
    def test_legacy_commit_excluded(self):self.assertEqual(self.judge(self.base)[0],0)
    def test_ancestor_input_fails(self):
        old=self.base;self.base=self.commit()
        self.assertEqual(self.judge(old)[0],1)
    def test_unrelated_branch_fails(self):
        self.git('checkout','--orphan','unrelated')
        self.assertEqual(self.judge(self.commit())[0],1)
    def test_zero_count_is_not_labelled_pass(self):
        rc,report=self.judge(self.base)
        self.assertEqual(rc,0);self.assertIn('검사 0건',report);self.assertNotIn('PASS',report)
    def test_new_correct_emails_pass(self):self.assertEqual(self.judge(self.commit())[0],0)
    def test_wrong_author_fails(self):self.assertEqual(self.judge(self.commit('wrong@example.invalid'))[0],1)
    def test_wrong_committer_fails(self):self.assertEqual(self.judge(self.commit(committer='wrong@example.invalid'))[0],1)
    def test_every_commit_not_only_tip_is_checked(self):
        self.commit('wrong@example.invalid');self.assertEqual(self.judge(self.commit())[0],1)
    def test_missing_baseline_fails_closed(self):self.assertEqual(check.judge(self.repo,'missing',self.base,git=GIT,env=self.env)[0],1)
    def test_empty_email_fails(self):self.assertEqual(self.judge(self.commit(''))[0],1)
    def test_report_contains_real_sha_and_both_emails(self):
        sha=self.commit();rc,report=self.judge(sha)
        self.assertIn(sha,report);self.assertEqual(report.count(GOOD),2)

if __name__=='__main__':unittest.main()
