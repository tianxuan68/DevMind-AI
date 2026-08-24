# DevMind-AI release pack script (Windows PowerShell 5+)
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DateTag = Get-Date -Format "yyyyMMdd_HHmmss"
$DistDir = Join-Path $Root "dist\release"
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

Write-Host "==> [1/2] build frontend"
Push-Location (Join-Path $Root "front")
npm ci
if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
npm run build
if ($LASTEXITCODE -ne 0) { throw "npm run build failed" }
Pop-Location

Write-Host "==> [2/2] pack zips"
$FrontZip = Join-Path $DistDir "devmind-ai-frontend-$DateTag.zip"
$BackendZip = Join-Path $DistDir "devmind-ai-backend-$DateTag.zip"

if (Test-Path $FrontZip) { Remove-Item $FrontZip -Force }
if (Test-Path $BackendZip) { Remove-Item $BackendZip -Force }

Compress-Archive -Path (Join-Path $Root "front\dist\*") -DestinationPath $FrontZip

Push-Location $Root
try {
    tar -a -cf $BackendZip `
        --exclude=internal_kb_qa/models `
        --exclude=**/__pycache__ `
        --exclude=**/.venv `
        --exclude=**/node_modules `
        --exclude=data/uploads `
        --exclude=logs `
        backend base internal_kb_qa config.ini pyproject.toml uv.lock sql docker scripts locust_test.py
    if ($LASTEXITCODE -ne 0) { throw "tar failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done."
Write-Host "  frontend: $FrontZip"
Write-Host "  backend:  $BackendZip"
