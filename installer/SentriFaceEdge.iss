#define MyAppName "SentriFace Edge"
#define MyAppVersion "1.0.0"
#define MyExeName "ui.exe"

[Setup]

AppId={{SentriFaceEdge}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}

DefaultDirName={autopf}\SentriFace Edge

PrivilegesRequired=admin

OutputDir=..\installer_output
OutputBaseFilename=SentriFaceEdge_Setup

Compression=lzma
SolidCompression=yes

ArchitecturesInstallIn64BitMode=x64


[Files]

Source: "..\build\ui.dist\*"; \
DestDir: "{app}"; \
Flags: recursesubdirs createallsubdirs


[Icons]

Name: "{autoprograms}\SentriFace Edge"; \
Filename: "{app}\{#MyExeName}"

Name: "{commondesktop}\SentriFace Edge"; \
Filename: "{app}\{#MyExeName}"


[Run]

Filename: "{app}\{#MyExeName}"; \
Description: "Launch SentriFace Edge"; \
Flags: nowait postinstall skipifsilent


[Run]

Filename: "powershell.exe"; \
Parameters: "-ExecutionPolicy Bypass -Command ""New-NetFirewallRule -DisplayName 'SentriFace Edge - deny outbound connections' -Name 'SentriFaceEdge-BlockOutbound' -Direction Outbound -Action Block -Program '{app}\ui.exe' -Profile Any"""; \
Flags: runhidden runascurrentuser
