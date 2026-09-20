# Install one of the Don't Starve Codex pets into the local Codex pets folder.
# Run this from the repo root:  powershell -ExecutionPolicy Bypass -File .\install.ps1 -Pet wilson

param(
    [string]$Pet = "wilson"
)
$petDir = Join-Path $env:USERPROFILE ".codex\pets\$Pet"
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

New-Item -ItemType Directory -Force -Path $petDir | Out-Null
Copy-Item -LiteralPath (Join-Path $here "pets\$Pet\final\spritesheet-extended.webp") -Destination (Join-Path $petDir "spritesheet.webp") -Force
Copy-Item -LiteralPath (Join-Path $here "pets\$Pet\pet\pet.json") -Destination (Join-Path $petDir "pet.json") -Force

Write-Host "Installed to $petDir"
Get-ChildItem -LiteralPath $petDir | Select-Object Name, Length
