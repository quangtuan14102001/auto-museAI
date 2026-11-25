$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$previousPath = $env:PATH
Push-Location $projectRoot
try {
    & "$projectRoot\.venv\Scripts\python.exe" -c "from core.license_source import LICENSE_REQUIRED, LICENSE_SERVER_URL; from urllib.parse import urlparse; assert not LICENSE_REQUIRED or (urlparse(LICENSE_SERVER_URL).scheme == 'https' and urlparse(LICENSE_SERVER_URL).hostname), 'Commercial build requires a configured HTTPS license server'"
    if ($LASTEXITCODE -ne 0) { throw 'License release configuration is incomplete.' }
    # Build only against Python and Windows. A deny-list of runtime paths can
    # miss renamed tooling installations and package an incompatible ucrtbase.
    $pythonBase = & "$projectRoot\.venv\Scripts\python.exe" -c "import sys; print(sys.base_prefix)"
    if ($LASTEXITCODE -ne 0) { throw 'Cannot locate the Python build runtime.' }
    $env:PATH = @(
        "$projectRoot\.venv\Scripts",
        $pythonBase.Trim(),
        (Join-Path $pythonBase.Trim() 'DLLs'),
        (Join-Path $env:WINDIR 'System32'),
        $env:WINDIR,
        (Join-Path $env:WINDIR 'System32\Wbem')
    ) -join ';'
    & "$projectRoot\.venv\Scripts\python.exe" -m PyInstaller --clean --noconfirm --distpath dist/fixed AutoMuseAI.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed.' }
    & "$projectRoot\.venv\Scripts\python.exe" "$projectRoot\tools\verify_windows_bundle.py" "$projectRoot\dist\fixed\AutoMuseAI.exe"
    if ($LASTEXITCODE -ne 0) { throw 'Packaged GUI dependencies failed validation.' }
} finally {
    $env:PATH = $previousPath
    Pop-Location
}
