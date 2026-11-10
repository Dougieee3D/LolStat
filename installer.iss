; LoLStat installer (Inno Setup 6). The builder compiles this automatically.

#define MyAppName "LoLStat"
#define MyAppVersion "4.4.3"
#define MyAppExe "LoLStat.exe"
#define OldAppId "{8F3C2A51-6B7D-4E2A-9C41-2D5E7A1B9F60}"

[Setup]
AppId={{3D7E9B42-1C5A-4F8E-A6D2-9B0C7E4F1A35}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=LoLStat
AppCopyright=Copyright (C) 2026 Dougieee3D. All rights reserved.
AppComments=League of Legends companion: auto-accept, phone remote and ARAM Mayhem builds.
VersionInfoVersion={#MyAppVersion}.0
VersionInfoProductName={#MyAppName}
VersionInfoDescription={#MyAppName} Setup
VersionInfoCompany=LoLStat
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableWelcomePage=no
LicenseFile=license.txt
OutputDir=.
OutputBaseFilename=LoLStat-Setup-{#MyAppVersion}
SetupIconFile=lolstat.ico
WizardImageFile=wizard_side_small.bmp,wizard_side.bmp
WizardSmallImageFile=wizard_corner.bmp
WizardStyle=modern
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName}
CloseApplications=yes
; a running LoLStat is asked to close before installing or uninstalling
AppMutex=LoLStatSingleInstance

[Messages]
WelcomeLabel1=Welcome to LoLStat
WelcomeLabel2=LoLStat is your all-in-one League of Legends companion:%n%n  - Auto-accept, phone remote, auto runes, spells and item sets%n  - Summoner's Rift, ARAM and ARAM Mayhem builds and augment grades%n  - Live game scouting, profiles, a friends leaderboard and replays%n  - A theme for every champion and skin, plus 16 more%n  - In-game overlay%n  - Your stats, records, badges, coach and weekly challenges%n%nClick Next to continue.
FinishedHeadingLabel=LoLStat is ready
FinishedLabel=LoLStat has been installed. Open it before you queue up and it takes care of the rest.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start LoLStat when Windows starts"; GroupDescription: "Options:"; Flags: unchecked

[Files]
Source: "dist\LoLStat\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "lolstat.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "license.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\lolstat.ico"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; IconFilename: "{app}\lolstat.ico"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: startup

[Run]
; let the phone remote work on home (private) Wi-Fi without a firewall pop-up
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""LoL Auto-Accept"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""{#MyAppName}"" dir=in action=allow program=""{app}\{#MyAppExe}"" enable=yes profile=private"; Flags: runhidden
Filename: "{app}\{#MyAppExe}"; Description: "Launch {#MyAppName} now"; Flags: nowait postinstall skipifsilent
; updates from inside LoLStat install quietly, then reopen LoLStat on the new version
Filename: "{app}\{#MyAppExe}"; Parameters: "--show"; Flags: nowait runasoriginaluser; Check: WizardSilent

[UninstallRun]
; remove LoLStat's item sets and rune page from League (if League is open)
Filename: "{app}\{#MyAppExe}"; Parameters: "--cleanup"; Flags: runhidden waituntilterminated; RunOnceId: "LoLStatCleanup"
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""{#MyAppName}"""; Flags: runhidden; RunOnceId: "RemoveFirewallRule"

[Code]
// Quietly remove the older "LoL Auto-Accept" app if it's installed (LoLStat replaces it).
procedure RemoveOldApp();
var
  Key, Cmd: String;
  Code: Integer;
begin
  Key := 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{#OldAppId}_is1';
  if RegQueryStringValue(HKLM, Key, 'UninstallString', Cmd) or
     RegQueryStringValue(HKCU, Key, 'UninstallString', Cmd) then
  begin
    Cmd := RemoveQuotes(Cmd);
    if FileExists(Cmd) then
      Exec(Cmd, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    RemoveOldApp();
end;
