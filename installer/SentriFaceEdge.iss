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

var
  ActivationPage: TWizardPage;
  ActivationStatusLabel: TNewStaticText;
  ActivationMachineLabel: TNewStaticText;
  ActivationMachineEdit: TNewEdit;
  ActivationCopyButton: TNewButton;
  ActivationKeyLabel: TNewStaticText;
  ActivationKeyEdit: TNewEdit;
  ActivationButton: TNewButton;
  ActivationMessageLabel: TNewStaticText;
  ActivationPageLoaded: Boolean;
  ActivationMachineId: String;


function LoadActivationResult(
  ResultFile: String;
  var Activated: Boolean;
  var MachineId: String;
  var MessageText: String
): Boolean;
var
  Lines: TArrayOfString;
begin
  Result := False;
  Activated := False;
  MachineId := '';
  MessageText := '';
  if not LoadStringsFromFile(ResultFile, Lines) then
    exit;
  if GetArrayLength(Lines) < 2 then
    exit;
  Activated := Lines[0] = '1';
  MachineId := Lines[1];
  if GetArrayLength(Lines) >= 3 then
    MessageText := Lines[2];
  Result := True;
end;


function RunActivationHelper(
  Action: String;
  KeyFile: String;
  var Activated: Boolean;
  var MachineId: String;
  var MessageText: String
): Boolean;
var
  ResultFile: String;
  Params: String;
  ResultCode: Integer;
begin
  ResultFile := ExpandConstant(
    '{commonappdata}\SentriFace Edge\cache\activation-result.txt'
  );
  DeleteFile(ResultFile);
  if Action = 'status' then
    Params := '--activation-helper status "' + ResultFile + '"'
  else
    Params := '--activation-helper activate "' + KeyFile + '" "' + ResultFile + '"';

  Result := ExecAsOriginalUser(
    ExpandConstant('{app}\{#MyExeName}'),
    Params,
    ExpandConstant('{app}'),
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  );
  if Result then
    Result := LoadActivationResult(ResultFile, Activated, MachineId, MessageText);
  DeleteFile(ResultFile);
end;


procedure ShowActivationState(Activated: Boolean; MessageText: String);
begin
  ActivationMachineLabel.Visible := not Activated;
  ActivationMachineEdit.Visible := not Activated;
  ActivationCopyButton.Visible := not Activated;
  ActivationKeyLabel.Visible := not Activated;
  ActivationKeyEdit.Visible := not Activated;
  ActivationButton.Visible := not Activated;
  if Activated then
  begin
    ActivationStatusLabel.Caption := 'SentriFace is activated.';
    ActivationStatusLabel.Font.Color := clGreen;
    ActivationMessageLabel.Caption := '';
  end
  else
  begin
    ActivationStatusLabel.Caption := 'SentriFace is not activated.';
    ActivationStatusLabel.Font.Color := clWindowText;
    ActivationMachineEdit.Text := ActivationMachineId;
    ActivationMessageLabel.Caption := MessageText;
  end;
end;


procedure CopyMachineIdClick(Sender: TObject);
var
  ResultCode: Integer;
begin
  if Exec(
    ExpandConstant('{cmd}'),
    '/C echo ' + ActivationMachineId + '| clip',
    '',
    SW_HIDE,
    ewWaitUntilTerminated,
    ResultCode
  ) and (ResultCode = 0) then
  begin
    ActivationMessageLabel.Caption := 'Machine ID copied.';
    ActivationMessageLabel.Font.Color := clGreen;
  end
  else
  begin
    ActivationMessageLabel.Caption := 'Copy failed. Select the machine ID and press Ctrl+C.';
    ActivationMessageLabel.Font.Color := clRed;
  end;
end;


procedure ActivateNowClick(Sender: TObject);
var
  KeyFile: String;
  Activated: Boolean;
  MachineId: String;
  MessageText: String;
begin
  if Trim(ActivationKeyEdit.Text) = '' then
  begin
    ActivationMessageLabel.Caption := 'Enter an activation key.';
    ActivationMessageLabel.Font.Color := clRed;
    exit;
  end;

  KeyFile := ExpandConstant(
    '{commonappdata}\SentriFace Edge\cache\activation-key.txt'
  );
  DeleteFile(KeyFile);
  SaveStringToFile(KeyFile, Trim(ActivationKeyEdit.Text), False);
  ActivationButton.Enabled := False;
  ActivationMessageLabel.Caption := 'Checking activation key...';
  try
    if not RunActivationHelper(
      'activate', KeyFile, Activated, MachineId, MessageText
    ) then
    begin
      Activated := False;
      MessageText := 'SentriFace could not check the activation key.';
    end;
  finally
    DeleteFile(KeyFile);
    ActivationButton.Enabled := True;
  end;

  if MachineId <> '' then
    ActivationMachineId := MachineId;
  if Activated then
    ActivationMessageLabel.Font.Color := clGreen
  else
    ActivationMessageLabel.Font.Color := clRed;
  ShowActivationState(Activated, MessageText);
end;


procedure InitializeWizard;
begin
  ActivationPage := CreateCustomPage(
    wpInstalling,
    'Activate SentriFace Edge',
    'Activate now or continue and activate when SentriFace starts.'
  );

  ActivationStatusLabel := TNewStaticText.Create(ActivationPage);
  ActivationStatusLabel.Parent := ActivationPage.Surface;
  ActivationStatusLabel.Left := 0;
  ActivationStatusLabel.Top := 0;
  ActivationStatusLabel.Width := ActivationPage.SurfaceWidth;
  ActivationStatusLabel.Font.Style := [fsBold];

  ActivationMachineLabel := TNewStaticText.Create(ActivationPage);
  ActivationMachineLabel.Parent := ActivationPage.Surface;
  ActivationMachineLabel.Left := 0;
  ActivationMachineLabel.Top := ScaleY(30);
  ActivationMachineLabel.Caption := 'Machine ID';

  ActivationMachineEdit := TNewEdit.Create(ActivationPage);
  ActivationMachineEdit.Parent := ActivationPage.Surface;
  ActivationMachineEdit.Left := 0;
  ActivationMachineEdit.Top := ScaleY(48);
  ActivationMachineEdit.Width := ScaleX(340);
  ActivationMachineEdit.ReadOnly := True;

  ActivationCopyButton := TNewButton.Create(ActivationPage);
  ActivationCopyButton.Parent := ActivationPage.Surface;
  ActivationCopyButton.Left := ScaleX(350);
  ActivationCopyButton.Top := ScaleY(47);
  ActivationCopyButton.Width := ScaleX(70);
  ActivationCopyButton.Caption := 'Copy';
  ActivationCopyButton.OnClick := @CopyMachineIdClick;

  ActivationKeyLabel := TNewStaticText.Create(ActivationPage);
  ActivationKeyLabel.Parent := ActivationPage.Surface;
  ActivationKeyLabel.Left := 0;
  ActivationKeyLabel.Top := ScaleY(84);
  ActivationKeyLabel.Caption := 'Activation key';

  ActivationKeyEdit := TNewEdit.Create(ActivationPage);
  ActivationKeyEdit.Parent := ActivationPage.Surface;
  ActivationKeyEdit.Left := 0;
  ActivationKeyEdit.Top := ScaleY(102);
  ActivationKeyEdit.Width := ScaleX(420);

  ActivationButton := TNewButton.Create(ActivationPage);
  ActivationButton.Parent := ActivationPage.Surface;
  ActivationButton.Left := 0;
  ActivationButton.Top := ScaleY(136);
  ActivationButton.Width := ScaleX(110);
  ActivationButton.Caption := 'Activate now';
  ActivationButton.OnClick := @ActivateNowClick;

  ActivationMessageLabel := TNewStaticText.Create(ActivationPage);
  ActivationMessageLabel.Parent := ActivationPage.Surface;
  ActivationMessageLabel.Left := ScaleX(122);
  ActivationMessageLabel.Top := ScaleY(143);
  ActivationMessageLabel.Width := ScaleX(298);
  ActivationMessageLabel.AutoSize := False;
  ActivationMessageLabel.WordWrap := True;
end;

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


procedure CurPageChanged(CurPageID: Integer);
var
  Activated: Boolean;
  MachineId: String;
  MessageText: String;
begin
  if (CurPageID = ActivationPage.ID) and not ActivationPageLoaded then
  begin
    ActivationPageLoaded := True;
    if RunActivationHelper(
      'status', '', Activated, MachineId, MessageText
    ) then
    begin
      ActivationMachineId := MachineId;
      ShowActivationState(Activated, MessageText);
    end
    else
    begin
      ActivationMachineId := '';
      ShowActivationState(False, 'Activation status could not be checked. You can activate when SentriFace starts.');
    end;
  end;
end;
