$ErrorActionPreference = 'Stop'
$Id = [guid]::NewGuid().ToString('N')
$Key = "Software\JBEduFormMigrationTests\$Id"
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.codex_tmp\brand-migration-$Id"))
$Output = Join-Path $Root 'test.exe'
$Compiler = Join-Path $env:LOCALAPPDATA 'tauri\NSIS\makensis.exe'
New-Item -ItemType Directory -Path $Root -Force | Out-Null
try {
    Push-Location -LiteralPath $PSScriptRoot
    try {
        & $Compiler /V2 /INPUTCHARSET UTF8 "/DTESTKEY=$Key" "/DTESTOUTPUT=$Output" 'test-brand-migration.nsi'
        if ($LASTEXITCODE -ne 0) { throw 'Brand migration test compilation failed.' }
    } finally { Pop-Location }
    $Test = Start-Process -FilePath $Output -ArgumentList '/S', ('/D=' + $Root) -WindowStyle Hidden -Wait -PassThru
    if ($Test.ExitCode -ne 0) { throw "Brand migration test failed: $($Test.ExitCode)" }
    Write-Host 'Brand migration verified: legacy path reused, registration replaced only after success, existing/custom/unrelated/incomplete installations preserved.'
} finally {
    $RegistryPath = "HKCU:\$Key"
    if (Test-Path -LiteralPath $RegistryPath) { Remove-Item -LiteralPath $RegistryPath -Recurse -Force }
}
