param(
    [string]$Version = "v3.4",
    [string]$PythonExe = "",
    [switch]$CheckOnly,
    [switch]$RunSmokeTest
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$AppPath = Join-Path $Root "app.py"
$SourcePackage = Join-Path $Root "src\jb_quickpanel"
$SpecPath = (Get-ChildItem -LiteralPath $Root -File -Filter "*_$Version.spec" | Select-Object -First 1).FullName
$ReleaseDir = Join-Path $Root "release"
$DistExe = $null

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$Label
    )
    if ([string]::IsNullOrWhiteSpace($Path) -or -not (Test-Path -LiteralPath $Path)) {
        throw "$Label not found: $Path"
    }
}

function Invoke-Checked {
    param(
        [scriptblock]$Command,
        [string]$FailureMessage
    )
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code: $LASTEXITCODE)"
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message"
}

if ([string]::IsNullOrWhiteSpace($PythonExe)) {
    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $VenvPython) {
        $PythonExe = $VenvPython
    } else {
        $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
        if (-not $PythonCommand) {
            throw "Python not found. Install Python 3.12 or create .venv first."
        }
        $PythonExe = $PythonCommand.Source
    }
}

Set-Location -LiteralPath $Root

Write-Step "Path check"
Assert-PathExists $PythonExe "Python"
Assert-PathExists $AppPath "Application entry point"
Assert-PathExists $SourcePackage "Source package"
Assert-PathExists $SpecPath "PyInstaller spec"
Assert-PathExists (Join-Path $Root "assets\splash\app_splash_v3.4.png") "Splash image"
Assert-PathExists (Join-Path $Root "assets\icons\app_icon.ico") "Application icon"

$VersionSource = Join-Path $SourcePackage "ui\app_window.py"
$VersionLine = Select-String -LiteralPath $VersionSource -Pattern 'APP_VERSION\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $VersionLine) {
    throw "APP_VERSION was not found in $VersionSource"
}
$CodeVersion = [regex]::Match($VersionLine.Line, 'APP_VERSION\s*=\s*"([^"]+)"').Groups[1].Value
if ($CodeVersion -ne $Version) {
    throw "Version mismatch: build=$Version, source=$CodeVersion"
}

Write-Step "Dependency check"
& $PythonExe -c "import tkinter, PIL, pythoncom, win32com.client, PyInstaller; print('dependencies ok')"
if ($LASTEXITCODE -ne 0) {
    throw "Build dependencies are missing. Run: $PythonExe -m pip install -r requirements-build.txt"
}

Write-Step "Syntax check"
$SyntaxFiles = @($AppPath)
$SyntaxFiles += Get-ChildItem -LiteralPath $SourcePackage -Recurse -File -Filter "*.py" | Select-Object -ExpandProperty FullName
& $PythonExe -m py_compile $SyntaxFiles
if ($LASTEXITCODE -ne 0) {
    throw "Python syntax check failed."
}

Write-Step "Unit tests"
& $PythonExe -m unittest discover -s tests
if ($LASTEXITCODE -ne 0) {
    throw "Unit tests failed."
}

if ($CheckOnly) {
    Write-Step "Check complete"
    Write-Host "CheckOnly mode: exe build was not executed."
    exit 0
}

Write-Step "PyInstaller build"
$BuildStamp = Get-Date -Format "yyyyMMdd-HHmmss-fff"
$WorkDir = Join-Path (Join-Path $Root "build") "$Version-$BuildStamp"
$DistDir = Join-Path (Join-Path $Root "dist") "$Version-$BuildStamp"
& $PythonExe -m PyInstaller --clean --noconfirm --workpath $WorkDir --distpath $DistDir $SpecPath
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$DistExe = (Get-ChildItem -LiteralPath $DistDir -File -Filter "*_$Version.exe" | Select-Object -First 1).FullName
Assert-PathExists $DistExe "Built exe"

if ($RunSmokeTest) {
    Write-Step "Smoke test"
    $Process = Start-Process -FilePath $DistExe -PassThru -WindowStyle Hidden
    Start-Sleep -Seconds 5
    if ($Process.HasExited) {
        throw "Exe exited immediately. Exit code: $($Process.ExitCode)"
    }
    Stop-Process -Id $Process.Id -Force
}

Write-Step "Release files"
New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
$ReleaseExe = Join-Path $ReleaseDir (Split-Path -Leaf $DistExe)
$ReleaseZip = [IO.Path]::ChangeExtension($ReleaseExe, ".zip")
Copy-Item -LiteralPath $DistExe -Destination $ReleaseExe -Force
Compress-Archive -LiteralPath $DistExe -DestinationPath $ReleaseZip -Force

Write-Step "Done"
Write-Host "exe: $ReleaseExe"
Write-Host "zip: $ReleaseZip"
