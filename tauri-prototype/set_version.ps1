param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^\d+\.\d+\.\d+$')]
    [string]$Version
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$DisplayVersion = "v.$Version"
$ProductName = (Get-Content -Raw -LiteralPath (Join-Path $ProjectRoot "src-tauri\tauri.conf.json") | ConvertFrom-Json).productName

function Set-FileText {
    param(
        [string]$Path,
        [string]$Pattern,
        [string]$Replacement
    )

    $FullPath = Join-Path $ProjectRoot $Path
    $Text = [IO.File]::ReadAllText($FullPath)
    if ($Text -notmatch $Pattern) {
        throw "$Path 에서 버전 표기를 찾지 못했습니다."
    }
    $Updated = [regex]::Replace($Text, $Pattern, $Replacement, 1)
    [IO.File]::WriteAllText($FullPath, $Updated, (New-Object Text.UTF8Encoding($false)))
    Write-Host "  $Path"
}

Write-Host "내부 버전을 $Version, 화면 표시를 $DisplayVersion 형태로 맞춥니다."

Set-FileText "package.json" `
    '"version"\s*:\s*"\d+\.\d+\.\d+"' `
    ('"version": "{0}"' -f $Version)

Set-FileText "src-tauri\Cargo.toml" `
    '(?m)^version = "\d+\.\d+\.\d+"' `
    ('version = "{0}"' -f $Version)

Set-FileText "src-tauri\Cargo.lock" `
    '(?m)(name = "jb-hwp-helper"\r?\nversion = )"\d+\.\d+\.\d+"' `
    ('${1}"' + $Version + '"')

Set-FileText "src-tauri\tauri.conf.json" `
    '"version"\s*:\s*"\d+\.\d+\.\d+"' `
    ('"version":  "{0}"' -f $Version)


Set-FileText "src-tauri\tauri.conf.json" `
    '("title"\s*:\s*")[^"]+("\s*,)' `
    ('${1}' + $ProductName + ' ' + $DisplayVersion + '${2}')

Set-FileText "src\App.tsx" `
    'const VERSION = "v\.\d+\.\d+\.\d+";' `
    ('const VERSION = "{0}";' -f $DisplayVersion)

Set-FileText "backend\full_features.py" `
    'APP_VERSION = "v\.\d+\.\d+\.\d+"' `
    ('APP_VERSION = "{0}"' -f $DisplayVersion)

Set-FileText "index.html" `
    '(<title>)[^<]+(</title>)' `
    ('${1}' + $ProductName + ' ' + $DisplayVersion + '${2}')

Write-Host ""
Write-Host "다음 단계"
Write-Host "  git add -A"
Write-Host "  git commit -m `"chore: 버전 $Version`""
Write-Host "  git tag v$Version"
Write-Host "  git push"
Write-Host "  git push origin v$Version"
