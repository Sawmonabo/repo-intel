$ErrorActionPreference = "Stop"
& python (Join-Path $PSScriptRoot "install.py") @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
