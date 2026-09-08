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

& $PythonExe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
