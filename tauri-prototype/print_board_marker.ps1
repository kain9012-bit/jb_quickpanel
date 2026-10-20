param(
    [string]$Version,
    [string]$SignaturePath,
    [string]$DownloadUrl,
    [string]$AppId = "JBEDU-FORM",
    [string]$AppName = "JBEdu FORM (JB에듀 폼)"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not $Version) {
    $Package = Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot "package.json") | ConvertFrom-Json
    $Version = [string]$Package.version
}

if (-not $SignaturePath) {
    $Bundle = Join-Path $ProjectRoot "src-tauri\target\release\bundle\nsis"
    $Found = Get-ChildItem -LiteralPath $Bundle -Filter "*.sig" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $Found) {
        throw "서명(.sig) 파일을 찾지 못했습니다. 먼저 build_v4.ps1을 실행하거나 -SignaturePath를 지정하세요."
    }
    $SignaturePath = $Found.FullName
}

if (-not $DownloadUrl) {
    throw "게시판에 ZIP을 첨부한 뒤 첨부 링크 주소를 -DownloadUrl로 지정하세요."
}
if ($DownloadUrl -notmatch '^https://') {
    throw "HTTPS 첨부 링크만 사용할 수 있습니다."
}
if ($DownloadUrl -notmatch 'download\.jbe') {
    Write-Warning "교육청 게시판 첨부 링크가 아닌 것 같습니다."
}

$Signature = (Get-Content -Raw -LiteralPath $SignaturePath).Trim()
if ($Signature -match '[\|\r\n]') {
    throw "서명에 구분자나 줄바꿈이 포함되어 있습니다. 올바른 .sig 파일인지 확인하세요."
}

try {
    $Decoded = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($Signature))
} catch {
    throw "서명 파일을 해석하지 못했습니다."
}
if (-not $Decoded.StartsWith("untrusted comment:")) {
    throw "올바른 minisign 서명 파일이 아닙니다."
}

$Marker = "[업데이트정보]id=$AppId|앱=$AppName|버전=$Version|다운로드=$DownloadUrl|서명=$Signature"
Write-Host ""
Write-Host "아래 한 줄을 업데이트 게시글 본문에 붙여 넣으세요."
Write-Host "----------------------------------------------------------------"
Write-Host $Marker
Write-Host "----------------------------------------------------------------"
Set-Clipboard -Value $Marker
Write-Host "클립보드에도 복사했습니다."
