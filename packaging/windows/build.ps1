# Builds dist\Susurros (the app folder) and dist\Susurros-Setup-VERSION.exe (its installer).
# Needs uv and Inno Setup 6. Usage:  powershell -ExecutionPolicy Bypass -File packaging\windows\build.ps1
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..\..")

uv sync --group package
if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
$env:SUSURROS_VERSION = uv run --no-sync python -c "import tomllib; print(tomllib.load(open('pyproject.toml', 'rb'))['project']['version'])"

New-Item -ItemType Directory -Force -Path build\windows | Out-Null
uv run --no-sync python -m susurros.cli icon build\windows\susurros.ico
if ($LASTEXITCODE -ne 0) { throw "Could not generate the icon" }

uv run --no-sync pyinstaller --noconfirm --distpath dist --workpath build\windows\work packaging\windows\Susurros.spec
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }

$iscc = (Get-Command iscc -ErrorAction SilentlyContinue).Source
if (-not $iscc) { $iscc = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe" }
if (-not (Test-Path $iscc)) { throw "Inno Setup 6 not found. Install it with: winget install JRSoftware.InnoSetup" }
& $iscc /Q packaging\windows\installer.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed" }
Write-Host "Built dist\Susurros-Setup-$env:SUSURROS_VERSION.exe"
