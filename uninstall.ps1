param([switch]$RemoveLocalData)

$ErrorActionPreference = 'Stop'
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA) -or [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    throw 'LOCALAPPDATA and USERPROFILE are required.'
}
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectRoot '.venv'
$stateDir = Join-Path $env:LOCALAPPDATA 'PersonalFilebridge'
$recoveryDir = Join-Path $env:USERPROFILE 'Filebridge Recovery'

$codex = Get-Command codex -ErrorAction SilentlyContinue
if ($codex) {
    & codex mcp get personal-filebridge *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Warning 'The personal-filebridge MCP registration may belong to a different installation. Inspect it with codex mcp get personal-filebridge before removal.'
        $answer = Read-Host 'Remove the Codex MCP registration named personal-filebridge? [y/N]'
        if ($answer -match '^(?i:y|yes)$') {
            & codex mcp remove personal-filebridge
            if ($LASTEXITCODE -ne 0) { throw 'Could not remove the MCP registration.' }
        }
    }
}

if (Test-Path -LiteralPath $venvDir) {
    $answer = Read-Host 'Remove the private Python environment in this folder? [y/N]'
    if ($answer -match '^(?i:y|yes)$') {
        $expected = [System.IO.Path]::GetFullPath((Join-Path $projectRoot '.venv'))
        $actual = [System.IO.Path]::GetFullPath($venvDir)
        if ($actual -ne $expected -or (Get-Item -LiteralPath $venvDir).Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe environment path.' }
        Remove-Item -LiteralPath $venvDir -Recurse -Force
    }
}

if ($RemoveLocalData) {
    Write-Warning 'Local state can contain recovery files and audit history. Removing it may prevent restoration.'
    foreach ($target in @($stateDir, $recoveryDir)) {
        if (Test-Path -LiteralPath $target) {
            Write-Host "Target: $target"
            $answer = Read-Host 'Type DELETE to permanently remove this directory and all its contents'
            if ($answer -ceq 'DELETE') {
                $actual = [System.IO.Path]::GetFullPath($target)
                $expected = if ($target -eq $stateDir) {
                    [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'PersonalFilebridge'))
                } else {
                    [System.IO.Path]::GetFullPath((Join-Path $env:USERPROFILE 'Filebridge Recovery'))
                }
                if ($actual -ne $expected -or (Get-Item -LiteralPath $target).Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) { throw 'Unsafe local data path.' }
                Remove-Item -LiteralPath $target -Recurse -Force
            }
        }
    }
} else {
    Write-Host "Local state retained: $stateDir"
    Write-Host "Recovery files retained: $recoveryDir"
}
Write-Host 'Uninstall steps complete. The source folder was not removed.'
