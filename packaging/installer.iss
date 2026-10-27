; Inno Setup script for the Windows installer. Built by packaging/build_windows.ps1:
;   ISCC /DAppVersion=1.1.0 /DLangFile=<path to ChineseSimplified.isl> packaging\installer.iss
; Installs per user (no administrator rights) to %LOCALAPPDATA%\Programs\PaperLook.
; User data lives in %LOCALAPPDATA%\PaperLook and is kept on upgrade and uninstall.

#ifndef AppVersion
  #error AppVersion is required (/DAppVersion=x.y.z)
#endif
#ifndef LangFile
  #define LangFile "compiler:Default.isl"
#endif

[Setup]
; Never change AppId: upgrades are matched by it.
AppId={{F6933F48-3368-48D7-8A57-E80EAD2D5648}
AppName=PaperLook
AppVersion={#AppVersion}
AppVerName=PaperLook {#AppVersion}
AppPublisher=koara666
AppPublisherURL=https://github.com/koara666/paperlook
AppSupportURL=https://github.com/koara666/paperlook/issues
AppUpdatesURL=https://github.com/koara666/paperlook/releases
DefaultDirName={localappdata}\Programs\PaperLook
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist
OutputBaseFilename=PaperLook-{#AppVersion}-Windows-Setup
SetupIconFile=..\assets\paperlook.ico
UninstallDisplayIcon={app}\PaperLook.exe
UninstallDisplayName=PaperLook
VersionInfoVersion={#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "zh"; MessagesFile: "{#LangFile}"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[InstallDelete]
; files of the previous version (asset names change between versions)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\PaperLook\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PaperLook"; Filename: "{app}\PaperLook.exe"
Name: "{autodesktop}\PaperLook"; Filename: "{app}\PaperLook.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PaperLook.exe"; Description: "{cm:LaunchProgram,PaperLook}"; Flags: nowait postinstall skipifsilent
