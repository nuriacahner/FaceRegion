# Push this folder into Fusion's AddIns directory.
# FaceRegion.py is the shell - changing it needs the add-in stopped and re-run.
# fr_core.py / fr_fit.py hot-reload: pushing them takes effect on the next command.
$src = Split-Path -Parent $MyInvocation.MyCommand.Definition
$dst = Join-Path $env:APPDATA 'Autodesk\Autodesk Fusion 360\API\AddIns\FaceRegion'

New-Item -ItemType Directory -Force -Path $dst | Out-Null

$cache = Join-Path $dst '__pycache__'
if (Test-Path -LiteralPath $cache) { Remove-Item -LiteralPath $cache -Recurse -Force }

# every runtime file - keep this list in step with the imports
foreach ($f in @('FaceRegion.py', 'fr_core.py', 'fr_fit.py', 'fr_validate.py', 'FaceRegion.manifest')) {
    Copy-Item -LiteralPath (Join-Path $src $f) -Destination $dst -Force
}
Copy-Item -LiteralPath (Join-Path $src 'resources') -Destination $dst -Recurse -Force

Write-Host "Installed to $dst"
