#define MyAppName "竹简工作台"
#define MyAppVersion "1.2.0"
#define MyAppPublisher "湖南大学智创未来团队"

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
ChangesAssociations=yes
CloseApplications=yes
RestartApplications=no
SetupIconFile=..\logo\BambooWorkbench.ico
UninstallDisplayIcon={app}\logo\BambooWorkbench.ico

[Files]
Source: "..\dist\BambooWorkbench\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"; IconFilename: "{app}\logo\BambooWorkbench.ico"; IconIndex: 0
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\BambooWorkbench.exe"; IconFilename: "{app}\logo\BambooWorkbench.ico"; IconIndex: 0; Tasks: desktopicon

[Run]
Filename: "{app}\BambooWorkbench.exe"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent
