#define MyAppName "竹简工作台"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "湖大智竹实践团队"

[Setup]
AppId={{B4A7CF5E-99C0-4CD9-9A30-B5D574A0F012}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\BambooWorkbench
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer-output
OutputBaseFilename=BambooWorkbench-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
WizardStyle=modern
UninstallDisplayIcon={app}\BambooWorkbench.exe

[Files]
Source: "..\dist\BambooWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\BambooWorkbench.exe"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent
