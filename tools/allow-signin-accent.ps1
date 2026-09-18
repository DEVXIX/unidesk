# Let unidesk colour the sign-in screen. Run once, as administrator:
#
#   powershell -ExecutionPolicy Bypass -File tools\allow-signin-accent.ps1
#
# The "Sign in" button, the focus rings and the spinner on the Windows sign-in
# screen are drawn in the accent colour of the .DEFAULT profile - the one that
# screen runs as, before anybody has signed in. Changing your own accent in
# Settings never touches it, which is why it stays the blue Windows shipped
# with however the desk looks.
#
# This grants your account permission to set values on exactly two keys in that
# profile:
#
#   HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent
#   HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\DWM
#
# Nothing else: no other profile, no other key, no policy, and nothing here
# writes a colour - unidesk does that afterwards, from the theme, so it follows
# your wallpaper. -Revoke takes the grant back off.
#
# Administrators already hold FullControl on both keys, so this only edits
# their access lists; no ownership is taken and nothing is left changed but the
# one entry.
[CmdletBinding()]
param([switch]$Revoke)
$ErrorActionPreference = 'Stop'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$isAdmin = ([Security.Principal.WindowsPrincipal]$identity).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    throw "Run this as administrator (right-click Windows Terminal > Run as administrator)."
}

# The account being granted is whoever is signed in at the desktop, which is
# not necessarily the account running an elevated shell.
$owner = (Get-CimInstance Win32_ComputerSystem).UserName
if (-not $owner) { $owner = "$env:USERDOMAIN\$env:USERNAME" }
$account = New-Object Security.Principal.NTAccount($owner)

# Each -bor is worked out on its own line and kept in a variable. Written
# inline in an argument list, PowerShell reads "a, b, X -bor Y" as an array of
# three followed by -bor, and fails with "[System.Object[]] does not contain a
# method named 'op_BitwiseOr'".
$Rights = [System.Security.AccessControl.RegistryRights]
$opening = $Rights::ReadKey -bor $Rights::ChangePermissions
$granting = $Rights::SetValue -bor $Rights::CreateSubKey -bor $Rights::ReadKey
$readWrite = [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree
$inherit = [System.Security.AccessControl.InheritanceFlags]::ContainerInherit
$propagate = [System.Security.AccessControl.PropagationFlags]::None
$allow = [System.Security.AccessControl.AccessControlType]::Allow

$paths = @(
    '.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent',
    '.DEFAULT\Software\Microsoft\Windows\DWM'
)

foreach ($path in $paths) {
    $key = [Microsoft.Win32.Registry]::Users.OpenSubKey($path, $readWrite, $opening)
    if (-not $key) { throw "no such key: HKEY_USERS\$path" }
    try {
        $acl = $key.GetAccessControl()
        if ($Revoke) {
            [void]$acl.PurgeAccessRules($account)
        } else {
            $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
                $account, $granting, $inherit, $propagate, $allow)
            $acl.SetAccessRule($rule)
        }
        $key.SetAccessControl($acl)
        "$(if ($Revoke) { 'revoked' } else { 'granted' }): HKEY_USERS\$path"
    } finally {
        $key.Close()
    }
}

if ($Revoke) { return }

""
"unidesk will colour the sign-in screen from your theme within a few seconds,"
"and again whenever the wallpaper changes it. What it cannot change is the"
"button's shape - LogonUI draws that, and it is not a themable surface."
