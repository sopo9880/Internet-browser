#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Internet Browser"
#define AppExe "internet_browser.exe"

[Setup]
AppId={{CF6FF9A3-8A80-4C6C-98B2-C9C44F280D1A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=sopo9880
AppPublisherURL=https://github.com/sopo9880/Internet-browser
AppSupportURL=https://github.com/sopo9880/Internet-browser/issues
DefaultDirName={autopf}\Internet Browser
DefaultGroupName=Internet Browser
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Internet-browser-Windows-Setup-v{#AppVersion}
Compression=lzma2
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayName={#AppName}
VersionInfoVersion={#AppVersion}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "..\build\windows\x64\runner\Release\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Internet Browser"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\Internet Browser"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch Internet Browser"; Flags: nowait postinstall skipifsilent
