param([Parameter(Mandatory = $true)][string]$InstallDir)

$ErrorActionPreference = 'Stop'
try {
    if (-not [IO.Path]::IsPathRooted($InstallDir)) {
        throw 'An absolute install directory is required.'
    }
    $Root = [IO.Path]::GetFullPath($InstallDir)
    $Target = [IO.Path]::GetFullPath((Join-Path $Root 'binaries\jb_hwp_backend.exe'))
    # Match the exact installed executable, not other copies or Hancom processes.
    $Processes = @(Get-Process -Name 'jb_hwp_backend' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -and [string]::Equals($_.Path, $Target, [StringComparison]::OrdinalIgnoreCase) })
    foreach ($Process in $Processes) {
        try {
            $Process.Kill()
        } catch {
            if (-not $Process.HasExited) { throw }
        }
    }
    foreach ($Process in $Processes) {
        if (-not $Process.WaitForExit(5000)) {
            throw 'The installed backend did not exit.'
        }
    }
    exit 0
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
