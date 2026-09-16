; Inno Setup script for unidesk. Built by tools\build.ps1.
#define AppName "unidesk"
#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6F1B7C2E-5A4D-4B8E-9C3A-2D7E1F0A9B61}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=unidesk
DefaultDirName={localappdata}\Programs\unidesk
DefaultGroupName=unidesk
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=unidesk-setup-{#AppVersion}
SetupIconFile=..\build\unidesk.ico
UninstallDisplayIcon={app}\unidesk.exe
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "startup"; Description: "Start unidesk when I sign in to Windows"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "..\dist\unidesk\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "READ-ME.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\unidesk"; Filename: "{app}\unidesk.exe"
Name: "{group}\Restore the Windows taskbar"; Filename: "{app}\unidesk.exe"; Parameters: "--restore-taskbar"
Name: "{group}\unidesk READ-ME"; Filename: "{app}\READ-ME.txt"
Name: "{group}\Uninstall unidesk"; Filename: "{uninstallexe}"
Name: "{userdesktop}\unidesk"; Filename: "{app}\unidesk.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "unidesk"; ValueData: """{app}\unidesk.exe"""; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\READ-ME.txt"; Description: "Open the READ-ME (shortcuts and setup)"; Flags: postinstall shellexec skipifsilent nowait
Filename: "{app}\unidesk.exe"; Description: "Launch unidesk"; Flags: nowait postinstall skipifsilent
; Silent installs are auto-updates: start the new version straight away.
Filename: "{app}\unidesk.exe"; Flags: nowait; Check: WizardSilent

[UninstallRun]
; Stop unidesk, then make sure the Windows taskbar is visible again.
Filename: "{cmd}"; Parameters: "/c taskkill /im unidesk.exe /f"; Flags: runhidden; RunOnceId: "StopUnidesk"
Filename: "{app}\unidesk.exe"; Parameters: "--restore-taskbar"; Flags: runhidden waituntilterminated; RunOnceId: "RestoreTaskbar"

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\unidesk"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Also delete your unidesk settings (~\.config\unidesk)?', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{%USERPROFILE}\.config\unidesk'), True, True, True);
end;
