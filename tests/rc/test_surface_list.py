"""surface.list 원본 수집 — 응답 원문을 그대로 저장하고, 실패해도 잡을 죽이지 않는다. 실행: python3 -m unittest tests.rc.test_surface_list"""
import json, os, socket, subprocess, sys, tempfile, threading, unittest
TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "surface_list.py")

class SurfaceList(unittest.TestCase):
    def run_tool(self, sock, out):
        return subprocess.run([sys.executable, TOOL, out], env=dict(os.environ, CYS_SOCKET=sock), capture_output=True, text=True, timeout=30)
    def test_saves_the_raw_response_line_after_sending_surface_list(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as d:
            sock, out, seen = os.path.join(d, "s"), os.path.join(d, "o.json"), []
            srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); srv.bind(sock); srv.listen(1)
            raw = b'{"id":1,"ok":true,"result":{"surfaces":[{"role":"master","launch_complete":true}]}}\n'
            def serve():
                c, _ = srv.accept(); seen.append(c.recv(4096)); c.sendall(raw); c.close()
            t = threading.Thread(target=serve); t.start()
            r = self.run_tool(sock, out); t.join(10); srv.close()
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(seen[0]), {"id": 1, "method": "surface.list", "params": {}})
            self.assertEqual(open(out, "rb").read(), raw); self.assertFalse(os.path.exists(out + ".error"))
    def test_failure_never_fails_the_job(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.json"); r = self.run_tool(os.path.join(d, "nope"), out)
            self.assertEqual(r.returncode, 0); self.assertFalse(os.path.exists(out)); self.assertIn("Error", open(out + ".error").read())

if __name__ == "__main__": unittest.main()
