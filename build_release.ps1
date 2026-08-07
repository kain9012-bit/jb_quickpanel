param(
    [string]$Version = "v3.4",
    [switch]$CheckOnly,
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = "C:\Users\kain9\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$PyInstallerPackages = "C:\work\pdf_merge_tool\.venv\Lib\site-packages"
$TkRoot = "C:\work\tk_runtime\tcl"
$VendorPywin32 = Join-Path $Root "vendor\pywin32"
$SpecPath = (Get-ChildItem -LiteralPath $Root -Filter "*_$Version.spec" | Select-Object -First 1).FullName
$SplashPath = $null
if ($SpecPath) {
    $SplashLine = Select-String -LiteralPath $SpecPath -Pattern "assets/splash/[^']+\.png" | Select-Object -First 1
    if ($SplashLine) {
        $SplashRelative = [regex]::Match($SplashLine.Line, "assets/splash/[^']+\.png").Value
        $SplashPath = Join-Path $Root ($SplashRelative -replace "/", "\")
    }
}
$AppPath = Join-Path $Root "app($Version).py"
$SourcePackage = if ($Version -eq "v2.2") {
    Join-Path $Root "src\jb_quickpanel_v22"
} elseif ($Version -eq "v2.3") {
    Join-Path $Root "src\jb_quickpanel_v23"
} elseif ($Version -eq "v2.4") {
    Join-Path $Root "src\jb_quickpanel_v24"
} elseif ($Version -eq "v2.5") {
    Join-Path $Root "src\jb_quickpanel_v25"
} elseif ($Version -eq "v2.6") {
    Join-Path $Root "src\jb_quickpanel_v26"
} elseif ($Version -eq "v2.7") {
    Join-Path $Root "src\jb_quickpanel_v27"
} elseif ($Version -eq "v2.8") {
    Join-Path $Root "src\jb_quickpanel_v28"
} elseif ($Version -eq "v2.9") {
    Join-Path $Root "src\jb_quickpanel_v29"
} elseif ($Version -eq "v3.0") {
    Join-Path $Root "src\jb_quickpanel_v30"
} elseif ($Version -eq "v3.1") {
    Join-Path $Root "src\jb_quickpanel_v31"
} elseif ($Version -eq "v3.2") {
    Join-Path $Root "src\jb_quickpanel_v32"
} elseif ($Version -eq "v3.3") {
    Join-Path $Root "src\jb_quickpanel_v33"
} else {
    Join-Path $Root "src\jb_quickpanel"
}
$ArchiveDir = (Get-ChildItem -LiteralPath $Root -Directory -Filter "exe*" | Select-Object -First 1).FullName
$DistExe = $null
$ArchiveExe = $null
$ArchiveZip = $null

function Assert-PathExists {
    param(
        [string]$Path,
        [string]$Label
    )
    if ([string]::IsNullOrWhiteSpace($Path)) {
        throw "$Label path is empty."
    }
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "$Label path not found: $Path"
    }
}

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "== $Message"
}

Set-Location -LiteralPath $Root

Write-Step "Path check"
Assert-PathExists $PythonExe "Python"
Assert-PathExists $PyInstallerPackages "PyInstaller packages"
Assert-PathExists (Join-Path $TkRoot "tcl8.6") "Tcl"
Assert-PathExists (Join-Path $TkRoot "tk8.6") "Tk"
Assert-PathExists $VendorPywin32 "pywin32 vendor"
Assert-PathExists (Join-Path $VendorPywin32 "pywin32_system32\pythoncom312.dll") "pythoncom312.dll"
Assert-PathExists (Join-Path $VendorPywin32 "pywin32_system32\pywintypes312.dll") "pywintypes312.dll"
Assert-PathExists $SpecPath "Spec"
Assert-PathExists $AppPath "app"
Assert-PathExists $SourcePackage "source package"
Assert-PathExists $ArchiveDir "Archive directory"
if ($SplashPath) {
    Assert-PathExists $SplashPath "Splash image"
}

$env:TCL_LIBRARY = Join-Path $TkRoot "tcl8.6"
$env:TK_LIBRARY = Join-Path $TkRoot "tk8.6"
$env:PYTHONPATH = @(
    $PyInstallerPackages,
    $VendorPywin32,
    (Join-Path $VendorPywin32 "win32"),
    (Join-Path $VendorPywin32 "win32\lib"),
    (Join-Path $VendorPywin32 "pywin32_system32")
) -join ";"
$env:PATH = (Join-Path $VendorPywin32 "pywin32_system32") + ";" + $env:PATH

Write-Step "Syntax check"
$SyntaxFiles = @(
    $AppPath,
    (Join-Path $SourcePackage "core\runtime.py"),
    (Join-Path $SourcePackage "features\registry.py"),
    (Join-Path $SourcePackage "features\cell_text.py"),
    (Join-Path $SourcePackage "features\auto_format.py"),
    (Join-Path $SourcePackage "bridges\hwp_bridge.py"),
    (Join-Path $SourcePackage "bridges\wxs_bridge.py"),
    (Join-Path $SourcePackage "ui\app_window.py"),
    (Join-Path $SourcePackage "services\app_config.py")
)
$OptionalSyntaxFiles = @(
    (Join-Path $SourcePackage "features\untagged_report.py"),
    (Join-Path $SourcePackage "features\document_preview.py"),
    (Join-Path $SourcePackage "features\cell_images.py"),
    (Join-Path $SourcePackage "features\global_hotkeys.py"),
    (Join-Path $SourcePackage "ui\hotkey_dialog.py"),
    (Join-Path $SourcePackage "services\user_content.py")
)
foreach ($OptionalFile in $OptionalSyntaxFiles) {
    if (Test-Path -LiteralPath $OptionalFile) {
        $SyntaxFiles += $OptionalFile
    }
}
& $PythonExe -m py_compile $SyntaxFiles

if ($CheckOnly) {
    Write-Step "Check complete"
    Write-Host "CheckOnly mode: exe build was not executed."
    exit 0
}

Write-Step "PyInstaller build"
& $PythonExe -m PyInstaller --clean --noconfirm $SpecPath

$DistExe = (Get-ChildItem -LiteralPath (Join-Path $Root "dist") -Filter "*_$Version.exe" | Select-Object -First 1).FullName
Assert-PathExists $DistExe "Built exe"

if (-not $SkipSmokeTest) {
    Write-Step "Smoke test"
    $process = Start-Process -FilePath $DistExe -PassThru
    Start-Sleep -Seconds 5
    if ($process.HasExited) {
        throw "exe exited immediately. Exit code: $($process.ExitCode)"
    }
    Stop-Process -Id $process.Id -Force
}

Write-Step "Archive files"
New-Item -ItemType Directory -Force -Path $ArchiveDir | Out-Null
$ArchiveExe = Join-Path $ArchiveDir (Split-Path -Leaf $DistExe)
$ArchiveZip = [System.IO.Path]::ChangeExtension($ArchiveExe, ".zip")
Copy-Item -LiteralPath $DistExe -Destination $ArchiveExe -Force
Compress-Archive -LiteralPath $DistExe -DestinationPath $ArchiveZip -Force

Write-Step "Done"
Write-Host "exe: $ArchiveExe"
Write-Host "zip: $ArchiveZip"
