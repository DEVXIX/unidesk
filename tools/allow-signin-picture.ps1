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
    & icacls $dir /remove:g $owner /t | Out-Null
    "revoked: $owner no longer writes $dir"
    return
}

# Why this needs more than one icacls: the folder's ACL holds SYSTEM and the
# built-in Administrator ACCOUNT - not the Administrators group. An elevated
# session running as any other account is therefore not on the list at all, and
# rewriting an ACL needs a right the list does not give it. icacls answers
# "Access is denied", exit 5, however elevated the shell is.
#
# So ownership is taken first (an administrator may always do that, which is
# what stops a locked-out folder being unrecoverable), the grant is written,
# and ownership is handed straight back to SYSTEM. What is left behind is the
# folder exactly as it was plus one entry: this account, Modify, here only.
$owned = $false
& icacls $dir /grant "${owner}:(OI)(CI)M" /t | Out-Null
if ($LASTEXITCODE) {
    "the folder will not take a grant from this account; taking ownership first"
    # /a gives it to Administrators rather than to whoever is running this, so
    # the machine is not left depending on one account.
    & takeown /f $dir /a /r /d Y | Out-Null
    if ($LASTEXITCODE) { throw "could not take ownership of $dir (exit $LASTEXITCODE)" }
    $owned = $true
    & icacls $dir /grant "${owner}:(OI)(CI)M" /t | Out-Null
    if ($LASTEXITCODE) { throw "icacls still refused after taking ownership: exit $LASTEXITCODE" }
}

if ($owned) {
    # Back to stock. The grant above survives this: an entry on the list does
    # not depend on who owns the folder.
    & icacls $dir /setowner "NT AUTHORITY\SYSTEM" /t | Out-Null
    if ($LASTEXITCODE) {
        "note: the grant is in place, but ownership stayed with Administrators"
    } else {
        "ownership handed back to SYSTEM"
    }
}

"granted: $owner may now replace its own sign-in picture"
"folder:  $dir"
""
"Turn it on in unidesk: Settings > 'Draw your sign-in picture', with your"
"GitHub name next to it. The picture is redrawn on the same timer as the lock"
"screen, in a different shape each time."
