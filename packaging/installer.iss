; Version is passed in by build.ps1: ISCC /DAppVersion=0.2.0 installer.iss
#ifndef AppVersion
  #error AppVersion must be defined (run packaging\build.ps1)
#endif

[Setup]
AppId={{8F3B6C1E-4D27-4A55-9B0E-5C2A7D1F6E93}
AppName=Local Dictation
AppVersion={#AppVersion}
AppPublisher=Local Dictation
DefaultDirName={localappdata}\Programs\Local Dictation
DefaultGroupName=Local Dictation
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
AppMutex=Local\LocalDictationSingleton
OutputDir=..\dist
OutputBaseFilename=LocalDictation-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=Local Dictation

[Files]
Source: "..\build\pyinstaller\dist\LocalDictation\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[InstallDelete]
; Drop files a newer build no longer ships (the folder is fully rewritten by [Files]).
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\Local Dictation"; Filename: "{app}\LocalDictation.exe"

[Run]
Filename: "{app}\LocalDictation.exe"; Description: "Launch Local Dictation"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RunValue = 'LocalDictation';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Command: String;
  DataDir: String;
begin
  if CurUninstallStep <> usUninstall then exit;

  { The app owns this value; remove it only if the quoted command starts inside this install folder. }
  if RegQueryStringValue(HKCU, RunKey, RunValue, Command) then
    if Pos(Lowercase('"' + ExpandConstant('{app}') + '\'), Lowercase(Command)) = 1 then
      RegDeleteValue(HKCU, RunKey, RunValue);

  DataDir := ExpandConstant('{userappdata}\LocalDictation');
  if DirExists(DataDir) then
    if SuppressibleMsgBox('Also delete your settings and logs?' + #13#10 + DataDir,
                          mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
      DelTree(DataDir, True, True, True);
end;
