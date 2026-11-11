param([string]$InstalledCys)
$ErrorActionPreference = 'Stop'
if ($PSVersionTable.PSVersion.Major -ne 5 -or $PSVersionTable.PSVersion.Minor -ne 1) { throw 'Needs Windows PowerShell 5.1' }
$repo = Split-Path $PSScriptRoot -Parent
$tokens = $null; $errors = $null
$ast = [Management.Automation.Language.Parser]::ParseFile((Join-Path $repo 'bootstrap.ps1'), [ref]$tokens, [ref]$errors)
if ($errors.Count) { throw ($errors | Out-String) }
foreach ($name in @('Read-SharedCheckLog', 'Invoke-BoundedCheck', 'Start-WaveDetached')) {
  $fn = @($ast.FindAll({ param($n) $n -is [Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $name }, $true))
  if ($fn.Count -ne 1) { throw "Expected one $name" }
  . ([scriptblock]::Create($fn[0].Extent.Text))
}
$root = Join-Path $env:TEMP ('av proof ' + [guid]::NewGuid().ToString('N'))
$WaveHome = Join-Path $root 'wave'
New-Item -ItemType Directory -Force $WaveHome | Out-Null
$fake = Join-Path $root 'parent probe.exe'
$priorHome = $env:WAVE_HOME
try {
  Add-Type -OutputType ConsoleApplication -OutputAssembly $fake -ReferencedAssemblies System.Management -TypeDefinition @'
using System;
using System.IO;
using System.Diagnostics;
using System.Management;
public static class Probe {
  public static int Main(string[] args) {
    int pid = Process.GetCurrentProcess().Id;
    using (var child = new ManagementObject("Win32_Process.Handle='" + pid + "'")) {
      int parentId = Convert.ToInt32(child["ParentProcessId"]);
      string parentName = "exited";
      try { using (var parent = new ManagementObject("Win32_Process.Handle='" + parentId + "'")) { parentName = (string)parent["Name"]; } }
      catch (ManagementException) {}
      {
        File.WriteAllLines(Environment.GetEnvironmentVariable("AV_PROBE_FILE"), new string[] {
          pid.ToString(), parentId.ToString(), parentName, Environment.CurrentDirectory, String.Join("|", args)
        });
      }
    }
    Console.WriteLine("probe stdout"); Console.Error.WriteLine("probe stderr");
    System.Threading.Thread.Sleep(Environment.GetEnvironmentVariable("AV_PROBE_MODE") == "timeout" ? 10000 : 3000);
    return 3;
  }
}
'@
  $env:AV_PROBE_FILE = Join-Path $root 'probe.txt'
  $env:AV_PROBE_MODE = 'io'
  $r = Invoke-BoundedCheck $fake @('one', '"two words"') 'io' 15000
  if ($r.timed_out -or $r.exit_code -ne 3 -or $r.stdout.Trim() -ne 'probe stdout' -or $r.stderr.Trim() -ne 'probe stderr' -or $r.kill_error) { throw 'G3 exit/stdout/stderr failed' }
  $probe = Get-Content -LiteralPath $env:AV_PROBE_FILE
  if ($probe[2] -ne 'cmd.exe') { throw "G2 expected cmd.exe parent, got $($probe[2])" }
  if ($probe[3] -ne $env:USERPROFILE -or $probe[4] -ne 'one|two words') { throw 'cwd/quoted arguments changed' }
  Write-Host 'PASS G2: live Win32_Process parent is cmd.exe; cwd and quoted arguments preserved'
  Write-Host 'PASS G3: exit 3 and both output streams preserved'

  Remove-Item -LiteralPath $env:AV_PROBE_FILE
  $env:AV_PROBE_MODE = 'timeout'
  $watch = [Diagnostics.Stopwatch]::StartNew()
  $r = Invoke-BoundedCheck $fake @() 'timeout' 2000
  $watch.Stop()
  if (-not $r.timed_out -or $null -ne $r.exit_code -or $r.kill_error -or $watch.ElapsedMilliseconds -gt 6000) { throw 'G3 timeout return/bound failed' }
  $probe = Get-Content -LiteralPath $env:AV_PROBE_FILE
  foreach ($processId in @([int]$probe[0], [int]$probe[1])) {
    if (Get-Process -Id $processId -ErrorAction SilentlyContinue) { throw "G3 orphan process $processId" }
  }
  Write-Host 'PASS G3: 2000ms timeout killed cmd and child tree'

  Remove-Item -LiteralPath $env:AV_PROBE_FILE
  $env:AV_PROBE_MODE = 'io'
  $watch.Restart()
  Start-WaveDetached $fake
  $watch.Stop()
  if ($watch.ElapsedMilliseconds -gt 2000) { throw 'Detached launch waited' }
  $deadline = [Diagnostics.Stopwatch]::StartNew()
  while (-not (Test-Path -LiteralPath $env:AV_PROBE_FILE) -and $deadline.ElapsedMilliseconds -lt 10000) { Start-Sleep -Milliseconds 100 }
  $probe = Get-Content -LiteralPath $env:AV_PROBE_FILE
  if ($probe[3] -ne $env:USERPROFILE) { throw 'Detached cwd changed' }
  Wait-Process -Id ([int]$probe[0]) -Timeout 10 -ErrorAction SilentlyContinue
  Write-Host 'PASS: detached launch returns immediately and keeps user-home cwd'

  if (-not $InstalledCys) { throw 'G2 requires real pinned installed cys.exe' }
  $r = Invoke-BoundedCheck $InstalledCys @('--version') 'real-version' 15000
  if ($r.timed_out -or $r.exit_code -ne 0 -or -not $r.stdout.Trim()) { throw 'G2 real installed cys --version failed' }
  Write-Host "PASS G2: real pinned installed cys --version: $($r.stdout.Trim())"

  $template = [IO.File]::ReadAllText((Join-Path $repo 'win-start.ps1'))
  $hint = '안랩 Safe Transaction(ASTx)·V3·알약: 작업 표시줄에서 ''종료''만으로는 부족할 수 있습니다; 설치하는 동안 해당 보안 프로그램의 예외 등록 또는 잠시 제거 후 같은 명령을 다시 실행하세요; 설치가 끝나면 다시 켜거나 설치하세요.'
  $trapLine = '실패 원문'
  foreach ($case in @(
    @{Name='killed'; Exit=1; Lines=@('[5/10] running'); Hint=$true},
    @{Name='normal-failure'; Exit=1; Lines=@('[5/10] running', $trapLine); Hint=$false},
    @{Name='old-failure'; Exit=1; Lines=@('[4/10] old', $trapLine, '[5/10] running'); Hint=$true},
    @{Name='success'; Exit=0; Lines=@('[5/10] running'); Hint=$false},
    @{Name='alive'; Exit=2; Lines=@('[5/10] running'); Hint=$false},
    @{Name='missing-log'; Exit=1; Lines=@(); Hint=$true}
  )) {
    $env:WAVE_HOME = Join-Path $root $case.Name
    New-Item -ItemType Directory -Force $env:WAVE_HOME | Out-Null
    if ($case.Lines.Count) { [IO.File]::WriteAllLines((Join-Path $env:WAVE_HOME 'install.log'), [string[]]$case.Lines, [Text.UTF8Encoding]::new($false)) }
    $stub = Join-Path $root ($case.Name + '-bootstrap.ps1')
    [IO.File]::WriteAllText($stub, ('exit ' + $case.Exit), [Text.Encoding]::ASCII)
    $sha = (Get-FileHash -LiteralPath $stub -Algorithm SHA256).Hash.ToLowerInvariant()
    $runner = Join-Path $root ($case.Name + '-run.ps1')
    # Stub only the download; win-start launches a real child PowerShell with the pinned fake bootstrap.
    $prefix = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new(); function Invoke-WebRequest { param([switch]`$UseBasicParsing, `$Uri, `$OutFile) Copy-Item -LiteralPath '$stub' -Destination `$OutFile }; try {`n"
    $body = $template.Replace('__WAVE_BOOTSTRAP_SHA256__', $sha)
    [IO.File]::WriteAllText($runner, ($prefix + $body + "`n} catch { Write-Host `$_.Exception.Message; exit 1 }"), [Text.UTF8Encoding]::new($true))
    $stdout = Join-Path $root ($case.Name + '.out')
    $stderr = Join-Path $root ($case.Name + '.err')
    $p = Start-Process powershell.exe -ArgumentList ('-NoProfile -ExecutionPolicy Bypass -File "' + $runner + '"') -Wait -PassThru -RedirectStandardOutput $stdout -RedirectStandardError $stderr
    $out = [IO.File]::ReadAllText($stdout) + [IO.File]::ReadAllText($stderr)
    if ($out.Contains($hint) -ne $case.Hint) { throw "G5 $($case.Name) hint mismatch: $out" }
    if ($case.Exit -eq 1 -and $p.ExitCode -ne 1) { throw "G5 $($case.Name) failure swallowed" }
    if ($case.Lines.Count -and $case.Exit -eq 1 -and -not $out.Contains('last lines of install.log')) { throw 'G5 tail lost' }
    if ($case.Exit -eq 0 -and $out.Trim()) { throw 'G5 success printed output' }
    Write-Host "PASS G5: $($case.Name)"
  }
} finally {
  if (Test-Path Env:AV_PROBE_FILE) {
    if (Test-Path -LiteralPath $env:AV_PROBE_FILE) {
      $probe = Get-Content -LiteralPath $env:AV_PROBE_FILE
      Stop-Process -Id ([int]$probe[0]) -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:AV_PROBE_FILE
  }
  Remove-Item Env:AV_PROBE_MODE -ErrorAction SilentlyContinue
  $env:WAVE_HOME = $priorHome
  Remove-Item -LiteralPath $root -Recurse -Force -ErrorAction SilentlyContinue
}
