; Instalador do MIR4 Companion (Inno Setup)
; Compilar com: ISCC.exe installer.iss

#define MyAppName "MIR4 Companion"
#define MyAppVersion "1.0"
#define MyAppExeName "MIR4Companion.exe"

[Setup]
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={localappdata}\MIR4Companion
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=installer_output
OutputBaseFilename=MIR4Companion_Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos adicionais:"

[Files]
Source: "dist\MIR4Companion.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: ".env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "winget"; Parameters: "install UB-Mannheim.TesseractOCR -e --silent --accept-package-agreements --accept-source-agreements"; StatusMsg: "Instalando Tesseract OCR (necessário pra ler a tela do jogo)..."; Flags: runhidden; Check: not TesseractInstalled
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName}"; Flags: postinstall nowait skipifsilent

[Code]
function TesseractInstalled: Boolean;
begin
  Result := FileExists('C:\Program Files\Tesseract-OCR\tesseract.exe');
end;
