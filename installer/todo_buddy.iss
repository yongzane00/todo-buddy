; Inno Setup script for Todo Buddy.
;
; Builds a conventional installer around the PyInstaller --onedir build in
; dist\TodoBuddy, instead of shipping that build's raw self-extracting
; --onefile exe directly. A single self-extracting exe that unpacks itself
; into a temp folder and runs from there is exactly the pattern antivirus
; and browser (Safe Browsing) heuristics flag as dropper-like; a normal
; installer avoids that shape entirely.
;
; Build with (from the repo root, after the PyInstaller onedir build exists
; in dist\TodoBuddy):
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\todo_buddy.iss

#define MyAppName "Todo Buddy"
#define MyAppVersion "0.1.1"
#define MyAppPublisher "Yong Zane"
#define MyAppURL "https://github.com/yongzane00/todo-buddy"
#define MyAppExeName "TodoBuddy.exe"

[Setup]
AppId={{6C6F9F2E-6E9B-4E77-9A0A-3E7F6D1C0C21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
; Per-user install under %LOCALAPPDATA% — no admin prompt, matching the
; app's own local-first, no-account, no-install-elsewhere philosophy.
DefaultDirName={localappdata}\Programs\TodoBuddy
DefaultGroupName=Todo Buddy
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
SetupIconFile=..\asset\icon\todo-buddy.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
OutputDir=..\dist
OutputBaseFilename=TodoBuddy-Setup-{#MyAppVersion}
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\TodoBuddy\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
