param([int]$Port = 7860)
$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $PSScriptRoot
$runtimePython = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw 'Run scripts/setup.ps1 first.'
}
Push-Location -LiteralPath $project
try {
    & $runtimePython -m skill2ui serve --port $Port --open
    if ($LASTEXITCODE -ne 0) { throw 'Skill2UI failed to start.' }
} finally { Pop-Location }
