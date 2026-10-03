# 실제 Ctrl+C(CTRL_C_EVENT)를 다른 프로세스의 콘솔에 보낸다 — 이 프로세스는 자기 콘솔을 버리고 대상 콘솔에 붙어 보낸 뒤 자기는 Ctrl+C 를 무시한다.
#  ctrlc_send.ps1 -TargetPid <콘솔 소유 프로세스> -Out <결과 파일>
param([uint32]$TargetPid, [string]$Out)
Add-Type -Namespace W -Name K -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool FreeConsole();
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool AttachConsole(uint p);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool SetConsoleCtrlHandler(IntPtr h, bool a);
[DllImport("kernel32.dll", SetLastError=true)] public static extern bool GenerateConsoleCtrlEvent(uint e, uint g);
'@
$r = [ordered]@{ target_pid = $TargetPid }
$r.free = [W.K]::FreeConsole(); $r.attach = [W.K]::AttachConsole($TargetPid); $r.attach_err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
$null = [W.K]::SetConsoleCtrlHandler([IntPtr]::Zero, $true)
$r.sent = [W.K]::GenerateConsoleCtrlEvent(0, 0); $r.sent_err = [Runtime.InteropServices.Marshal]::GetLastWin32Error()
Start-Sleep 2
$r | ConvertTo-Json | Set-Content -Path $Out -Encoding ASCII
