$ErrorActionPreference = 'Stop'
$Root = Join-Path $PSScriptRoot '..\..\.codex_tmp'
$TestRoot = Join-Path ([IO.Path]::GetFullPath($Root)) ('installer-backend-' + [guid]::NewGuid().ToString('N'))
$InstallDir = Join-Path $TestRoot 'installed'
$OtherDir = Join-Path $TestRoot 'other'
$Hook = Join-Path $PSScriptRoot '..\src-tauri\stop-installed-backend.ps1'
$Shell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'
$Compiler = Join-Path $env:LOCALAPPDATA 'tauri\NSIS\makensis.exe'
$Harness = Join-Path $Root 'installer-backend-test.exe'
$Children = @()
try {
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $Compiler /V2 'test-installer-backend.nsi'
        if ($LASTEXITCODE -ne 0) { throw 'NSIS test compilation failed.' }
    } finally { Pop-Location }
    foreach ($Directory in @($InstallDir, $OtherDir)) {
        $Bin = Join-Path $Directory 'binaries'
        New-Item -ItemType Directory -Path $Bin -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $env:WINDIR 'System32\ping.exe') -Destination (Join-Path $Bin 'jb_hwp_backend.exe')
    }
    foreach ($Directory in @($InstallDir, $InstallDir, $OtherDir)) {
        $Children += Start-Process -FilePath (Join-Path $Directory 'binaries\jb_hwp_backend.exe') -ArgumentList '-t', '127.0.0.1' -WindowStyle Hidden -PassThru
    }
    Start-Sleep -Milliseconds 300
    $Installer = Start-Process -FilePath $Harness -ArgumentList '/S', ('/D=' + $InstallDir) -WindowStyle Hidden -Wait -PassThru
    if ($Installer.ExitCode -ne 0) { throw 'NSIS backend cleanup failed.' }
    foreach ($Child in $Children[0..1]) {
        if (-not $Child.WaitForExit(2000)) { throw 'An installed backend survived.' }
    }
    $Children[2].Refresh()
    if ($Children[2].HasExited) { throw 'A backend in another directory was stopped.' }
    $Children += Start-Process -FilePath (Join-Path $InstallDir 'binaries\jb_hwp_backend.exe') -ArgumentList '-t', '127.0.0.1' -WindowStyle Hidden -PassThru
    Start-Sleep -Milliseconds 300
    $Uninstaller = Start-Process -FilePath (Join-Path $InstallDir 'uninstall-test.exe') -ArgumentList '/S', ('_?=' + $InstallDir) -WindowStyle Hidden -Wait -PassThru
    if ($Uninstaller.ExitCode -ne 0 -or -not $Children[3].WaitForExit(2000)) { throw 'Uninstall backend cleanup failed.' }
    $Children[2].Refresh()
    if ($Children[2].HasExited) { throw 'Uninstall stopped an unrelated backend.' }
    & $Shell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Hook -InstallDir $InstallDir
    if ($LASTEXITCODE -ne 0) { throw 'Cleanup should work when nothing is running.' }
    & $Shell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $Hook -InstallDir 'relative-path'
    if ($LASTEXITCODE -eq 0) { throw 'A relative install directory was accepted.' }
    Write-Host 'NSIS install/uninstall cleanup verified: installed copies stopped, other copy preserved, repeat safe, relative path rejected.'
} finally {
    foreach ($Child in $Children) {
        if (-not $Child.HasExited) {
            $Child.Kill()
            $Child.WaitForExit()
        }
    }
}
