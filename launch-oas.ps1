$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$launcherMutex = New-Object Threading.Mutex($false, 'Local\OnmyojiAutoScriptLocalLauncher')
try {
    $ownsLauncherMutex = $launcherMutex.WaitOne(0)
} catch [Threading.AbandonedMutexException] {
    $ownsLauncherMutex = $true
}
if (-not $ownsLauncherMutex) {
    $launcherMutex.Dispose()
    exit
}
$backend = $null
try {
    $ready = $false
    try { $ready = (Invoke-RestMethod 'http://127.0.0.1:22267/home/test' -TimeoutSec 2).message -eq 'test' } catch {}
    if (-not $ready) {
        $backend = Start-Process -FilePath $env:ComSpec -ArgumentList '/c', ('"' + (Join-Path $PSScriptRoot 'start-oas.bat') + '"') -WindowStyle Hidden -PassThru
        for ($i = 0; $i -lt 60; $i++) {
            if ($backend.HasExited) { throw 'Backend exited. Run start-oas.bat to inspect errors.' }
            try { $ready = (Invoke-RestMethod 'http://127.0.0.1:22267/home/test' -TimeoutSec 1).message -eq 'test' } catch {}
            if ($ready) { break }
            Start-Sleep -Seconds 1
        }
        if (-not $ready) { throw 'Backend startup timed out. Run start-oas.bat to inspect errors.' }
    }
    # OASX adds http:// itself; its saved Address must contain only host:port.
    $storagePath = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'GetStorage.gs'
    $storage = @{}
    if (Test-Path -LiteralPath $storagePath) {
        $storage = Get-Content -LiteralPath $storagePath -Raw | ConvertFrom-Json
    }
    $savedAddress = if ($storage -is [hashtable]) { $storage['address'] } else { $storage.address }
    if ($savedAddress -ne '127.0.0.1:22267') {
        if (Test-Path -LiteralPath $storagePath) {
            $backupPath = Join-Path $PSScriptRoot ('GetStorage-before-address-fix-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.json')
            Copy-Item -LiteralPath $storagePath -Destination $backupPath
        }
        if ($storage -is [hashtable]) {
            $storage['address'] = '127.0.0.1:22267'
        } else {
            $storage | Add-Member -NotePropertyName address -NotePropertyValue '127.0.0.1:22267' -Force
        }
        [IO.File]::WriteAllText($storagePath, ($storage | ConvertTo-Json -Depth 100 -Compress), (New-Object Text.UTF8Encoding($false)))
    }
    $taskUiLogDirectory = Join-Path $PSScriptRoot '.logs'
    New-Item -ItemType Directory -Path $taskUiLogDirectory -Force | Out-Null
    $taskUiLogStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    Start-Process -FilePath (Join-Path $PSScriptRoot 'OASX\oasx.exe') -WorkingDirectory (Join-Path $PSScriptRoot 'OASX') -RedirectStandardOutput (Join-Path $taskUiLogDirectory "oasx-$taskUiLogStamp-stdout.log") -RedirectStandardError (Join-Path $taskUiLogDirectory "oasx-$taskUiLogStamp-stderr.log") -Wait
} catch {
    Write-Host $_ -ForegroundColor Red
    Read-Host 'Press Enter to close'
} finally {
    if ($null -ne $backend -and -not $backend.HasExited) {
        & taskkill.exe /PID $backend.Id /T /F | Out-Null
    }
    $launcherMutex.ReleaseMutex()
    $launcherMutex.Dispose()
}
