$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot
if (Get-Command python -ErrorAction SilentlyContinue) {
    python -m streamlit run dashboard/app.py
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -m streamlit run dashboard/app.py
} else {
    throw "Python is not installed or is not available on PATH."
}
