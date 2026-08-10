param(
    [string]$PythonExe = "",
    [string]$PnpmExe = ""
)

$ErrorActionPreference = "Stop"
$DisplayVersion = "v4.0"
$InternalVersion = "4.0.0"
$PrototypeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepositoryRoot = Split-Path -Parent $PrototypeRoot
$TauriRoot = Join-Path $PrototypeRoot "src-tauri"
$SidecarSpec = Join-Path $PrototypeRoot "jb_hwp_backend.spec"
$SidecarBinDir = Join-Path $TauriRoot "binaries"
$SidecarBin = Join-Path $SidecarBinDir "jb_hwp_backend.exe"
$BuildRoot = Join-Path $PrototypeRoot "build-sidecar"
$SidecarWork = Join-Path $BuildRoot "work"
$SidecarDist = Join-Path $BuildRoot "dist"
$ReleaseDir = Join-Path $RepositoryRoot "release"

function Invoke-Checked {
    param([scriptblock]$Command, [string]$Message)
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Message (exit code: $LASTEXITCODE)"
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
if ([string]::IsNullOrWhiteSpace($PnpmExe)) {
    $PnpmCommand = Get-Command pnpm.cmd -ErrorAction SilentlyContinue
    if ($PnpmCommand) {
        $PnpmExe = $PnpmCommand.Source
    } else {
        $BundledPnpm = "C:\Users\kain9\.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd"
        if (-not (Test-Path -LiteralPath $BundledPnpm)) { throw "pnpm을 찾지 못했습니다." }
        $PnpmExe = $BundledPnpm
    }
}

Set-Location -LiteralPath $PrototypeRoot
$env:PYTHONPATH = $RepositoryRoot

Write-Step "버전 확인"
$VersionFiles = @(
    @{ Path = "package.json"; Pattern = '"version"\s*:\s*"4\.0\.0"' },
    @{ Path = "src-tauri\Cargo.toml"; Pattern = 'version\s*=\s*"4\.0\.0"' },
    @{ Path = "src-tauri\tauri.conf.json"; Pattern = '전북교육 한글 서식도우미 v4\.0' },
    @{ Path = "src\App.tsx"; Pattern = 'const VERSION = "v4\.0"' },
    @{ Path = "backend\full_features.py"; Pattern = 'APP_VERSION = "v4\.0"' }
)
foreach ($Item in $VersionFiles) {
    if (-not (Select-String -LiteralPath $Item.Path -Pattern $Item.Pattern -Quiet)) {
        throw "버전 불일치: $($Item.Path)"
    }
}

Write-Step "의존성 확인"
Invoke-Checked { & $PythonExe -c "import PIL, PyInstaller, pythoncom, win32com.client; print('Python dependencies ok')" } "Python 빌드 의존성 확인 실패"

Write-Step "Python 테스트"
Invoke-Checked { & $PythonExe -m unittest discover -s backend -p "test_*.py" -q } "Python 테스트 실패"

Write-Step "Python COM sidecar 빌드"
New-Item -ItemType Directory -Force -Path $SidecarBinDir | Out-Null
New-Item -ItemType Directory -Force -Path $BuildRoot | Out-Null
Invoke-Checked {
    & $PythonExe -m PyInstaller --clean --noconfirm --workpath $SidecarWork --distpath $SidecarDist $SidecarSpec
} "Python sidecar 빌드 실패"
$BuiltSidecar = Join-Path $SidecarDist "jb_hwp_backend.exe"
if (-not (Test-Path -LiteralPath $BuiltSidecar)) { throw "빌드된 sidecar를 찾지 못했습니다: $BuiltSidecar" }
Copy-Item -LiteralPath $BuiltSidecar -Destination $SidecarBin -Force

Write-Step "sidecar 스모크 테스트"
Invoke-Checked { & $PythonExe (Join-Path $PrototypeRoot "backend\smoke_sidecar.py") $SidecarBin } "Python sidecar 스모크 테스트 실패"

Write-Step "프론트엔드 및 Rust 검사"
Invoke-Checked { & $PnpmExe build } "프론트엔드 빌드 실패"
Push-Location -LiteralPath $TauriRoot
try {
    Invoke-Checked { cargo check --release } "Rust 검사 실패"
} finally {
    Pop-Location
}

Write-Step "Tauri NSIS 설치파일 빌드"
Invoke-Checked { & $PnpmExe tauri build --bundles nsis } "Tauri 설치파일 빌드 실패"
$BundleDir = Join-Path $TauriRoot "target\release\bundle\nsis"
$Installer = Get-ChildItem -LiteralPath $BundleDir -File -Filter "*.exe" |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $Installer) { throw "NSIS 설치파일을 찾지 못했습니다: $BundleDir" }

Write-Step "릴리스 파일 정리"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ReleaseExe = Join-Path $ReleaseDir "전북교육 한글 서식도우미 v4.0 설치파일.exe"
$ReleaseZip = Join-Path $ReleaseDir "전북교육 한글 서식도우미 v4.0.zip"
Copy-Item -LiteralPath $Installer.FullName -Destination $ReleaseExe -Force
Compress-Archive -LiteralPath $ReleaseExe -DestinationPath $ReleaseZip -Force

Write-Step "완료"
Write-Host "표시 버전: $DisplayVersion"
Write-Host "내부 버전: $InternalVersion"
Write-Host "설치파일: $ReleaseExe"
Write-Host "압축파일: $ReleaseZip"