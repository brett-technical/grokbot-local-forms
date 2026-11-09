#Requires -Version 5.1
<#
.SYNOPSIS
  Start the local form server in the background and open it in the browser.
.PARAMETER NoBrowser
  Start the server but don't open a browser.
#>
param(
  [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# Prefer py launcher, then python on PATH.
$Python = $null
foreach ($name in @("py", "python", "python3")) {
  $cmd = Get-Command $name -ErrorAction SilentlyContinue
  if ($cmd) { $Python = $cmd.Source; break }
}
if (-not $Python) { throw "Python not found on PATH. Install Python 3, then retry." }

# Prefer Brave if installed; otherwise the system default browser.
$BraveCandidates = @(
  "${env:ProgramFiles}\BraveSoftware\Brave-Browser\Application\brave.exe",
  "${env:ProgramFiles(x86)}\BraveSoftware\Brave-Browser\Application\brave.exe",
  "$env:LOCALAPPDATA\BraveSoftware\Brave-Browser\Application\brave.exe"
)
$Brave = $BraveCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1

$pidFile = Join-Path $PSScriptRoot ".form-server.pid"
$outLog = Join-Path $PSScriptRoot "server.log"
$errLog = Join-Path $PSScriptRoot "server.err.log"

# Stop a previous instance from this folder only.
if (Test-Path -LiteralPath $pidFile) {
  $oldPid = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
  if ($oldPid) {
    $proc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($proc) {
      Stop-Process -Id $oldPid -Force -ErrorAction SilentlyContinue
      Start-Sleep -Milliseconds 400
    }
  }
  Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

Remove-Item -LiteralPath $outLog, $errLog -Force -ErrorAction SilentlyContinue

$proc = Start-Process -FilePath $Python `
  -ArgumentList @("-u", "server.py") `
  -WorkingDirectory $PSScriptRoot `
  -WindowStyle Hidden `
  -RedirectStandardOutput $outLog `
  -RedirectStandardError $errLog `
  -PassThru

Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding ascii

$url = $null
for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 250
  if (Test-Path -LiteralPath $outLog) {
    $text = Get-Content -LiteralPath $outLog -Raw -ErrorAction SilentlyContinue
    if ($text -match 'Form at (http://127\.0\.0\.1:\d+/)') {
      $url = $Matches[1]
      break
    }
  }
  $alive = Get-Process -Id $proc.Id -ErrorAction SilentlyContinue
  if (-not $alive) { break }
}

if (-not $url) {
  $err = ""
  if (Test-Path -LiteralPath $errLog) { $err = Get-Content -LiteralPath $errLog -Raw -ErrorAction SilentlyContinue }
  if (Test-Path -LiteralPath $outLog) { $err += "`n" + (Get-Content -LiteralPath $outLog -Raw -ErrorAction SilentlyContinue) }
  throw "Form server did not print a URL. Output:`n$err"
}

Write-Host $url
if (-not $NoBrowser) {
  if ($Brave) {
    Start-Process -FilePath $Brave -ArgumentList @($url)
  } else {
    Start-Process $url
  }
}
