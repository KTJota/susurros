# Installs Susurros on Windows: its own environment in %LOCALAPPDATA%\Susurros plus shortcuts.
# Usage:  powershell -ExecutionPolicy Bypass -File scripts\install.ps1
$ErrorActionPreference = "Stop"

$project = Split-Path -Parent $PSScriptRoot
$base = Join-Path $env:LOCALAPPDATA "Susurros"
$venv = Join-Path $base "venv"
New-Item -ItemType Directory -Force -Path $base | Out-Null

# A terminal opened before uv was installed does not have it on PATH yet: refresh it.
$env:PATH = $env:PATH + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
$uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
if (-not $uv) {
    $uv = Get-ChildItem (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages") -Recurse -Filter uv.exe -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $uv -or -not (Test-Path $uv)) { throw "uv not found. Install it with: winget install astral-sh.uv" }

# If the app is open its files are locked: close it before updating.
Get-Process susurros -ErrorAction SilentlyContinue | Stop-Process -Force
Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" |
    Where-Object { $_.ExecutablePath -like "$venv*" -or $_.CommandLine -match "-m susurros(\s|$)" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800   # Windows takes a moment to release the process's files

$env:UV_PROJECT_ENVIRONMENT = $venv
$env:UV_LINK_MODE = "copy"
& $uv sync --project $project --no-dev --no-editable --reinstall-package susurros
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }

# Launched with the environment's interpreter and not susurros.exe: that launcher is generated
# unsigned on every install and Windows Smart App Control blocks it.
$pythonw = Join-Path $venv "Scripts\pythonw.exe"
$icon = Join-Path $base "susurros.ico"
& (Join-Path $venv "Scripts\python.exe") -m susurros.cli icon $icon
if ($LASTEXITCODE -ne 0) { throw "Could not generate the icon" }

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    (Join-Path ([Environment]::GetFolderPath("Programs")) "Susurros.lnk"),
    (Join-Path ([Environment]::GetFolderPath("Desktop")) "Susurros.lnk")
)
foreach ($path in $targets) {
    $link = $shell.CreateShortcut($path)
    $link.TargetPath = $pythonw
    $link.Arguments = "-m susurros"
    $link.WorkingDirectory = $base
    $link.IconLocation = $icon
    $link.Description = "Voice dictation"
    $link.Save()
}
Write-Host "Susurros installed. Open it from the Start menu or the desktop."
