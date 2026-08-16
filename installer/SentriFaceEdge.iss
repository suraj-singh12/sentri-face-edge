#ifndef MyAppVersion
  #error MyAppVersion must be supplied by build_release.ps1
#endif
#ifndef MyAppVersionQuad
  #error MyAppVersionQuad must be supplied by build_release.ps1
#endif

#define MyAppName "SentriFace Edge"
#define MyPublisher "SentriFace"
#define MyExeName "SentriFaceEdge.exe"
#define MyAppId "{9B86BE35-3E8F-47F0-A9C2-A4CF4933B985}"

[Setup]
AppId={{#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyPublisher}
DefaultDirName={autopf}\SentriFace Edge
DefaultGroupName=SentriFace Edge
SetupIconFile=..\packaging\windows\SentriFace.ico
UninstallDisplayIcon={app}\{#MyExeName}
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=SentriFaceEdge-{#MyAppVersion}-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
CloseApplications=yes
CloseApplicationsFilter={#MyExeName}
RestartApplications=no
VersionInfoVersion={#MyAppVersionQuad}
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
MinVersion=10.0.17763

[Files]
Source: "..\build\ui.dist\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\packaging\windows\Install-OfflinePolicy.ps1"; Flags: dontcopy
Source: "..\packaging\windows\Remove-OfflinePolicy.ps1"; DestDir: "{app}\support"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\SentriFace Edge"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"
Name: "{commondesktop}\SentriFace Edge"; Filename: "{app}\{#MyExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#MyExeName}"; Description: "Launch SentriFace Edge"; WorkingDir: "{app}"; Flags: nowait postinstall skipifsilent runasoriginaluser

[UninstallRun]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File ""{app}\support\Remove-OfflinePolicy.ps1"""; Flags: runhidden waituntilterminated; RunOnceId: "RemoveSentriFaceFirewall"

[Code]
var
  PreviousInstallation: Boolean;
  SetupCompleted: Boolean;

function NextVersionPart(var Version: String): Integer;
var
  Separator: Integer;
  Part: String;
begin
  Separator := Pos('.', Version);
  if Separator = 0 then begin
    Part := Version;
    Version := '';
  end else begin
    Part := Copy(Version, 1, Separator - 1);
    Delete(Version, 1, Separator);
  end;
  Result := StrToIntDef(Part, 0);
end;

function CompareVersions(Left, Right: String): Integer;
var
  Index, LeftPart, RightPart: Integer;
begin
  Result := 0;
  for Index := 1 to 4 do begin
    LeftPart := NextVersionPart(Left);
    RightPart := NextVersionPart(Right);
    if LeftPart < RightPart then begin Result := -1; exit; end;
    if LeftPart > RightPart then begin Result := 1; exit; end;
  end;
end;

function InitializeSetup(): Boolean;
var
  InstalledVersion, UninstallKey: String;
begin
  Result := True;
  UninstallKey := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#MyAppId}_is1';
  PreviousInstallation := RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', InstalledVersion);
  if PreviousInstallation then begin
    if CompareVersions('{#MyAppVersion}', InstalledVersion) < 0 then begin
      MsgBox('A newer SentriFace Edge version is already installed. Downgrades are not supported.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

procedure RequestGracefulShutdown();
var
  ResultCode: Integer;
begin
  if FileExists(ExpandConstant('{app}\{#MyExeName}')) then begin
    ExecAsOriginalUser(
      ExpandConstant('{app}\{#MyExeName}'),
      '--request-shutdown',
      ExpandConstant('{app}'),
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode
    );
    Sleep(1500);
  end;
end;

function InstallOfflinePolicy(): Boolean;
var
  ResultCode: Integer;
begin
  ExtractTemporaryFile('Install-OfflinePolicy.ps1');
  Result := Exec(
    ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
      ExpandConstant('{tmp}\Install-OfflinePolicy.ps1') + '" -ExecutablePath "' +
      ExpandConstant('{app}\{#MyExeName}') + '"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode
  ) and (ResultCode = 0);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  RequestGracefulShutdown();
  if InstallOfflinePolicy() then
    Result := ''
  else
    Result := 'SentriFace offline firewall setup or verification failed.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssDone then SetupCompleted := True;
end;

procedure DeinitializeSetup();
var
  ResultCode: Integer;
begin
  if SetupCompleted then exit;
  if PreviousInstallation and FileExists(ExpandConstant('{app}\{#MyExeName}')) then begin
    ExtractTemporaryFile('Install-OfflinePolicy.ps1');
    Exec(
      ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
        ExpandConstant('{tmp}\Install-OfflinePolicy.ps1') + '" -ExecutablePath "' +
        ExpandConstant('{app}\{#MyExeName}') + '"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode
    );
  end else begin
    Exec(
      ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command "' +
        'Get-NetFirewallRule -Name ''SentriFaceEdge-BlockOutbound'' -ErrorAction SilentlyContinue | Remove-NetFirewallRule"',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode
    );
  end;
end;
