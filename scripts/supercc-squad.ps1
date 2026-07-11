param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]] $Rest
)

$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path $PSScriptRoot 'supercc_squad.py'

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    & $python.Source $scriptPath @Rest
    exit $LASTEXITCODE
}

$python3 = Get-Command python3 -ErrorAction SilentlyContinue
if ($python3) {
    & $python3.Source $scriptPath @Rest
    exit $LASTEXITCODE
}

$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {
    & $py.Source -3 $scriptPath @Rest
    exit $LASTEXITCODE
}

Write-Error 'supercc-squad.ps1: python/python3/py is required to run supercc_squad.py'
exit 127
