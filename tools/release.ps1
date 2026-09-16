# Publish a new version to GitHub Releases. Installed copies pick it up
# automatically (they check for updates every few hours).
#
#   1. Bump __version__ in unidesk\__init__.py and commit your changes.
#   2. powershell -ExecutionPolicy Bypass -File tools\release.ps1 -Notes "What changed"
param(
    [string]$Notes = "",
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (git status --porcelain) { throw "Commit your changes first (git status is not clean)." }
if (-not $SkipBuild) { & "$PSScriptRoot\build.ps1" }
python "$PSScriptRoot\publish_release.py" --notes $Notes
if ($LASTEXITCODE) { throw "publishing failed" }
