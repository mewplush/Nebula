; PyNeb / Nebula installer (Inno Setup 6)
; Compile com:  "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" pyneb_installer.iss   (ou use build_installer.bat)

#define MyAppName "PyNeb"
#define MyAppVersion "1.11.0"
#define MyAppPublisher "mewplush"
#define MyAppURL "https://github.com/rdb231-com231/pyneb"
#define SourceDir "C:\Users\Pc-Ryzen3\OneDrive\Área de Trabalho\NebulaPY\pyneb"
#define MyIconFile "st-_3_.ico"

[Setup]
; NOTA: mantenha o MESMO AppId para que esta versão atualize instalações anteriores.
AppId={{39CD4145-EC75-4360-924B-62F36E43A213}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
; Antes era "nebula\pyneb" (caminho relativo, que não é válido). {autopf} = Arquivos de Programas
; (admin) ou %LOCALAPPDATA%\Programs (instalação só para o usuário).
DefaultDirName={autopf}\Nebula
DefaultGroupName={#MyAppName}
DisableWelcomePage=no
; O usuário escolhe no início: para todos (admin) ou só para ele (sem admin).
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=C:\Users\Pc-Ryzen3\OneDrive\Área de Trabalho\NebulaPY
OutputBaseFilename=pyneb_installer
SetupIconFile={#SourceDir}\{#MyIconFile}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
WizardImageFile=C:\Users\Pc-Ryzen3\Downloads\wizimg.bmp
WizardSmallImageFile=C:\Program Files (x86)\Inno Setup 6\WizClassicSmallImage.bmp
WizardSizePercent=140, 100
UninstallDisplayName={#MyAppName}
; Ícone do "Adicionar/Remover programas": caminho INSTALADO (o antigo apontava para a pasta Downloads do seu PC).
UninstallDisplayIcon={app}\{#MyIconFile}
UsePreviousAppDir=no
; Avisa o Windows que PATH e associações de arquivo mudaram.
ChangesEnvironment=yes
ChangesAssociations=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[CustomMessages]
english.AddToPath=Add Nebula to PATH (type "nebula" in any terminal)
english.AssocNeb=Open .neb files with Nebula (double-click to run)
english.IntegrationGroup=System integration:
english.PythonMissing=Python 3 was not found on this computer. Nebula needs Python 3 to run.%n%nInstall it from python.org (check "Add python.exe to PATH") and then use Nebula.%n%nContinue installing anyway?
english.OpenShell=Nebula Shell
brazilianportuguese.AddToPath=Adicionar a Nebula ao PATH (digitar "nebula" em qualquer terminal)
brazilianportuguese.AssocNeb=Abrir arquivos .neb com a Nebula (duplo clique executa)
brazilianportuguese.IntegrationGroup=Integração com o sistema:
brazilianportuguese.PythonMissing=O Python 3 não foi encontrado neste computador. A Nebula precisa do Python 3 para funcionar.%n%nInstale em python.org (marque "Add python.exe to PATH") e depois use a Nebula.%n%nContinuar a instalação mesmo assim?
brazilianportuguese.OpenShell=Shell da Nebula

[Tasks]
Name: "addtopath"; Description: "{cm:AddToPath}"; GroupDescription: "{cm:IntegrationGroup}"
Name: "assoc"; Description: "{cm:AssocNeb}"; GroupDescription: "{cm:IntegrationGroup}"

[Files]
; Não copia caches, testes, extensão do VS Code, config local nem o próprio .iss.
Source: "{#SourceDir}\*"; DestDir: "{app}"; Excludes: "__pycache__,*.pyc,.git*,.config,tests,vscode-nebula,*.iss"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; Caches de versões antigas podem ficar "velhos" depois de uma atualização.
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: filesandordirs; Name: "{app}\__pycache__"

[UninstallDelete]
; O Python recria __pycache__ ao rodar; sem isso a pasta de instalação não some por completo.
Type: filesandordirs; Name: "{app}\src\__pycache__"
Type: filesandordirs; Name: "{app}\__pycache__"

[Registry]
; Ícone dos arquivos .neb (o caminho agora é o instalado, não o da sua pasta Downloads).
Root: HKA; Subkey: "Software\Classes\.neb"; ValueType: string; ValueName: ""; ValueData: "NebulaFile"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.neb"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.neb"; ValueType: dword; ValueName: "BrowserFlags"; ValueData: $00000000; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.neb"; ValueType: dword; ValueName: "EditFlags"; ValueData: $00000000; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.neb\DefaultIcon"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.neb\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyIconFile},0"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\NebulaFile"; ValueType: string; ValueName: ""; ValueData: "Nebula Script"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\NebulaFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyIconFile},0"
; Duplo clique em um .neb: executa e espera uma tecla (nebula-run.bat).
Root: HKA; Subkey: "Software\Classes\NebulaFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\nebula-run.bat"" ""%1"""; Tasks: assoc

[Icons]
Name: "{group}\{cm:OpenShell}"; Filename: "{app}\nebula.bat"; Parameters: "--shell"; IconFilename: "{app}\{#MyIconFile}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"

[Code]
const
  EnvKeyUser = 'Environment';
  EnvKeyMachine = 'SYSTEM\CurrentControlSet\Control\Session Manager\Environment';

// Instalação para todos (admin) mexe no PATH do sistema; senão, no PATH do usuário.
function EnvRoot: Integer;
begin
  if IsAdminInstallMode then
    Result := HKEY_LOCAL_MACHINE
  else
    Result := HKEY_CURRENT_USER;
end;

function EnvKey: String;
begin
  if IsAdminInstallMode then
    Result := EnvKeyMachine
  else
    Result := EnvKeyUser;
end;

function PathHasDir(const Dir: String): Boolean;
var
  Paths: String;
begin
  if not RegQueryStringValue(EnvRoot, EnvKey, 'Path', Paths) then
    Result := False
  else
    Result := Pos(';' + Uppercase(Dir) + ';', ';' + Uppercase(Paths) + ';') > 0;
end;

procedure AddToPath(const Dir: String);
var
  Paths: String;
begin
  if PathHasDir(Dir) then
    Exit;
  if not RegQueryStringValue(EnvRoot, EnvKey, 'Path', Paths) then
    Paths := '';
  if (Paths <> '') and (Copy(Paths, Length(Paths), 1) <> ';') then
    Paths := Paths + ';';
  Paths := Paths + Dir;
  RegWriteExpandStringValue(EnvRoot, EnvKey, 'Path', Paths);
end;

procedure RemoveFromPath(const Dir: String);
var
  Paths, Wrapped, Needle: String;
  P: Integer;
begin
  if not RegQueryStringValue(EnvRoot, EnvKey, 'Path', Paths) then
    Exit;
  Wrapped := ';' + Paths + ';';
  Needle := ';' + Dir + ';';
  P := Pos(Uppercase(Needle), Uppercase(Wrapped));
  if P = 0 then
    Exit;
  // remove ";Dir" e mantém o ";" seguinte; depois tira os ";" artificiais das pontas
  Delete(Wrapped, P, Length(Needle) - 1);
  Paths := Copy(Wrapped, 2, Length(Wrapped) - 2);
  RegWriteExpandStringValue(EnvRoot, EnvKey, 'Path', Paths);
end;

function PythonOk: Boolean;
var
  Code: Integer;
begin
  Result := False;
  if Exec(ExpandConstant('{cmd}'), '/C py -3 --version', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := (Code = 0);
  if not Result then
    if Exec(ExpandConstant('{cmd}'), '/C python --version', '', SW_HIDE, ewWaitUntilTerminated, Code) then
      Result := (Code = 0);
end;

function InitializeSetup: Boolean;
begin
  Result := True;
  if not PythonOk then
    if MsgBox(CustomMessage('PythonMissing'), mbConfirmation, MB_YESNO) = IDNO then
      Result := False;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and WizardIsTaskSelected('addtopath') then
    AddToPath(ExpandConstant('{app}'));
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
