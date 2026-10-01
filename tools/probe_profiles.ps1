# Run tools/probe_profiles.py in the WSL Ubuntu test environment (it has all dependencies).
# It asks for your Anker login in this window; nothing is stored.
$repo = Split-Path $PSScriptRoot -Parent
$wslRepo = (wsl.exe -d Ubuntu -u root -- wslpath -a ($repo -replace '\\', '/')).Trim()
wsl.exe -d Ubuntu -u root -- bash -c "cd '$wslRepo' && PYTHONPATH=. /root/ha-test-venv/bin/python tools/probe_profiles.py"
