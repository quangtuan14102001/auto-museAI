$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
Push-Location $projectRoot
try {
    & "$projectRoot\.venv\Scripts\python.exe" -c "from core.license_source import LICENSE_REQUIRED, LICENSE_SERVER_URL; from urllib.parse import urlparse; assert not LICENSE_REQUIRED or (urlparse(LICENSE_SERVER_URL).scheme == 'https' and urlparse(LICENSE_SERVER_URL).hostname), 'Commercial build requires a configured HTTPS license server'"
    if ($LASTEXITCODE -ne 0) { throw 'License release configuration is incomplete.' }
    # Avoid collecting unrelated runtime DLLs (notably ucrtbase.dll) from
    # document/image tooling supplied by the agent environment.
    $env:PATH = (($previousPath -split ';') | Where-Object {
        $_ -and $_ -notmatch '[\\/]codex-runtimes[\\/]'
    }) -join ';'
    & "$projectRoot\.venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --distpath dist/fixed AutoMuseAI.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
