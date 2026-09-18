# Let unidesk draw your sign-in picture. Run once, as administrator:
#
#   powershell -ExecutionPolicy Bypass -File tools\allow-signin-picture.ps1
#
# Windows keeps the picture above your name on the sign-in screen in
# C:\Users\Public\AccountPictures\<your SID>\, one JPEG per size. That folder
# is readable by everyone and writable only by SYSTEM and Administrators, so an
# ordinary program - unidesk included - cannot replace what is in it.
#
# This grants your own account Modify on your own picture folder. Nothing else
# changes: not other accounts' folders, not the registry, not any policy, and
# nothing here runs afterwards. To undo it, run with -Revoke.
[CmdletBinding()]
param([switch]$Revoke)
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Run this as administrator (right-click Windows Terminal > Run as administrator)."
}

# The account being granted is the one that is signed in, which is not
# necessarily the one running an elevated shell. Prefer the desktop owner.
$owner = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $owner) { $owner = "$env:USERDOMAIN\$env:USERNAME" }
$sid = (New-Object Security.Principal.NTAccount($owner)).Translate(
    [Security.Principal.SecurityIdentifier]).Value

$dir = Join-Path 'C:\Users\Public\AccountPictures' $sid
if (-not (Test-Path -LiteralPath $dir)) {
    throw "No picture folder for $owner yet. Set any account picture once in Settings > Accounts > Your info, then run this again."
}

if ($Revoke) {
    & icacls $dir /remove:g $owner | Out-Null
    "revoked: $owner no longer writes $dir"
    return
}

# (OI)(CI) so the files inside inherit it; M is Modify, which is read, write
# and delete on those files and nothing beyond this folder.
& icacls $dir /grant "${owner}:(OI)(CI)M" | Out-Null
if ($LASTEXITCODE) { throw "icacls refused: exit $LASTEXITCODE" }

"granted: $owner may now replace its own sign-in picture"
"folder:  $dir"
""
"Turn it on in unidesk: Settings > 'Draw your sign-in picture', with your"
"GitHub name next to it. The picture is redrawn on the same timer as the lock"
"screen, in a different shape each time."
