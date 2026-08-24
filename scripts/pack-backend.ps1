# Pack backend only (skip frontend build) - Windows PowerShell 5+
$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$DateTag = Get-Date -Format "yyyyMMdd_HHmmss"
$DistDir = Join-Path $Root "dist\release"
New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

$BackendZip = Join-Path $DistDir "devmind-ai-backend-$DateTag.zip"
if (Test-Path $BackendZip) { Remove-Item $BackendZip -Force }

Push-Location $Root
try {
    # tar streams files; avoids OOM from Compress-Archive on large trees
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

Write-Host "backend zip: $BackendZip"
