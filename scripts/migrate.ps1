# Add-on migration for Windows PowerShell 5.1. Source configuration is read-only.
[CmdletBinding()]
param([switch]$DryRun)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$utf8 = New-Object System.Text.UTF8Encoding($false)
$homeDir = $env:USERPROFILE
if (-not $homeDir) { $homeDir = $HOME }
$source = if ($env:WAVE_MIGRATE_SRC) { $env:WAVE_MIGRATE_SRC } else { Join-Path $homeDir '.claude' }
$account = if ($env:CYS_ACCOUNT_DIR) { $env:CYS_ACCOUNT_DIR } else { Join-Path $homeDir '.cys/claude' }
$local = if ($env:CYS_LOCAL_DIR) { $env:CYS_LOCAL_DIR } else { Join-Path $homeDir '.cys/local' }
$base = Join-Path $homeDir '.cys/backup'
$script:copied = 0
$script:clashes = 0
$script:hooks = 0
$script:mcp = 0
$script:report = $null
$script:lines = New-Object 'System.Collections.Generic.List[string]'
function Log([string]$Text) {
    Write-Output $Text
    if ($script:report) { [IO.File]::AppendAllText($script:report, $Text + "`n", $utf8) }
    else { $script:lines.Add($Text) }
}
function Validate-Path([string]$Path) {
    if (-not [IO.Path]::IsPathRooted($Path)) { throw "Absolute path required: $Path" }
    $full = [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)
    if ($full -eq [IO.Path]::GetPathRoot($Path).TrimEnd([IO.Path]::DirectorySeparatorChar)) {
        throw 'Filesystem root is not a migration directory'
    }
    $cursor = $full
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $info = Get-Item -Force -LiteralPath $cursor
            if ($info.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "symlink/reparse path: $cursor" }
        }
        $parent = [IO.Path]::GetDirectoryName($cursor)
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $full
}
function Contains-Path([string]$Root, [string]$Path) {
    return $Path.Equals($Root, [StringComparison]::OrdinalIgnoreCase) -or
        $Path.StartsWith($Root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}
$source = Validate-Path $source
$account = Validate-Path $account
$local = Validate-Path $local
$base = Validate-Path $base
$homeSettings = Join-Path $homeDir '.claude.json'
$roots = @($source, $account, $local, $base)
for ($i = 0; $i -lt $roots.Count; $i++) {
    for ($j = $i + 1; $j -lt $roots.Count; $j++) {
        if ((Contains-Path $roots[$i] $roots[$j]) -or (Contains-Path $roots[$j] $roots[$i])) {
            throw 'Source, destinations and backup must be disjoint'
        }
    }
}
if (-not [IO.Directory]::Exists($source)) { throw "Source directory missing: $source" }
foreach ($path in @($account, $local, $base)) {
    if ([IO.File]::Exists($path)) { throw "Not a directory: $path" }
}
function Is-Link($Info) { return [bool]($Info.Attributes -band [IO.FileAttributes]::ReparsePoint) }
# shortcut: assumes no concurrent writers, add locking before supporting live migration.
function Copy-Tree([string]$From, [string]$To, [bool]$Memory = $false) {
    $info = Get-Item -Force -LiteralPath $From
    if (Is-Link $info) { Log "skipped symlink: $From"; return }
    if ($Memory -and $info.Name.EndsWith('.jsonl', [StringComparison]::OrdinalIgnoreCase)) {
        Log "skipped transcript: $From"; return
    }
    if ($info.PSIsContainer) {
        if (-not $DryRun) { [void][IO.Directory]::CreateDirectory($To) }
        foreach ($child in [IO.Directory]::GetFileSystemEntries($From)) {
            Copy-Tree $child (Join-Path $To ([IO.Path]::GetFileName($child))) $Memory
        }
    } elseif (-not $DryRun) {
        [IO.File]::Copy($From, $To, $false)
    }
}
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path $base "migrate-$stamp"
if ($DryRun) {
    Log 'DRY RUN: no files will be written'
    Log "planned backup: $backup"
} else {
    [void][IO.Directory]::CreateDirectory($base)
    while (Test-Path -LiteralPath $backup) {
        Start-Sleep -Seconds 1
        $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
        $backup = Join-Path $base "migrate-$stamp"
    }
    [void][IO.Directory]::CreateDirectory($backup)
    Log "backup: $backup"
    if ([IO.Directory]::Exists($account)) { Copy-Tree $account (Join-Path $backup 'claude') }
    if ([IO.Directory]::Exists($local)) { Copy-Tree $local (Join-Path $backup 'local') }
    $script:report = Join-Path $backup 'report.txt'
    [IO.File]::WriteAllLines($script:report, $script:lines.ToArray(), $utf8)
}
function Copy-ItemSafe([string]$From, [string]$To, [bool]$Memory = $false) {
    $info = Get-Item -Force -LiteralPath $From
    if (Is-Link $info) { Log "skipped symlink: $From"; return }
    try { $null = Validate-Path $To }
    catch { Log "skipped symlink/unsafe target: $To"; return }
    if (Test-Path -LiteralPath $To) {
        $script:clashes++; Log "skipped clash: $To"; return
    }
    Log "copy: $From -> $To"
    if (-not $DryRun) { [void][IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($To)) }
    Copy-Tree $From $To $Memory
    $script:copied++
}
$targetMd = Join-Path $account 'CLAUDE.md'
$sourceMd = Join-Path $source 'CLAUDE.md'
if (Test-Path -LiteralPath $sourceMd) {
    if (Is-Link (Get-Item -Force -LiteralPath $sourceMd)) { Log "skipped symlink: $sourceMd" }
    elseif ((Test-Path -LiteralPath $targetMd) -and (Is-Link (Get-Item -Force -LiteralPath $targetMd))) {
        Log "skipped symlink: $targetMd"
    }
    elseif ([IO.File]::Exists($sourceMd)) {
        $null = Validate-Path $targetMd
        $bytes = [IO.File]::ReadAllBytes($sourceMd)
        $sha = [Security.Cryptography.SHA256]::Create()
        try { $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant() }
        finally { $sha.Dispose() }
        $marker = "<!-- source sha256: $hash -->"
        $block = '(?ms)^<!-- migrated from ~/\.claude/CLAUDE\.md [^\r\n]+ -->\r?\n<!-- source sha256: ' + $hash + ' -->\r?\n.*?^<!-- end migrated -->\r?$'
        if ([IO.File]::Exists($targetMd) -and [regex]::IsMatch([IO.File]::ReadAllText($targetMd), $block)) {
            Log 'skipped identical migrated CLAUDE.md block'
        } elseif ([IO.Directory]::Exists($targetMd)) {
            $script:clashes++; Log 'skipped clash: CLAUDE.md is not a regular file'
        } else {
            Log "append: $sourceMd -> $targetMd (sha256 $hash)"
            if (-not $DryRun) {
                [void][IO.Directory]::CreateDirectory($account)
                $stream = [IO.File]::Open($targetMd, [IO.FileMode]::Append, [IO.FileAccess]::Write, [IO.FileShare]::None)
                try {
                    $header = $utf8.GetBytes("`n<!-- migrated from ~/.claude/CLAUDE.md $stamp -->`n$marker`n")
                    $footer = $utf8.GetBytes("`n<!-- end migrated -->`n")
                    $stream.Write($header, 0, $header.Length)
                    $stream.Write($bytes, 0, $bytes.Length)
                    $stream.Write($footer, 0, $footer.Length)
                } finally { $stream.Dispose() }
            }
            $script:copied++
        }
    }
}
foreach ($category in @('skills', 'agents', 'commands', 'projects')) {
    $dir = Join-Path $source $category
    if (-not (Test-Path -LiteralPath $dir)) { continue }
    if (Is-Link (Get-Item -Force -LiteralPath $dir)) { Log "skipped symlink: $dir"; continue }
    if (-not [IO.Directory]::Exists($dir)) { continue }
    foreach ($entry in [IO.Directory]::GetFileSystemEntries($dir)) {
        $info = Get-Item -Force -LiteralPath $entry
        if (Is-Link $info) { Log "skipped symlink: $entry"; continue }
        $name = $info.Name
        switch ($category) {
            'skills' { if ($info.PSIsContainer) { Copy-ItemSafe $entry (Join-Path $local "skills/$name") } }
            'agents' { Copy-ItemSafe $entry (Join-Path $account "agents/$name") }
            'commands' { Copy-ItemSafe $entry (Join-Path $account "commands/$name") }
            'projects' {
                $memory = Join-Path $entry 'memory'
                if (Test-Path -LiteralPath $memory) {
                    $memoryInfo = Get-Item -Force -LiteralPath $memory
                    if ((Is-Link $memoryInfo) -or $memoryInfo.PSIsContainer) {
                        Copy-ItemSafe $memory (Join-Path $account "projects/$name/memory") $true
                    }
                }
            }
        }
    }
}
foreach ($settings in @((Join-Path $source 'settings.json'), $homeSettings)) {
    if (-not (Test-Path -LiteralPath $settings)) { continue }
    if (Is-Link (Get-Item -Force -LiteralPath $settings)) { Log "skipped symlink: $settings"; continue }
    # Only property names leave the JSON parser; commands, tokens and URLs stay private.
    try { $data = [IO.File]::ReadAllText($settings) | ConvertFrom-Json }
    catch { throw "Cannot parse settings: $settings (backup: $backup)" }
    foreach ($group in @('hooks', 'mcpServers')) {
        $property = $data.PSObject.Properties[$group]
        if ($null -eq $property -or $null -eq $property.Value) { continue }
        foreach ($prop in $property.Value.PSObject.Properties) {
            $name = ConvertTo-Json -InputObject $prop.Name -Compress
            Log "listed $settings ${group}: $name"
            if ($group -eq 'hooks') { $script:hooks++ } else { $script:mcp++ }
        }
    }
}
Log "summary: copied $script:copied / skipped (clash) $script:clashes / listed hooks $script:hooks + MCP $script:mcp / backup $backup"
if ($DryRun) { Log 'report: none (dry run)' } else { Log "report: $script:report" }

$reportLocation = if ($DryRun) { '없음(미리보기)' } else { $script:report }
Write-Output "옮긴 것 $script:copied`개 / 건너뛴 것 $script:clashes`개(이름 충돌) / 훅·MCP 목록: 훅 $script:hooks`개 + MCP $script:mcp`개 / 백업 위치: $backup / 보고서 위치: $reportLocation"
