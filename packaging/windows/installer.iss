; Inno Setup script for Susurros-Setup.exe. Built by packaging\windows\build.ps1, which
; passes the version in the SUSURROS_VERSION environment variable.
#define AppVersion GetEnv("SUSURROS_VERSION")

[Setup]
AppId={{8C1B6A52-6E0B-4B0E-9B8E-5A1D3C2F7E41}
AppName=Susurros
AppVersion={#AppVersion}
AppPublisher=KTJota
AppPublisherURL=https://github.com/KTJota/susurros
DefaultDirName={localappdata}\Programs\Susurros
DefaultGroupName=Susurros
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=Susurros-Setup-{#AppVersion}
SetupIconFile=..\..\build\windows\susurros.ico
UninstallDisplayIcon={app}\Susurros.exe
WizardStyle=modern
Compression=lzma2/normal
SolidCompression=no
LZMAUseSeparateProcess=yes
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"

[Files]
Source: "..\..\dist\Susurros\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Susurros"; Filename: "{app}\Susurros.exe"
Name: "{autodesktop}\Susurros"; Filename: "{app}\Susurros.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\Susurros.exe"; Description: "{cm:LaunchProgram,Susurros}"; Flags: nowait postinstall skipifsilent
