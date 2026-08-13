#define MyAppName "SentriFace Edge"
#define MyAppVersion "1.0.0"
#define MyPublisher "SentriFace"
#define MyExeName "SentriFaceEdge.exe"

[Setup]
AppId=SentriFaceEdge
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}

DefaultDirName={autopf}\SentriFace Edge
DefaultGroupName=SentriFace Edge

SetupIconFile=..\packaging\windows\SentriFaceEdge.ico
UninstallDisplayIcon={app}\SentriFaceEdge.exe

PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

OutputDir=..\installer_output
OutputBaseFilename=SentriFaceEdge_Setup

Compression=lzma2
SolidCompression=yes

WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
RestartApplications=no

VersionInfoVersion=1.0.0.0
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}


[Files]

; Compiled immutable application
Source: "..\build\ui.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Existing authoritative firewall installer
; Temporary only. It is NOT left on the customer's machine.
Source: "..\packaging\windows\Install-OfflinePolicy.ps1"; DestDir: "{tmp}"; Flags: deleteafterinstall


[Dirs]

; Persistent mutable application state.
; NEVER automatically delete these during normal uninstall.

Name: "{commonappdata}\SentriFace Edge"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\database"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\data"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\logs"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\backups"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\config"; Permissions: users-modify; Flags: uninsneveruninstall

Name: "{commonappdata}\SentriFace Edge\cache"; Permissions: users-modify; Flags: uninsneveruninstall


[Icons]

Name: "{autoprograms}\SentriFace Edge"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"

Name: "{commondesktop}\SentriFace Edge"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"


[Run]

; Launch as the original customer user, NOT as elevated installer process.
Filename: "{app}\{#MyExeName}"; Description: "Launch SentriFace Edge"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent runasoriginaluser


[UninstallRun]

; Remove only the firewall policy owned by SentriFace.
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ""Get-NetFirewallRule -Name 'SentriFaceEdge-BlockOutbound' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"""; Flags: runhidden waituntilterminated


[Code]

procedure InstallOfflinePolicy;
var
  PowerShell: String;
  Params: String;
  ResultCode: Integer;
begin
  PowerShell :=
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');

  { Remove an existing SentriFace rule before recreating it for
    the exact newly installed executable path. }

  Params :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass ' +
    '-Command "Get-NetFirewallRule -Name ''SentriFaceEdge-BlockOutbound'' ' +
    '-ErrorAction SilentlyContinue | Remove-NetFirewallRule"';

  Exec(
    PowerShell,
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );

  Params :=
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass ' +
    '-File "' +
    ExpandConstant('{tmp}\Install-OfflinePolicy.ps1') +
    '" -ExecutablePath "' +
    ExpandConstant('{app}\{#MyExeName}') +
    '"';

  if not Exec(
    PowerShell,
    Params,
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) then
  begin
    RaiseException(
      'Could not execute the SentriFace offline firewall installer.'
    );
  end;

    if ResultCode <> 0 then
  begin
    RaiseException(
      'SentriFace offline firewall setup failed with exit code ' +
      IntToStr(ResultCode) + '.'
    );
  end;
end;


procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    InstallOfflinePolicy;
  end;
end;