$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectRoot

$NeedsInstall = -not (Test-Path -LiteralPath ".venv")
if ($NeedsInstall) {
    python -m venv .venv
}

$PythonExe = ".\.venv\Scripts\python.exe"
& $PythonExe -c "import fastapi, uvicorn, pydantic, serial" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $PythonExe -m pip install -r requirements.txt
}

$BindAddress = if ($env:YINBAN_HOST) { $env:YINBAN_HOST } else { "0.0.0.0" }
$ServerPort = if ($env:YINBAN_PORT) { $env:YINBAN_PORT } else { "8000" }

Write-Host ""
Write-Host "Yinban is starting..."
Write-Host "Local computer: http://127.0.0.1:$ServerPort"

try {
    $LanAddress = Get-NetIPConfiguration |
        Where-Object { $_.IPv4DefaultGateway -ne $null } |
        Select-Object -First 1 -ExpandProperty IPv4Address |
        Select-Object -ExpandProperty IPAddress
    if ($LanAddress) {
        Write-Host "Other computer on the same network: http://${LanAddress}:$ServerPort"
    }
} catch {
    Write-Host "To use another computer, open this computer's IPv4 address on port $ServerPort."
}

Write-Host "Keep this window open while using Yinban."
Write-Host ""

& $PythonExe -m uvicorn app.main:app --host $BindAddress --port $ServerPort
