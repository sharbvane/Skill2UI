$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $project
try {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            & uv venv .venv --python python
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
        }
        & uv pip install --python .venv\Scripts\python.exe -r requirements.lock -e '.[mcp]' --no-deps
    } else {
        if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
            & python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
        }
        & .venv\Scripts\python.exe -m ensurepip --upgrade
        if ($LASTEXITCODE -ne 0) { throw 'pip setup failed.' }
        & .venv\Scripts\python.exe -m pip install -r requirements.lock -e '.[mcp]' --no-deps
    }
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    & .venv\Scripts\python.exe -m skill2ui --version
    if ($LASTEXITCODE -ne 0) { throw 'Installation check failed.' }
} finally { Pop-Location }
