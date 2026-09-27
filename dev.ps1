# Starts the Prospector FastAPI backend (in a new window) and the Next.js
# frontend (in this window). Run from the repo root:
#
#   .\dev.ps1
#
# Stop the frontend with Ctrl+C; close the backend window separately.

$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; python -m uvicorn server:app --port 8000"

Push-Location (Join-Path $root "web")
try {
    if (-not (Test-Path "node_modules\.bin\next.cmd")) {
        Write-Host "Installing frontend packages (first run only)..."
        npm install
    }
    npm run dev
} finally {
    Pop-Location
}
