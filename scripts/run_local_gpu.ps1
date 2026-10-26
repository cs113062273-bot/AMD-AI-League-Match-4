$ErrorActionPreference = 'Stop'
$env:APERTURE_MODEL = (Join-Path $PSScriptRoot '..\models\qwen')
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
& (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe') (Join-Path $PSScriptRoot '..\app.py') --serve
if ($LASTEXITCODE -ne 0) { throw 'Resident model failed' }
