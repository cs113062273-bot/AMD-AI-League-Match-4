$ErrorActionPreference = 'Stop'
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
& .\.venv\Scripts\python.exe -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) { throw 'CUDA torch install failed' }
& .\.venv\Scripts\python.exe -m pip install --no-deps -r requirements-runtime.lock
if ($LASTEXITCODE -ne 0) { throw 'Locked runtime installation failed' }
& .\.venv\Scripts\python.exe -m pip install pytest==9.1.1
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& .\.venv\Scripts\python.exe scripts/fetch_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model download failed' }
& .\.venv\Scripts\python.exe scripts/gpu_smoke_test.py
if ($LASTEXITCODE -ne 0) { throw 'GPU validation failed' }
