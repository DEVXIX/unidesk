# Let unidesk colour the sign-in screen. Run once, as administrator:
#
#   powershell -ExecutionPolicy Bypass -File tools\allow-signin-accent.ps1
#
# The "Sign in" button, the focus rings and the spinner on the Windows sign-in
# screen are drawn in the accent colour of the .DEFAULT profile - the one the
# screen runs as before anybody has signed in. Changing your own accent in
# Settings never touches it, which is why it stays the stock blue.
#
# This grants your account write on exactly two keys in that profile:
#
#   HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent
#   HKEY_USERS\.DEFAULT\Software\Microsoft\Windows\DWM
#
# Nothing else: no other profile, no other key, no policy, and nothing here
# writes a colour - unidesk does that afterwards, from the theme. -Revoke takes
# the grant back off.
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

$paths = @(
    '.DEFAULT\Software\Microsoft\Windows\CurrentVersion\Explorer\Accent',
    '.DEFAULT\Software\Microsoft\Windows\DWM'
)

foreach ($path in $paths) {
    $key = [Microsoft.Win32.Registry]::Users.OpenSubKey(
        $path, [Microsoft.Win32.RegistryKeyPermissionCheck]::ReadWriteSubTree,
        [System.Security.AccessControl.RegistryRights]::TakeOwnership -bor
        [System.Security.AccessControl.RegistryRights]::ChangePermissions)
    if (-not $key) { throw "no such key: HKEY_USERS\$path" }
    try {
        $acl = $key.GetAccessControl()
        if ($Revoke) {
            $acl.PurgeAccessRules($account)
        } else {
            # SetValue and CreateSubKey on this key only - not the whole hive,
            # and not the right to hand the same access to anybody else.
            $rule = New-Object System.Security.AccessControl.RegistryAccessRule(
                $account,
                [System.Security.AccessControl.RegistryRights]::SetValue -bor
                [System.Security.AccessControl.RegistryRights]::CreateSubKey -bor
                [System.Security.AccessControl.RegistryRights]::ReadKey,
                [System.Security.AccessControl.InheritanceFlags]::ContainerInherit,
                [System.Security.AccessControl.PropagationFlags]::None,
                [System.Security.AccessControl.AccessControlType]::Allow)
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
"Turn it on in unidesk: Settings > 'Colour the sign-in screen like the desk'."
"The colour follows your theme, so it changes with the wallpaper. What it"
"cannot change is the button's shape - LogonUI draws that, and it is not a"
"themable surface."
