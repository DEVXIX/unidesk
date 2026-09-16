# Publish a new version to GitHub Releases. Installed copies pick it up
# automatically (they check for updates every few hours).
#
#   1. Bump __version__ in unidesk\__init__.py and commit your changes.
#   2. powershell -ExecutionPolicy Bypass -File tools\release.ps1 -Notes "What changed"
#
# Uses $env:GITHUB_TOKEN if set, otherwise the GitHub login git already has
# (Git Credential Manager).
param(
    [string]$Notes = "",
    [switch]$SkipBuild
)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$repo = "DEVXIX/unidesk"
$version = (Select-String -Path unidesk\__init__.py -Pattern '__version__ = "(.+)"').Matches[0].Groups[1].Value
$tag = "v$version"
Write-Host "Releasing unidesk $tag"

if (git status --porcelain) { throw "Commit your changes first (git status is not clean)." }
if (git tag --list $tag) { throw "$tag already exists. Bump __version__ in unidesk\__init__.py." }

if (-not $SkipBuild) { & "$PSScriptRoot\build.ps1" }
$setup = Get-Item "dist\unidesk-setup-$version.exe"

# GitHub token: env var, or the one git's credential manager stores.
$token = $env:GITHUB_TOKEN
if (-not $token) {
    # PowerShell pipes add a BOM / CRLF that git rejects, so talk to it directly.
    $psi = New-Object System.Diagnostics.ProcessStartInfo "git", "credential fill"
    $psi.RedirectStandardInput = $true
    $psi.RedirectStandardOutput = $true
    $psi.UseShellExecute = $false
    $git = [System.Diagnostics.Process]::Start($psi)
    $git.StandardInput.NewLine = "`n"
    $git.StandardInput.Write("protocol=https`nhost=github.com`n`n")
    $git.StandardInput.Close()
    $cred = $git.StandardOutput.ReadToEnd() -split "`n"
    $git.WaitForExit()
    $token = (($cred | Where-Object { $_ -like "password=*" }) -replace "^password=", "").Trim()
}
if (-not $token) { throw "No GitHub credentials. Set GITHUB_TOKEN or run 'git push' once to sign in." }
$headers = @{ Authorization = "Bearer $token"; Accept = "application/vnd.github+json"; "User-Agent" = "unidesk-release" }

Write-Host "Pushing code and tag"
git tag -a $tag -m "unidesk $version"
git push origin HEAD
git push origin $tag

if (-not $Notes) { $Notes = "unidesk $version" }
$body = @{ tag_name = $tag; name = "unidesk $version"; body = $Notes; draft = $false; prerelease = $false } | ConvertTo-Json
$release = Invoke-RestMethod -Method Post -Uri "https://api.github.com/repos/$repo/releases" -Headers $headers -Body $body -ContentType "application/json"

Write-Host ("Uploading {0} ({1:N1} MB)" -f $setup.Name, ($setup.Length / 1MB))
$upload = "https://uploads.github.com/repos/$repo/releases/$($release.id)/assets?name=$($setup.Name)"
Invoke-RestMethod -Method Post -Uri $upload -Headers $headers -InFile $setup.FullName -ContentType "application/octet-stream" | Out-Null

Write-Host "Done: $($release.html_url)"
