$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
Push-Location $projectRoot
try {
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
