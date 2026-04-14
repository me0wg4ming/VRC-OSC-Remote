[Setup]
AppName=VRChat OSC Remote
AppVersion=1.0
AppPublisher=me0wg4ming
DefaultDirName={autopf}\VRChatOSCRemote
DefaultGroupName=VRChat OSC Remote
OutputDir=E:\python_bot_osc\installer
OutputBaseFilename=VRChatOSCRemote-Setup
SetupIconFile=E:\python_bot_osc\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\icon.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; Python embeddable (includes tkinter, tcl, site-packages)
Source: "E:\python_bot_osc\python_embed\*"; DestDir: "{app}\python"; Flags: recursesubdirs createallsubdirs

; Main script and assets
Source: "E:\python_bot_osc\client.py"; DestDir: "{app}"
Source: "E:\python_bot_osc\banner.png"; DestDir: "{app}"
Source: "E:\python_bot_osc\icon.ico"; DestDir: "{app}"

; Start script
Source: "E:\python_bot_osc\start.bat"; DestDir: "{app}"

[Icons]
Name: "{group}\VRChat OSC Remote"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\client.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Uninstall VRChat OSC Remote"; Filename: "{uninstallexe}"
Name: "{commondesktop}\VRChat OSC Remote"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\client.py"""; WorkingDir: "{app}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Code]
procedure FixPthFile();
var
  PthFile: String;
  Lines: TArrayOfString;
  Content: String;
  i: Integer;
  HasLib: Boolean;
begin
  PthFile := ExpandConstant('{app}\python\python311._pth');
  if not FileExists(PthFile) then Exit;
  
  LoadStringsFromFile(PthFile, Lines);
  HasLib := False;
  for i := 0 to GetArrayLength(Lines) - 1 do
    if Lines[i] = 'Lib' then HasLib := True;
  
  if not HasLib then
  begin
    Content := '';
    for i := 0 to GetArrayLength(Lines) - 1 do
      Content := Content + Lines[i] + #13#10;
    Content := Content + 'Lib' + #13#10 + 'Lib\site-packages' + #13#10;
    SaveStringToFile(PthFile, Content, False);
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    FixPthFile();
end;

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\client.py"""; WorkingDir: "{app}"; Description: "Launch VRChat OSC Remote"; Flags: nowait postinstall skipifsilent
