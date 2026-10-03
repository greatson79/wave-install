/* 시험용 합성 claude 의 맥 런처 — 처음부터 끝까지 프로세스 이름이 "claude" 여야 한다.
 * 이유(16차 확정): cysd 워치독은 sysinfo 0.33.1 refresh_processes() 로 프로세스 *이름*만 보고, 이름은 프로세스를 처음 본 순간 한 번만 기록된다.
 * 파이썬 스크립트가 도중에 claude 로 exec 하면 처음 본 이름(Python)이 굳어 agent_alive 가 영영 켜지지 않는다(cso 만 반복 실패한 근인).
 * 빌드: cc -O0 -DLOGIC='"/path/logic.py"' -o claude claude_launcher.c */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
  if (argc > 1 && !strcmp(argv[1], "--version")) { puts("2.1.300 (Claude Code)"); return 0; }
  if (argc > 1 && (!strcmp(argv[1], "auth") || !strcmp(argv[1], "update"))) return 0;
  char cmd[4096]; snprintf(cmd, sizeof cmd, "python3 \"%s\" --logic-only", LOGIC);
  (void)system(cmd);                 /* 훅 실행·마스터 부트·진단 — 끝나면 돌아온다 */
  fputs("\n\xe2\x9d\xaf \n", stdout); fflush(stdout);   /* agents.json ready_marker ❯ */
  char b[4096];
  for (;;) { if (read(0, b, sizeof b) <= 0) sleep(1); }  /* 주입되는 지침을 비워 준다 */
}
