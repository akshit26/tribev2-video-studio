param([switch]$Stop, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$studioRoot = $PSScriptRoot
$studioPython = Join-Path $studioRoot '.venv\Scripts\python.exe'
$studioLogs = Join-Path $studioRoot 'results\studio'
$studioUrl = 'http://127.0.0.1:8765'
$studioScript = Join-Path $studioRoot 'studio_server.py'
if ($Stop) {
    # Verify the executable and absolute script path; never trust a stale PID.
    $studioOwned = @(Get-CimInstance Win32_Process | Where-Object {
        $_.Name -eq 'python.exe' -and $_.CommandLine -and
        ($_.CommandLine.Contains($studioScript) -or
         ($_.ExecutablePath -eq $studioPython -and $_.CommandLine -match '(?:^|\s|\")studio_server\.py(?:\s|\"|$)'))
    })
    $studioOwnedIds = @($studioOwned | ForEach-Object { $_.ProcessId })
    foreach ($studioWorker in ($studioOwned | Where-Object { $_.ParentProcessId -notin $studioOwnedIds })) {
        if (Get-Process -Id $studioWorker.ProcessId -ErrorAction SilentlyContinue) {
            & taskkill.exe /PID $studioWorker.ProcessId /T /F | Out-Null
        }
    }
    Write-Host 'Studio stopped. Saved reports are kept.'
    exit 0
}
if (-not (Test-Path -LiteralPath $studioPython)) {
    throw 'The Python environment is missing. Follow STUDIO_GUIDE.md to install it.'
}
try {
    $studioHealth = Invoke-RestMethod -Uri "$studioUrl/api/system" -TimeoutSec 3
    if ($studioHealth.profiles[0].id -eq 'compact') {
        if (-not $NoBrowser) { Start-Process $studioUrl }
        exit 0
    }
} catch { }
New-Item -ItemType Directory -Path $studioLogs -Force | Out-Null
$studioExisting = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'python.exe' -and $_.CommandLine -and $_.CommandLine.Contains($studioScript)
})
if ($studioExisting.Count -gt 0) {
    throw 'Studio is already starting or not responding. Use Stop Studio.cmd, then Start Studio.cmd.'
}
$studioProcess = Start-Process -FilePath $studioPython -ArgumentList ('"' + $studioScript + '"') -WorkingDirectory $studioRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $studioLogs 'server_stdout.log') -RedirectStandardError (Join-Path $studioLogs 'server_stderr.log') -PassThru
$studioProcess.Id | Set-Content -LiteralPath (Join-Path $studioLogs 'server.pid')
$studioProcess.PriorityClass = 'BelowNormal'
for ($studioAttempt = 0; $studioAttempt -lt 30; $studioAttempt++) {
    Start-Sleep -Seconds 1
    if ($studioProcess.HasExited) { throw 'Studio exited. See results\studio\server_stderr.log.' }
    try {
        $studioHealth = Invoke-RestMethod -Uri "$studioUrl/api/system" -TimeoutSec 2
        if ($studioHealth.profiles[0].id -eq 'compact') {
            if (-not $NoBrowser) { Start-Process $studioUrl }
            exit 0
        }
    } catch { }
}
throw 'The studio could not start. See results\studio\server_stderr.log.'
