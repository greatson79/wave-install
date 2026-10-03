/* 시험용 합성 claude 의 윈도우 런처 — 프로세스 이름이 처음부터 끝까지 claude.exe 여야 cysd 가 잡는다
 * (맥 판 claude_launcher.c 와 같은 이유: 워치독은 프로세스 *이름*을 처음 본 순간 한 번만 기록. 앱 8e124a4 가 claude.exe 의 .exe 를 인식하도록 고쳤다).
 * 동작: claude.cfg(같은 폴더, UTF-16LE: 1행 python 경로, 2행 로직 스크립트 경로)를 읽어 「python 로직 --logic-only」 를 실행·대기한 뒤
 *       ready 표지 ❯ 를 찍고 stdin 을 비우며 대기한다. 한글·공백 경로를 위해 전부 와이드 API.
 * 빌드(ubuntu): x86_64-w64-mingw32-gcc -O0 -municode -static -o claude.exe claude_launcher_win.c */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

static int read_cfg(const wchar_t *cfg, wchar_t *py, wchar_t *logic, size_t cap) {
  HANDLE f = CreateFileW(cfg, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, 0, NULL);
  if (f == INVALID_HANDLE_VALUE) return 0;
  static wchar_t buf[8192]; DWORD got = 0;
  BOOL ok = ReadFile(f, buf, (sizeof buf) - sizeof(wchar_t), &got, NULL); CloseHandle(f);
  if (!ok) return 0;
  buf[got / sizeof(wchar_t)] = 0;
  wchar_t *p = buf; if (*p == 0xFEFF) p++;
  wchar_t *nl = wcschr(p, L'\n'); if (!nl) return 0;
  *nl = 0; wchar_t *l2 = nl + 1;
  size_t n1 = wcslen(p); while (n1 && (p[n1 - 1] == L'\r')) p[--n1] = 0;
  wchar_t *nl2 = wcschr(l2, L'\n'); if (nl2) *nl2 = 0;
  size_t n2 = wcslen(l2); while (n2 && (l2[n2 - 1] == L'\r')) l2[--n2] = 0;
  if (n1 + 1 > cap || n2 + 1 > cap) return 0;
  wcscpy(py, p); wcscpy(logic, l2); return 1;
}

int wmain(int argc, wchar_t **argv) {
  if (argc > 1 && !wcscmp(argv[1], L"--version")) { puts("2.1.300 (Claude Code)"); return 0; }
  if (argc > 1 && (!wcscmp(argv[1], L"auth") || !wcscmp(argv[1], L"update"))) return 0;
  wchar_t exe[MAX_PATH * 2], cfg[MAX_PATH * 2], py[MAX_PATH * 2], logic[MAX_PATH * 2];
  GetModuleFileNameW(NULL, exe, MAX_PATH * 2);
  wchar_t *slash = wcsrchr(exe, L'\\'); if (slash) *(slash + 1) = 0;
  _snwprintf(cfg, MAX_PATH * 2 - 1, L"%lsclaude.cfg", exe); cfg[MAX_PATH * 2 - 1] = 0;
  /* 맥 런처와 같은 이유: ❯ 를 먼저 찍어 launch-agent 의 준비 확인(최대 60초)을 통과시키고, 로직은 기다리지 않고 따로 돌린다 */
  HANDLE out = GetStdHandle(STD_OUTPUT_HANDLE); DWORD w;
  /* 콘솔(ConPTY)에는 UTF-8 바이트를 WriteFile 로 쓰면 출력 코드페이지(OEM)로 해석돼 ❯ 가 깨진다 — launch-agent 가 표지를 못 봐 master 좌석이 75초 뒤 정리됐다(20차). 콘솔이면 와이드 API 로 쓴다 */
  const wchar_t readyw[] = L"\r\n\x276F \r\n"; const char ready[] = "\r\n\xE2\x9D\xAF \r\n"; DWORD mode;
  if (GetConsoleMode(out, &mode)) WriteConsoleW(out, readyw, (DWORD)wcslen(readyw), &w, NULL);
  else WriteFile(out, ready, (DWORD)(sizeof ready - 1), &w, NULL);
  if (read_cfg(cfg, py, logic, MAX_PATH * 2)) {
    static wchar_t cmd[MAX_PATH * 6];
    _snwprintf(cmd, MAX_PATH * 6 - 1, L"\"%ls\" \"%ls\" --logic-only", py, logic); cmd[MAX_PATH * 6 - 1] = 0;
    STARTUPINFOW si; PROCESS_INFORMATION pi; ZeroMemory(&si, sizeof si); si.cb = sizeof si; ZeroMemory(&pi, sizeof pi);
    if (CreateProcessW(NULL, cmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) { CloseHandle(pi.hProcess); CloseHandle(pi.hThread); }
  }
  HANDLE in = GetStdHandle(STD_INPUT_HANDLE); char b[4096]; DWORD r;
  for (;;) { if (!ReadFile(in, b, sizeof b, &r, NULL) || r == 0) Sleep(1000); }
}
