# Dot-sourced by Mars.ps1. An offline distribution never falls back to downloads.
function Resolve-MarsOfflineFile {
    param([string]$Bundle, [string]$Relative)
    if ($Relative -notmatch '^[A-Za-z0-9_+.\-/]+$' -or $Relative.StartsWith('/') -or
        $Relative -match '(^|/)\.{1,2}(/|$)' -or $Relative.Contains('//')) {
        throw 'Invalid offline dependency path.'
    }
    $current = [IO.Path]::GetFullPath($Bundle)
    foreach ($part in $Relative.Split('/')) {
        $current = Join-Path $current $part
        if ((Test-Path -LiteralPath $current) -and
            ((Get-Item -LiteralPath $current -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw 'Offline dependency paths cannot traverse links.'
        }
    }
    return $current
}

function Restore-MarsOfflineDependency {
    param([string]$Bundle, $Entry)
    $target = Resolve-MarsOfflineFile $Bundle ([string]$Entry.path)
    if ((Test-Path -LiteralPath $target) -or 'parts' -notin $Entry.PSObject.Properties.Name) { return }
    if (@($Entry.parts).Count -eq 0 -or $Entry.bytes -le 0) { throw 'Empty offline dependency parts.' }
    # GitHub source ZIPs contain ordinary binary pieces, never Git LFS pointers.
    # Reassemble with streaming .NET IO before the usual whole-file SHA check.
    $partPaths = @()
    $seen = @{}
    $total = [long]0
    foreach ($part in $Entry.parts) {
        $path = Resolve-MarsOfflineFile $Bundle ([string]$part.path)
        if ($seen.ContainsKey($path.ToLowerInvariant()) -or $part.sha256 -notmatch '^[a-f0-9]{64}$' -or
            $part.bytes -le 0 -or -not (Test-Path -LiteralPath $path -PathType Leaf) -or
            (Get-Item -LiteralPath $path).Length -ne $part.bytes -or
            (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -cne $part.sha256) {
            throw 'Offline dependency part is missing, duplicate or corrupt. Re-extract the complete package.'
        }
        $seen[$path.ToLowerInvariant()] = $true
        $total += [long]$part.bytes
        $partPaths += $path
    }
    if ($total -ne $Entry.bytes) { throw 'Offline dependency parts have an incorrect total size.' }
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    $temporary = $target + '.assemble-' + [guid]::NewGuid().ToString('N')
    $output = $null
    try {
        $output = [IO.File]::Open($temporary, [IO.FileMode]::CreateNew, [IO.FileAccess]::Write, [IO.FileShare]::None)
        foreach ($path in $partPaths) {
            $inputFile = [IO.File]::OpenRead($path)
            try { $inputFile.CopyTo($output) } finally { $inputFile.Dispose() }
        }
        $output.Dispose()
        $output = $null
        if ((Get-FileHash -LiteralPath $temporary -Algorithm SHA256).Hash.ToLowerInvariant() -cne $Entry.sha256) {
            throw 'Reassembled offline dependency checksum mismatch.'
        }
        Move-Item -LiteralPath $temporary -Destination $target
    } finally {
        if ($null -ne $output) { $output.Dispose() }
        Remove-Item -LiteralPath $temporary -Force -ErrorAction SilentlyContinue
    }
}

function Read-MarsOfflineBundle {
    param([string]$Root)
    $marker = Join-Path $Root 'WINDOWS-OFFLINE.json'
    if (-not (Test-Path -LiteralPath $marker)) { return $null }
    $receipt = Get-Content -LiteralPath $marker -Raw | ConvertFrom-Json
    $bundle = (Get-MarsWindowsLayout $Root).Offline
    $manifestPath = Join-Path $bundle 'manifest.json'
    if ($receipt.schema -ne 'mars.windows.offline.v1' -or -not (Test-Path -LiteralPath $manifestPath) -or
        (Get-FileHash -LiteralPath $manifestPath -Algorithm SHA256).Hash -ne $receipt.manifest_sha256) {
        throw 'Offline package manifest is missing or changed. Re-extract the complete trusted ZIP.'
    }
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.schema -ne 'mars.windows.dependencies.v1' -or @($manifest.files).Count -eq 0) {
        throw 'Invalid offline dependency manifest.'
    }
    $seen = @{}
    foreach ($entry in $manifest.files) {
        if ($entry.path -notmatch '^[A-Za-z0-9_+.\-/]+$' -or $entry.path -match '(^|/)\.{1,2}(/|$)' -or
            $entry.path.StartsWith('/') -or $seen.ContainsKey($entry.path.ToLowerInvariant()) -or $entry.sha256 -notmatch '^[a-f0-9]{64}$') {
            throw 'Invalid or duplicate offline dependency path.'
        }
        $seen[$entry.path.ToLowerInvariant()] = $true
        Restore-MarsOfflineDependency $bundle $entry
        $file = Resolve-MarsOfflineFile $bundle ([string]$entry.path)
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or
            ((Get-Item -LiteralPath $file).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0 -or
            (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $entry.sha256) {
            throw "Offline dependency is missing or corrupt: $($entry.path). No network download was attempted."
        }
    }
    foreach ($name in @('uv.zip', 'node.zip', 'git.zip', 'python.zip', 'zcode.zip', 'npm-cache.zip',
                       'vc_redist.x64.exe', 'requirements.windows.txt')) {
        if (-not $seen.ContainsKey($name)) { throw "Offline package lacks required file: $name" }
    }
    return $bundle
}

function Expand-MarsOfflineTool {
    param([string]$Bundle, [string]$Name, [string]$Target)
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    Expand-Archive -LiteralPath (Join-Path $Bundle "$Name.zip") -DestinationPath $Target -Force
}

function Install-OfflineDependencies {
    Assert-ServicesStopped
    $bundle = Read-MarsOfflineBundle $root
    if ($null -eq $bundle) { throw 'An offline installation requires its package marker.' }
    Remove-Item -LiteralPath (Join-Path $runtime 'installed.json') -Force -ErrorAction SilentlyContinue
    Write-Host 'Installing verified Windows dependencies from this folder. No external installation sources are used.'
    foreach ($name in @('uv', 'node', 'git', 'zcode')) {
        Expand-MarsOfflineTool $bundle $name (Join-Path $runtime "tools/$name")
    }
    Expand-MarsOfflineTool $bundle 'python' (Join-Path $runtime 'tools/python-runtime')
    Expand-MarsOfflineTool $bundle 'npm-cache' (Join-Path $runtime 'npm-cache')
    Set-NativeEnvironment
    if (-not (Test-Path "$env:WINDIR/System32/vcruntime140_1.dll")) {
        $vc = Join-Path $bundle 'vc_redist.x64.exe'
        $signature = Get-AuthenticodeSignature -FilePath $vc
        if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') {
            throw 'Microsoft C++ runtime signature verification failed.'
        }
        $installed = Start-Process -FilePath $vc -ArgumentList '/install /passive /norestart' -Wait -PassThru
        if ($installed.ExitCode -notin @(0, 1638, 3010)) { throw "C++ runtime installation failed: $($installed.ExitCode)" }
        if ($installed.ExitCode -eq 3010) { throw 'Restart Windows to finish the C++ runtime, then double-click MARS-Windows.cmd again.' }
    }
    $bootstrap = Join-Path $runtime 'tools/python-runtime/python/python.exe'
    Invoke-MarsNativeCommand $uv @('venv', '--offline', '--no-python-downloads', '--python', $bootstrap,
        '--clear', (Join-Path $runtime 'venv')) $root
    Invoke-MarsNativeCommand $uv @('pip', 'install', '--offline', '--no-index', '--require-hashes', '--python', $python,
        '--find-links', (Join-Path $bundle 'wheelhouse'), '-r', (Join-Path $bundle 'requirements.windows.txt')) $root
    Invoke-MarsNativeCommand $uv @('pip', 'install', '--offline', '--no-index', '--no-deps', '--no-build-isolation',
        '--python', $python, '-e', '.') $root
    Invoke-MarsNativeCommand $uv @('pip', 'check', '--python', $python) $root
    Invoke-MarsNativeCommand $python @('-c', 'import torch, scipy, matplotlib, tensorboard, chromadb, app.main; assert torch.ones(2).sum().item() == 2') $root
    Install-FrontendDependencies -Offline
    Ensure-FrontendBuild
    Invoke-MarsNativeCommand $python @((Join-Path $PSScriptRoot 'probe_zcode.py')) $root
    $fingerprint = Get-MarsDependencyFingerprint $root
    $fingerprint['root'] = $root
    $fingerprint['frontend_mode'] = 'production'
    $fingerprint | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runtime 'installed.json') -Encoding UTF8
    Write-Host 'Offline installation, imports, frontend build and real ZCode handshake passed.' -ForegroundColor Green
}
