$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$portableExe = Join-Path $projectRoot 'PersonalFilebridge.exe'
if (Test-Path -LiteralPath $portableExe) {
    & $portableExe --transport stdio
    exit $LASTEXITCODE
}
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run setup.ps1 first.' }
& $python -m filebridge.server --transport stdio
exit $LASTEXITCODE
