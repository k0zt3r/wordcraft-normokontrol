; Windows x64, current-user installation. Build with installer/build.py.
#ifndef StageDir
  #error StageDir must point to the prepared staging directory.
#endif
#ifndef OutputDir
  #error OutputDir must point to the output directory.
#endif
#ifndef AppVersion
  #error AppVersion is required.
#endif
#include AddBackslash(StageDir) + "dependencies.iss"
#define WordcraftArchiveRoot "wordcraft-" + WordcraftVersion + "-windows-x64-portable"

[Setup]
AppId={{A0B6EA78-6B8B-44B4-90E1-16EBD43C3D5F}
AppName=Нормоконтроль ИрГУПС
AppVersion={#AppVersion}
AppVerName=Нормоконтроль ИрГУПС {#AppVersion}
AppPublisher=wordcraft-normokontrol contributors
AppPublisherURL=https://github.com/k0zt3r/wordcraft-normokontrol
AppSupportURL=https://github.com/k0zt3r/wordcraft-normokontrol/issues
AppUpdatesURL=https://github.com/k0zt3r/wordcraft-normokontrol/releases
DefaultDirName={localappdata}\Programs\WordcraftNormokontrol
DefaultGroupName=Нормоконтроль ИрГУПС
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
WizardStyle=modern
DisableWelcomePage=no
LicenseFile={#StageDir}\app\LICENSE
OutputDir={#OutputDir}
OutputBaseFilename=Normokontrol-{#AppVersion}-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ArchiveExtraction=full
; Portable Wordcraft is extracted by code, outside the [Files] size estimate.
ExtraDiskSpaceRequired=536870912
SetupLogging=yes
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Нормоконтроль ИрГУПС
UninstallDisplayIcon={app}\runtime\pythonw.exe
UninstallFilesDir={app}\uninstall
ChangesEnvironment=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
russian.WelcomeLabel2=Программа будет установлена для текущего пользователя.%n%nPython, Tcl/Tk и Python-зависимости включены в установщик. Подходящий установленный Wordcraft будет использован повторно; при его отсутствии Wordcraft {#WordcraftVersion} загрузится с официальной страницы и проверится по SHA-256.%n%nПрава администратора не требуются. Существующие установки Python и Wordcraft не изменяются.
english.WelcomeLabel2=Setup installs the application for the current user.%n%nPython, Tcl/Tk and Python packages are included. A compatible existing Wordcraft is reused; otherwise Wordcraft {#WordcraftVersion} is downloaded from its official release and verified using SHA-256.%n%nAdministrator rights are not required. Existing Python and Wordcraft installations are left unchanged.

[CustomMessages]
russian.DesktopIcon=Создать ярлык на рабочем столе
english.DesktopIcon=Create a desktop shortcut
russian.RunProgram=Открыть нормоконтроль
english.RunProgram=Open the application
russian.Downloading=Загрузка Wordcraft {#WordcraftVersion}
english.Downloading=Downloading Wordcraft {#WordcraftVersion}
russian.DownloadingDescription=Официальный архив проверяется по контрольной сумме SHA-256.
english.DownloadingDescription=The official archive is verified using its SHA-256 checksum.
russian.DownloadError=Не удалось подготовить Wordcraft. Проверьте подключение к Интернету и повторите установку. Для установки без сети передайте /WORDCRAFTARCHIVE="полный путь к официальному ZIP".%n%n
english.DownloadError=Could not prepare Wordcraft. Check your Internet connection and try again. For offline installation pass /WORDCRAFTARCHIVE="full path to the official ZIP".%n%n
russian.UnownedDirectory=Выбранная папка содержит другие файлы и не является установкой нормоконтроля. Выберите новую пустую папку.
english.UnownedDirectory=The selected folder contains other files and is not an existing installation. Choose a new empty folder.
russian.Extracting=Распаковка Wordcraft…
english.Extracting=Extracting Wordcraft…
russian.Verifying=Проверка установленной программы и зависимостей…
english.Verifying=Verifying the installed application and dependencies…
russian.VerifyError=Проверка установки завершилась ошибкой. Подробности находятся в install-report.json и журнале установщика. Повторите установку после устранения причины.
english.VerifyError=Installation verification failed. See install-report.json and the setup log for details. Correct the problem and run setup again.
russian.RuntimeSummary=Python, Tcl/Tk и PyMuPDF: автономная среда программы (не меняет системный Python).
english.RuntimeSummary=Python, Tcl/Tk and PyMuPDF: a private application runtime (does not change system Python).
russian.WordcraftReuse=Wordcraft: найден совместимый компонент; будет использован:
english.WordcraftReuse=Wordcraft: a compatible existing component will be reused:
russian.WordcraftDownload=Wordcraft: совместимая установка не найдена; будет загружена приватная копия {#WordcraftVersion}.
english.WordcraftDownload=Wordcraft: no compatible installation found; a private copy {#WordcraftVersion} will be downloaded.
russian.ExplicitWordcraftError=Указанный WORDCRAFTCLI отсутствует, не запускается или имеет неподдерживаемую версию. Нужен wordcraft-cli не ниже {#WordcraftVersion}: 
english.ExplicitWordcraftError=The supplied WORDCRAFTCLI is missing, cannot run, or has an unsupported version. wordcraft-cli {#WordcraftVersion} or newer is required: 

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked

[Files]
Source: "{#StageDir}\app\*"; DestDir: "{app}"; Excludes: ".normokontrol-installed.json"; Flags: ignoreversion recursesubdirs createallsubdirs
; Keep the ownership marker with preserved settings/results so reinstalling into
; that nonempty application folder remains possible after uninstall.
Source: "{#StageDir}\app\.normokontrol-installed.json"; DestDir: "{app}"; Flags: ignoreversion uninsneveruninstall
Source: "{#StageDir}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Нормоконтроль ИрГУПС"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\normokontrol.py"" --gui"; WorkingDir: "{app}"
Name: "{group}\Удалить нормоконтроль"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Нормоконтроль ИрГУПС"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\normokontrol.py"" --gui"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "-E -s ""{app}\normokontrol.py"" --gui"; WorkingDir: "{app}"; Description: "{cm:RunProgram}"; Flags: nowait postinstall skipifsilent

[InstallDelete]
; A repair/upgrade installs a complete private runtime. Do not retain obsolete
; package files or an incompatible previous Python ABI. Destination ownership
; was validated in PrepareToInstall; user settings/results are outside runtime.
Type: filesandordirs; Name: "{app}\runtime"

[UninstallDelete]
; Only private vendor/cache directories: never recursively delete {app} or user results.
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\wordcraft"
Type: filesandordirs; Name: "{app}\scripts\__pycache__"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\install-report.json"
Type: files; Name: "{app}\.normokontrol-dependencies.json"

[Code]
var
  DownloadPage: TDownloadWizardPage;
  WordcraftArchive: String;
  ExistingWordcraft: String;
  ManagedWordcraft: Boolean;
  VerificationPassed: Boolean;

function CompatibleWordcraft(const Candidate: String): Boolean;
var
  ExitCode, Index, EndIndex: Integer;
  Captured: TExecOutput;
  VersionText: String;
  InstalledVersion, MinimumVersion: Int64;
begin
  Result := False;
  if (Candidate = '') or not FileExists(Candidate) then
    Exit;
  try
    if not ExecAndCaptureOutput(Candidate, '--version', ExtractFileDir(Candidate),
        SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode, Captured) then
      Exit;
    if (ExitCode <> 0) or Captured.Error then
      Exit;
    for Index := 0 to GetArrayLength(Captured.StdOut) - 1 do
    begin
      VersionText := Trim(Captured.StdOut[Index]);
      if Pos('wordcraft-cli ', VersionText) = 1 then
      begin
        Delete(VersionText, 1, Length('wordcraft-cli '));
        EndIndex := 1;
        while (EndIndex <= Length(VersionText)) and
            (((VersionText[EndIndex] >= '0') and (VersionText[EndIndex] <= '9')) or
             (VersionText[EndIndex] = '.')) do
          EndIndex := EndIndex + 1;
        VersionText := Copy(VersionText, 1, EndIndex - 1);
        if StrToVersion(VersionText, InstalledVersion) and
            StrToVersion('{#WordcraftVersion}', MinimumVersion) then
          Result := ComparePackedVersion(InstalledVersion, MinimumVersion) >= 0;
        if Result then
          Log('Compatible Wordcraft found: ' + Candidate + ' (' + VersionText + ')');
        Exit;
      end;
    end;
  except
    Log('Wordcraft detection failed: ' + Candidate + ': ' + GetExceptionMessage);
  end;
end;

function FindExistingWordcraft: String;
var
  Candidate: String;
begin
  Result := '';
  Candidate := ExpandConstant('{param:WORDCRAFTCLI|}');
  if Candidate <> '' then
  begin
    if not CompatibleWordcraft(Candidate) then
      RaiseException(CustomMessage('ExplicitWordcraftError') + Candidate);
    Result := Candidate;
    Exit;
  end;
  Candidate := GetPreviousData('wordcraft_cli', '');
  if not CompatibleWordcraft(Candidate) then
    Candidate := ExpandConstant('{app}\wordcraft\{#WordcraftArchiveRoot}\wordcraft-cli.exe');
  if not CompatibleWordcraft(Candidate) then
    Candidate := ExpandConstant('{app}\wordcraft\wordcraft-cli.exe');
  if not CompatibleWordcraft(Candidate) then
    Candidate := GetEnv('WORDCRAFT_CLI');
  if not CompatibleWordcraft(Candidate) then
    Candidate := FileSearch('wordcraft-cli.exe', GetEnv('PATH'));
  if not CompatibleWordcraft(Candidate) then
    Candidate := ExpandConstant('{localappdata}\Programs\ArtCraft\WordCraft\wordcraft-cli.exe');
  if not CompatibleWordcraft(Candidate) then
    Candidate := ExpandConstant('{localappdata}\ArtCraft\WordCraft\wordcraft-cli.exe');
  if not CompatibleWordcraft(Candidate) then
    Candidate := ExpandConstant('{pf64}\ArtCraft\WordCraft\wordcraft-cli.exe');
  if CompatibleWordcraft(Candidate) then
    Result := Candidate;
end;

function DirectoryHasEntries(const Directory: String): Boolean;
var
  Entry: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Directory) + '*', Entry) then
  begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then
        begin
          Result := True;
          Break;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function DestinationError: String;
var
  Destination: String;
begin
  Result := '';
  Destination := ExpandConstant('{app}');
  if DirExists(Destination) and DirectoryHasEntries(Destination) and
      not FileExists(AddBackslash(Destination) + '.normokontrol-installed.json') then
    Result := CustomMessage('UnownedDirectory');
end;

function OnDownloadProgress(const Url, FileName: String;
  const Progress, ProgressMax: Int64): Boolean;
begin
  Result := not DownloadPage.AbortedByUser;
end;

procedure InitializeWizard;
begin
  VerificationPassed := False;
  DownloadPage := CreateDownloadPage(CustomMessage('Downloading'),
    CustomMessage('DownloadingDescription'), @OnDownloadProgress);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  LocalArchive, ManagedPrefix: String;
begin
  Result := DestinationError;
  if Result <> '' then
    Exit;
  try
    LocalArchive := ExpandConstant('{param:WORDCRAFTARCHIVE|}');
    if (LocalArchive <> '') and (ExpandConstant('{param:WORDCRAFTCLI|}') <> '') then
      RaiseException('Use WORDCRAFTARCHIVE or WORDCRAFTCLI, not both.');
    ExistingWordcraft := '';
    ManagedWordcraft := False;
    if LocalArchive = '' then
      ExistingWordcraft := FindExistingWordcraft;
    if ExistingWordcraft <> '' then
    begin
      ManagedPrefix := AddBackslash(ExpandConstant('{app}\wordcraft'));
      ManagedWordcraft := CompareText(Copy(ExpandFileName(ExistingWordcraft),
        1, Length(ManagedPrefix)), ManagedPrefix) = 0;
      Log('Reusing Wordcraft: ' + ExistingWordcraft);
      Exit;
    end;
    if LocalArchive <> '' then
    begin
      if not FileExists(LocalArchive) then
        RaiseException('Wordcraft archive not found: ' + LocalArchive);
      if CompareText(GetSHA256OfFile(LocalArchive), '{#WordcraftSHA256}') <> 0 then
        RaiseException('Wordcraft SHA-256 mismatch: ' + LocalArchive);
      { Freeze the validated bytes before copying any application files. }
      WordcraftArchive := ExpandConstant('{tmp}\wordcraft-portable.zip');
      if not CopyFile(LocalArchive, WordcraftArchive, False) then
        RaiseException('Could not copy Wordcraft archive to the temporary folder.');
      if CompareText(GetSHA256OfFile(WordcraftArchive), '{#WordcraftSHA256}') <> 0 then
        RaiseException('Wordcraft archive changed while copying.');
    end
    else
    begin
      DownloadPage.Clear;
      DownloadPage.Add('{#WordcraftURL}', 'wordcraft-portable.zip', '{#WordcraftSHA256}');
      DownloadPage.Show;
      try
        DownloadPage.Download;
        WordcraftArchive := ExpandConstant('{tmp}\wordcraft-portable.zip');
      finally
        DownloadPage.Hide;
      end;
    end;
  except
    Result := CustomMessage('DownloadError') + GetExceptionMessage;
    Log(Result);
  end;
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo,
  MemoTypeInfo, MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
var
  Candidate: String;
begin
  Result := MemoDirInfo + NewLine + NewLine + CustomMessage('RuntimeSummary') + NewLine;
  try
    Candidate := '';
    if ExpandConstant('{param:WORDCRAFTARCHIVE|}') = '' then
      Candidate := FindExistingWordcraft;
    if Candidate <> '' then
      Result := Result + CustomMessage('WordcraftReuse') + NewLine + Space + Candidate
    else
      Result := Result + CustomMessage('WordcraftDownload');
  except
    Result := Result + GetExceptionMessage;
  end;
  if MemoTasksInfo <> '' then
    Result := Result + NewLine + NewLine + MemoTasksInfo;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  if ExistingWordcraft <> '' then
    SetPreviousData(PreviousDataKey, 'wordcraft_cli', ExistingWordcraft);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ExitCode: Integer;
  Parameters: String;
begin
  if CurStep = ssPostInstall then
  begin
    if ExistingWordcraft = '' then
    begin
      WizardForm.StatusLabel.Caption := CustomMessage('Extracting');
      ExtractArchive(WordcraftArchive, ExpandConstant('{app}\wordcraft'), '', True, nil);
      ExistingWordcraft := ExpandConstant('{app}\wordcraft\{#WordcraftArchiveRoot}\wordcraft-cli.exe');
      ManagedWordcraft := True;
    end;
    WizardForm.StatusLabel.Caption := CustomMessage('Verifying');
    Parameters := '-E -s ' + AddQuotes(ExpandConstant('{app}\scripts\setup_support.py')) +
      ' --verify-install --wordcraft ' + AddQuotes(ExistingWordcraft) +
      ' --output ' + AddQuotes(ExpandConstant('{app}\install-report.json'));
    if ManagedWordcraft then
      Parameters := Parameters + ' --managed-wordcraft';
    if not Exec(ExpandConstant('{app}\runtime\python.exe'), Parameters,
        ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) then
      RaiseException(CustomMessage('VerifyError'));
    if ExitCode <> 0 then
      RaiseException(CustomMessage('VerifyError'));
    VerificationPassed := True;
  end;
end;

function GetCustomSetupExitCode: Integer;
begin
  if VerificationPassed then
    Result := 0
  else
    Result := 1;
end;
