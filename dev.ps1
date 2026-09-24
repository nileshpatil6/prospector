# Starts the Prospector FastAPI backend (in a new window) and the Next.js
# frontend (in this window). Run from the repo root:
#
#   .\dev.ps1
#
# Stop the frontend with Ctrl+C; close the backend window separately.

$root = $PSScriptRoot

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root'; uvicorn server:app --port 8000"

Set-Location (Join-Path $root "web")
npm run dev
