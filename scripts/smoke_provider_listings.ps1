# Smoke-test provider service-listing APIs.
# Requires: venv, Postgres, seeded catalog, uvicorn on :8000
#
# Usage:
#   cd "C:\Users\Daniyal Qais\Desktop\Pak Clean App\pak-clean-backend"
#   .\.venv\Scripts\activate
#   .\scripts\smoke_provider_listings.ps1

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

Write-Host "Running provider listing smoke test..." -ForegroundColor Cyan
.\.venv\Scripts\python.exe -m scripts.smoke_provider_listings @args
if ($LASTEXITCODE -ne 0) {
    Write-Host "Smoke test FAILED (exit $LASTEXITCODE)" -ForegroundColor Red
    exit $LASTEXITCODE
}
Write-Host "Smoke test PASSED" -ForegroundColor Green
