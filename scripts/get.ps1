# Downloads the latest Susurros for Windows and installs it. In PowerShell:
#   irm https://raw.githubusercontent.com/KTJota/susurros/main/scripts/get.ps1 | iex
# SUSURROS_ZIP can point to an already downloaded release zip to install that one instead.
& {
    $ErrorActionPreference = "Stop"
    $ProgressPreference = "SilentlyContinue"   # the progress bar makes downloads many times slower
    $repo = "KTJota/susurros"
    $base = Join-Path $env:LOCALAPPDATA "Susurros"
    New-Item -ItemType Directory -Force -Path $base | Out-Null

    $env:PATH = $env:PATH + ";" + [Environment]::GetEnvironmentVariable("PATH", "User")
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        Write-Host "Installing uv (it downloads Python and the libraries Susurros needs)..."
        Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
        $env:PATH = (Join-Path $env:USERPROFILE ".local\bin") + ";" + $env:PATH
    }

    $zip = $env:SUSURROS_ZIP
    if (-not $zip) {
        Write-Host "Downloading Susurros..."
        $releases = Invoke-RestMethod "https://api.github.com/repos/$repo/releases?per_page=30"
        $release = $releases | Where-Object { $_.tag_name -like "*-windows" } | Select-Object -First 1
        if (-not $release) { throw "No Windows release of Susurros was found." }
        $asset = $release.assets | Where-Object { $_.name -like "*-windows.zip" } | Select-Object -First 1
        $zip = Join-Path $env:TEMP $asset.name
        Invoke-WebRequest $asset.browser_download_url -OutFile $zip
    }

    $source = Join-Path $base "source"
    if (Test-Path $source) { Remove-Item $source -Recurse -Force }
    Expand-Archive $zip -DestinationPath $source
    $folder = Get-ChildItem $source -Directory | Select-Object -First 1

    Write-Host "Installing (the first time this downloads a few gigabytes)..."
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $folder.FullName "scripts\install.ps1")
    if ($LASTEXITCODE -ne 0) { throw "The installation did not finish." }
}
