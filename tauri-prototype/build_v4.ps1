param(
    [string]$PythonExe = "",
    [string]$PnpmExe = "",
    [string]$SigningKey = ".signing\tauri.key",
    [string]$SigningPassword = ""
)

$ErrorActionPreference = "Stop"
$PrototypeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PackageJson = Get-Content -Raw -LiteralPath (Join-Path $PrototypeRoot "package.json") | ConvertFrom-Json
$InternalVersion = [string]$PackageJson.version
if ($InternalVersion -notmatch '^\d+\.\d+\.\d+$') {
    throw "package.json 버전이 올바른 형식이 아닙니다: $InternalVersion"
}
$DisplayVersion = "v.$InternalVersion"
$RepositoryRoot = Split-Path -Parent $PrototypeRoot
$TauriRoot = Join-Path $PrototypeRoot "src-tauri"
$TauriConfig = Get-Content -Raw -LiteralPath (Join-Path $TauriRoot "tauri.conf.json") | ConvertFrom-Json
$ProductName = [string]$TauriConfig.productName
$SidecarSpec = Join-Path $PrototypeRoot "jb_hwp_backend.spec"
$SidecarBinDir = Join-Path $TauriRoot "binaries"
$SidecarBin = Join-Path $SidecarBinDir "jb_hwp_backend.exe"
$BuildRoot = Join-Path $PrototypeRoot "build-sidecar"
$SidecarWork = Join-Path $BuildRoot "work"
$SidecarDist = Join-Path $BuildRoot "dist"
$ReleaseDir = Join-Path $RepositoryRoot "release"
$ArchiveDir = Join-Path $RepositoryRoot "exe버전관리"
$SigningKeyPath = Join-Path $PrototypeRoot $SigningKey
$SigningPublicKeyPath = "$SigningKeyPath.pub"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw ($Message + " - exit code: " + $LASTEXITCODE)
    }
}

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "== $Message"
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $VenvPython = Join-Path $RepositoryRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $PythonExe = $VenvPython
    } else {
        $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $PythonCommand) { throw "Python 3.12를 찾지 못했습니다." }
        $PythonExe = $PythonCommand.Source
    }
}
$PythonVersion = & $PythonExe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0 -or [string]$PythonVersion -ne "3.12") {
    throw "Python sidecar는 검증된 Python 3.12로 빌드해야 합니다. 현재: $PythonVersion ($PythonExe)"
}
$LocalTauriCli = Join-Path $PrototypeRoot 'node_modules\.bin\tauri.cmd'
$UseLocalTauri = [string]::IsNullOrWhiteSpace($PnpmExe) -and (Test-Path -LiteralPath $LocalTauriCli)
if (-not $UseLocalTauri -and [string]::IsNullOrWhiteSpace($PnpmExe)) {
    $PnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($PnpmCommand) {
        $PnpmExe = $PnpmCommand.Source
    } else {
        $BundledPnpm = "C:\Users\kain9\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
        if (-not (Test-Path -LiteralPath $BundledPnpm)) { throw "pnpm을 찾지 못했습니다." }
        $PnpmExe = $BundledPnpm
    }
}

if (-not (Test-Path -LiteralPath $SigningKeyPath)) {
    throw "자동 업데이트 서명 개인키를 찾지 못했습니다: $SigningKeyPath"
}
if (-not (Test-Path -LiteralPath $SigningPublicKeyPath)) {
    throw "자동 업데이트 서명 공개키를 찾지 못했습니다: $SigningPublicKeyPath"
}
$SigningPublicKey = (Get-Content -Raw -LiteralPath $SigningPublicKeyPath).Trim()
$UpdateConfig = Get-Content -Raw -LiteralPath (Join-Path $PrototypeRoot "update-config.json") | ConvertFrom-Json
if ($SigningPublicKey -ne [string]$UpdateConfig.app.public_key) {
    throw "서명 공개키와 update-config.json의 공개키가 다릅니다."
}

Set-Location -LiteralPath $PrototypeRoot
$env:PYTHONPATH = $RepositoryRoot

Write-Step "버전 확인"
$VersionFiles = @(
    @{ Path = "package.json"; Pattern = ('"version"\s*:\s*"{0}"' -f [regex]::Escape($InternalVersion)) },
    @{ Path = "src-tauri\Cargo.toml"; Pattern = ('version\s*=\s*"{0}"' -f [regex]::Escape($InternalVersion)) },
    @{ Path = "src-tauri\tauri.conf.json"; Pattern = [regex]::Escape("$ProductName $DisplayVersion") },
    @{ Path = "src\App.tsx"; Pattern = [regex]::Escape("const VERSION = `"$DisplayVersion`"") },
    @{ Path = "backend\full_features.py"; Pattern = [regex]::Escape("APP_VERSION = `"$DisplayVersion`"") }
)
foreach ($Item in $VersionFiles) {
    if (-not (Select-String -LiteralPath $Item.Path -Pattern $Item.Pattern -Quiet)) {
        throw "버전 불일치: $($Item.Path)"
    }
}

Write-Step "의존성 확인"
Invoke-Checked { & $PythonExe -c "import PIL, PyInstaller, pythoncom, win32com.client; print('Python dependencies ok')" } "Python 빌드 의존성 확인 실패"

Write-Step "사용자 매뉴얼 변경 검토 확인"
Invoke-Checked { node ..\매뉴얼\도구\build-manual.cjs --check } "매뉴얼 변경 검토 확인 실패"

Write-Step "Python 테스트"
Invoke-Checked { & $PythonExe -m unittest discover -s backend -p "test_*.py" -q } "Python 테스트 실패"
Invoke-Checked { & $PythonExe -m unittest discover -s ..\tests -p "test_line_spacing.py" -q } "자간 정리 테스트 실패"

Write-Step "Python COM sidecar 빌드"
New-Item -ItemType Directory -Force -Path $SidecarBinDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
Invoke-Checked {
    & $PythonExe -m PyInstaller --clean --noconfirm --workpath $SidecarWork --distpath $SidecarDist $SidecarSpec
} "Python sidecar 빌드 실패"
$BuiltSidecar = Join-Path $SidecarDist "jb_hwp_backend.exe"
if (-not (Test-Path -LiteralPath $BuiltSidecar)) { throw "빌드된 sidecar를 찾지 못했습니다: $BuiltSidecar" }
$SidecarSizeMb = (Get-Item -LiteralPath $BuiltSidecar).Length / 1MB
if ($SidecarSizeMb -gt 75) {
    throw ("Python sidecar 용량이 비정상적으로 큽니다: {0:N1} MiB. 빌드 환경과 포함된 의존성을 확인하세요." -f $SidecarSizeMb)
}
Copy-Item -LiteralPath $BuiltSidecar -Destination $SidecarBin -Force

Write-Step "sidecar 스모크 테스트"
Invoke-Checked { & $PythonExe (Join-Path $PrototypeRoot "backend\smoke_sidecar.py") $SidecarBin } "Python sidecar 스모크 테스트 실패"

Write-Step "프론트엔드 및 Rust 검사"
if ($UseLocalTauri) {
    Invoke-Checked { npm run build } "프론트엔드 빌드 실패"
} else {
    Invoke-Checked { & $PnpmExe build } "프론트엔드 빌드 실패"
}
Write-Step "사용자 매뉴얼 화면·HTML·PDF 갱신"
$PreviousManualPython = $env:MANUAL_PYTHON
try {
    $env:MANUAL_PYTHON = $PythonExe
    Invoke-Checked { node ..\매뉴얼\도구\build-manual.cjs } "사용자 매뉴얼 생성 실패"
} finally {
    $env:MANUAL_PYTHON = $PreviousManualPython
}
Push-Location -LiteralPath $TauriRoot
try {
    Invoke-Checked { cargo check --release } "Rust 검사 실패"
} finally {
    Pop-Location
}

Write-Step "Tauri NSIS 설치파일 빌드"
if ($UseLocalTauri) {
    $BuildConfigPath = Join-Path $BuildRoot 'tauri-local-build.json'
    $BuildConfig = @{ build = @{ beforeBuildCommand = 'npm run build' } } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($BuildConfigPath, $BuildConfig, (New-Object Text.UTF8Encoding($false)))
    Invoke-Checked { & $LocalTauriCli build --bundles nsis --ci --config $BuildConfigPath } "Tauri 설치파일 빌드 실패"
} else {
    Invoke-Checked { & $PnpmExe tauri build --bundles nsis } "Tauri 설치파일 빌드 실패"
}
$BundleDir = Join-Path $TauriRoot "target\release\bundle\nsis"
$Installer = Get-ChildItem -LiteralPath $BundleDir -File -Filter "*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $Installer) { throw "NSIS 설치파일을 찾지 못했습니다: $BundleDir" }
$SignerPasswordArgument = "--password=$SigningPassword"
Invoke-Checked {
    if ($UseLocalTauri) {
        & $LocalTauriCli signer sign -f $SigningKeyPath $SignerPasswordArgument $Installer.FullName
    } else {
        & $PnpmExe tauri signer sign -f $SigningKeyPath $SignerPasswordArgument $Installer.FullName
    }
} "Tauri 설치파일 서명 실패"

$InstallerSignature = Get-Item -LiteralPath ($Installer.FullName + ".sig") -ErrorAction SilentlyContinue
if (-not $InstallerSignature) {
    throw "자동 업데이트 서명 파일을 찾지 못했습니다: $($Installer.FullName).sig"
}

Write-Step "릴리스 파일 정리"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ReleaseExe = Join-Path $ReleaseDir "$ProductName $DisplayVersion 설치파일.exe"
$ReleaseZip = Join-Path $ReleaseDir "$ProductName $DisplayVersion.zip"
$ReleaseSig = "$ReleaseExe.sig"
$GithubExe = Join-Path $ReleaseDir "JBEduForm_v${InternalVersion}_Setup.exe"
$GithubZip = Join-Path $ReleaseDir "JBEduForm_v$InternalVersion.zip"
$GithubSig = "$GithubExe.sig"
$ArchiveExe = Join-Path $ArchiveDir "JBEdu_FORM_$DisplayVersion.exe"
$ArchiveZip = Join-Path $ArchiveDir "JBEdu_FORM_$DisplayVersion.zip"
$ArchiveSig = "$ArchiveExe.sig"
$MarkerFile = Join-Path $ReleaseDir "업데이트_게시글_표식_$DisplayVersion.txt"
Copy-Item -LiteralPath $Installer.FullName -Destination $ReleaseExe -Force
Copy-Item -LiteralPath $InstallerSignature.FullName -Destination $ReleaseSig -Force
Compress-Archive -LiteralPath $ReleaseExe -DestinationPath $ReleaseZip -Force
Copy-Item -LiteralPath $ReleaseExe -Destination $GithubExe -Force
Copy-Item -LiteralPath $ReleaseZip -Destination $GithubZip -Force
Copy-Item -LiteralPath $ReleaseSig -Destination $GithubSig -Force
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
Copy-Item -LiteralPath $ReleaseExe -Destination $ArchiveExe -Force
Copy-Item -LiteralPath $ReleaseZip -Destination $ArchiveZip -Force
Copy-Item -LiteralPath $ReleaseSig -Destination $ArchiveSig -Force
$Signature = (Get-Content -Raw -LiteralPath $ReleaseSig).Trim()
$Marker = "[업데이트정보]id=$($UpdateConfig.app.app_id)|앱=$ProductName|버전=$InternalVersion|다운로드=<교육청 게시판 ZIP 첨부 링크>|서명=$Signature"
[IO.File]::WriteAllText($MarkerFile, $Marker, (New-Object Text.UTF8Encoding($false)))

Write-Step "완료"
Write-Host "표시 버전: $DisplayVersion"
Write-Host "내부 버전: $InternalVersion"
Write-Host "설치파일: $ReleaseExe"
Write-Host "압축파일: $ReleaseZip"
Write-Host "버전 보관 설치파일: $ArchiveExe"
Write-Host "GitHub 업로드 설치파일: $GithubExe"
Write-Host "업데이트 서명: $GithubSig"
Write-Host "게시판 표식 초안: $MarkerFile"
