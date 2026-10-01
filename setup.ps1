param(
    [string[]]$AllowedRoots,
    [switch]$SkipCodexRegistration
)

$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Personal Filebridge V1 requires Windows.' }
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) { throw 'LOCALAPPDATA is required.' }
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $projectRoot '.venv'
$python = Join-Path $venvDir 'Scripts\python.exe'
$stateDir = Join-Path $env:LOCALAPPDATA 'PersonalFilebridge'
$configPath = Join-Path $stateDir 'config.json'
$recoveryDir = Join-Path $env:USERPROFILE 'Filebridge Recovery'

function Set-PrivateAcl([string]$Path, [bool]$Directory) {
    $sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    if ($Directory) {
        $acl = [System.Security.AccessControl.DirectorySecurity]::new()
        $flags = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit -bor [System.Security.AccessControl.InheritanceFlags]::ObjectInherit
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($sid, [System.Security.AccessControl.FileSystemRights]::FullControl, $flags, [System.Security.AccessControl.PropagationFlags]::None, [System.Security.AccessControl.AccessControlType]::Allow)
    } else {
        $acl = [System.Security.AccessControl.FileSecurity]::new()
        $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($sid, [System.Security.AccessControl.FileSystemRights]::FullControl, [System.Security.AccessControl.AccessControlType]::Allow)
    }
    $acl.SetOwner($sid)
    $acl.SetAccessRuleProtection($true, $false)
    $acl.AddAccessRule($rule)
    Set-Acl -LiteralPath $Path -AclObject $acl
    $applied = Get-Acl -LiteralPath $Path
    $rules = @($applied.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
    if (-not $applied.AreAccessRulesProtected -or $rules.Count -ne 1 -or $rules[0].IdentityReference.Value -ne $sid.Value) {
        throw "Could not verify private Windows permissions on $Path"
    }
}

if (Test-Path -LiteralPath $configPath) {
    Write-Warning "An existing Filebridge configuration was found at $configPath. Replacing it will change the folders available to an existing installation."
    $answer = Read-Host 'Type REPLACE to overwrite the existing allowed roots'
    if ($answer -cne 'REPLACE') { throw 'Existing configuration left unchanged.' }
}

if (-not $AllowedRoots) {
    Write-Host 'Choose folders that Personal Filebridge may access. Enter a blank line when done.'
    $AllowedRoots = @()
    do {
        $answer = Read-Host 'Allowed folder (absolute path)'
        if (-not [string]::IsNullOrWhiteSpace($answer)) { $AllowedRoots += $answer }
    } while (-not [string]::IsNullOrWhiteSpace($answer))
}

$validatedRoots = @()
foreach ($root in $AllowedRoots) {
    $driveAbsolute = $root -match '^[A-Za-z]:[\\/]'
    $uncAbsolute = $root -match '^\\\\[^\\]+\\[^\\]+(?:\\|$)'
    if (-not ($driveAbsolute -or $uncAbsolute)) { throw "Allowed folder must be an absolute path: $root" }
    $item = Get-Item -LiteralPath $root -ErrorAction Stop
    if (-not $item.PSIsContainer) { throw "Allowed path must be a directory: $root" }
    if (($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
        throw "Allowed folder cannot be a link or reparse point: $root"
    }
    $fullPath = [System.IO.Path]::GetFullPath($item.FullName).TrimEnd('\')
    $driveRoot = [System.IO.Path]::GetPathRoot($fullPath).TrimEnd('\')
    if ($fullPath -eq $driveRoot) { throw "A drive root cannot be an allowed folder: $root" }
    $validatedRoots += $fullPath
}
$validatedRoots = @($validatedRoots | Select-Object -Unique)
if ($validatedRoots.Count -eq 0) { throw 'At least one allowed folder is required. No configuration was written.' }

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if (-not (Test-Path -LiteralPath $python)) {
    if ($pythonLauncher) {
        & py -3 -m venv $venvDir
    } else {
        & python -m venv $venvDir
    }
    if ($LASTEXITCODE -ne 0) { throw 'Python 3.13+ is required to create the environment.' }
}
& $python -c 'import sys; assert sys.version_info >= (3, 13), "Python 3.13+ required"'
if ($LASTEXITCODE -ne 0) { throw 'The Python environment must use Python 3.13 or newer.' }
& $python -m pip install --upgrade $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }

New-Item -ItemType Directory -Force -Path $stateDir | Out-Null
New-Item -ItemType Directory -Force -Path $recoveryDir | Out-Null
foreach ($directory in @($stateDir, $recoveryDir)) {
    if ((Get-Item -LiteralPath $directory).Attributes.HasFlag([System.IO.FileAttributes]::ReparsePoint)) {
        throw "Private data directory cannot be a link: $directory"
    }
    Set-PrivateAcl $directory $true
}
$tempConfig = Join-Path $stateDir ('.config-' + [guid]::NewGuid().ToString('N') + '.tmp')
try {
    $json = @{ allowed_roots = @($validatedRoots) } | ConvertTo-Json -Depth 3
    [System.IO.File]::WriteAllText($tempConfig, $json, [System.Text.UTF8Encoding]::new($false))
    Move-Item -LiteralPath $tempConfig -Destination $configPath -Force
    Set-PrivateAcl $configPath $false
} finally {
    if (Test-Path -LiteralPath $tempConfig) { Remove-Item -LiteralPath $tempConfig -Force }
}
Write-Host "Allowed folders saved to $configPath"

if (-not $SkipCodexRegistration) {
    $codex = Get-Command codex -ErrorAction SilentlyContinue
    if (-not $codex) {
        Write-Warning 'Codex CLI was not found. Installation is complete; register the MCP server manually using run-stdio.cmd.'
    } else {
        & codex mcp get personal-filebridge *> $null
        if ($LASTEXITCODE -eq 0) {
            Write-Warning 'An MCP server named personal-filebridge already exists. It was left unchanged; review it before switching to this installation.'
        } else {
            & codex mcp add personal-filebridge -- $python -m filebridge.server --transport stdio
            if ($LASTEXITCODE -ne 0) { throw 'Codex registration failed. The local installation and configuration are available.' }
            Write-Host 'Registered personal-filebridge with Codex. Restart Codex, then call health.'
        }
    }
}

Write-Host 'Setup complete. Commits require an approval dialog on this Windows desktop.'
