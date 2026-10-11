@echo off
rem ============================================================================
rem  Homeserver - installazione automatica su Windows (WSL2 + Ubuntu + Docker)
rem  Doppio clic su questo file. Si puo' rilanciare quando vuoi (aggiorna senza
rem  toccare .env e dati). Facoltativo: setup-windows.bat Ubuntu-24.04
rem ============================================================================
setlocal EnableExtensions EnableDelayedExpansion
title Homeserver - installazione automatica

set "DISTRO=%~1"
if "%DISTRO%"=="" set "DISTRO=Ubuntu"

rem --- 1. servono i permessi di amministratore (per WSL e per l'attivita' pianificata)
net session >nul 2>&1
if errorlevel 1 (
  echo Chiedo i permessi di amministratore: conferma nella finestra che compare.
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%DISTRO%' -Verb RunAs"
  exit /b 0
)

cd /d "%~dp0"
set "WP=%~dp0"
set "WP=%WP:~0,-1%"
if not "%WP: =%"=="%WP%" (
  echo.
  echo ERRORE: il percorso di questa cartella contiene spazi:
  echo   %WP%
  echo Sposta la cartella del progetto in un percorso senza spazi, per esempio C:\homeserver,
  echo e rilancia questo file da li'.
  goto fine
)

rem --- 2. WSL e Ubuntu presenti?
where wsl >nul 2>&1
if errorlevel 1 (
  echo.
  echo ERRORE: WSL non e' disponibile su questo Windows. Serve Windows 10 22H2 o Windows 11 aggiornato.
  goto fine
)

wsl -d %DISTRO% -e true >nul 2>&1
if errorlevel 1 (
  echo.
  echo Ubuntu non e' ancora installato: lo installo ora.
  wsl --install -d %DISTRO%
  echo.
  echo ============================================================================
  echo  COSA FARE ORA:
  echo   1. Se Windows chiede di riavviare: riavvia il PC.
  echo   2. Dopo l'installazione si apre una finestra nera di Ubuntu che chiede
  echo      "username" e "password": scegli un nome semplice senza spazi e una password
  echo      che ricordi ^(mentre scrivi la password non compare nulla: e' normale^).
  echo   3. Quando Ubuntu ti da' il prompt, chiudi la finestra e rilancia questo file.
  echo ============================================================================
  goto fine
)

set "WSLUSER="
for /f "delims=" %%u in ('wsl -d %DISTRO% -e whoami') do set "WSLUSER=%%u"
if /i "%WSLUSER%"=="root" (
  echo.
  echo ERRORE: Ubuntu e' configurato solo con l'utente root. Serve un utente normale.
  echo Apri PowerShell e scrivi, sostituendo mario con un nome a tua scelta:
  echo   wsl -d %DISTRO% -u root -e adduser mario
  echo   wsl -d %DISTRO% -u root -e usermod -aG sudo mario
  echo   wsl -d %DISTRO% -u root -e bash -c "printf '[user]\ndefault=mario\n' >> /etc/wsl.conf"
  echo   wsl --terminate %DISTRO%
  echo Poi rilancia questo file.
  goto fine
)
echo Utente Ubuntu: %WSLUSER%

rem --- 3. memoria data a WSL: meta' della RAM, tra 4 e 8 GB ^(solo se non hai gia' un .wslconfig^)
if not exist "%UserProfile%\.wslconfig" (
  set "RAMGB=8"
  for /f %%m in ('powershell -NoProfile -Command "[math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)"') do set "RAMGB=%%m"
  set /a WSLMEM=!RAMGB!/2
  if !WSLMEM! lss 4 set "WSLMEM=4"
  if !WSLMEM! gtr 8 set "WSLMEM=8"
  (
    echo [wsl2]
    echo memory=!WSLMEM!GB
    echo swap=4GB
  ) > "%UserProfile%\.wslconfig"
  echo Creato %UserProfile%\.wslconfig: WSL puo' usare !WSLMEM! GB di RAM ^(il PC ne ha !RAMGB!^).
  if !RAMGB! lss 8 echo ATTENZIONE: con meno di 8 GB di RAM Immich puo' essere lento.
) else (
  echo .wslconfig gia' presente: lo lascio com'e'.
)

rem --- 4. installazione dentro Ubuntu
set "LP="
for /f "delims=" %%p in ('wsl -d %DISTRO% -e wslpath -u "%WP:\=/%"') do set "LP=%%p"
if "%LP%"=="" (
  echo ERRORE: non riesco a convertire il percorso %WP% per Ubuntu.
  goto fine
)
echo.
echo Avvio l'installazione dentro Ubuntu. Ti chiedera' la password di Ubuntu.
echo.
wsl -d %DISTRO% -e bash "%LP%/scripts/install-linux.sh" "%LP%"
if errorlevel 1 (
  echo.
  echo L'installazione si e' fermata con un errore: leggi il messaggio qui sopra.
  echo Puoi rilanciare questo file dopo aver risolto: riparte da dove serve.
  goto fine
)

rem --- 5. tiene acceso WSL anche a finestre chiuse (altrimenti i servizi si fermano)
echo.
echo Configuro l'avvio automatico di WSL ad ogni accesso a Windows...
schtasks /Create /F /TN "Homeserver-WSL" /SC ONLOGON /RL HIGHEST /TR "powershell.exe -NoProfile -WindowStyle Hidden -Command \"wsl.exe -d %DISTRO% -u root -e sleep infinity\"" >nul
if errorlevel 1 (echo ATTENZIONE: attivita' pianificata non creata: dopo un riavvio dovrai avviare WSL a mano.) else (echo Fatto: attivita' "Homeserver-WSL".)

set "ANS="
set /p "ANS=Disattivo la sospensione automatica quando il PC e' alimentato? (S/N): "
if /i "!ANS!"=="S" (
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
  echo Sospensione disattivata con il PC alimentato.
)

rem --- 6. riavvio di WSL per applicare .wslconfig, systemd e gruppo docker
echo.
echo Riavvio WSL per applicare le impostazioni ^(i servizi ripartono da soli^)...
wsl --shutdown
start "" /min powershell.exe -NoProfile -WindowStyle Hidden -Command "wsl.exe -d %DISTRO% -u root -e sleep infinity"
echo Attendo l'avvio dei servizi ^(circa 45 secondi^)...
timeout /t 45 /nobreak >nul
wsl -d %DISTRO% -e docker ps --format "table {{.Names}}\t{{.Status}}"

echo.
echo ============================================================================
echo  FATTO.  Pannello:  http://localhost:8088   ^(token mostrato prima^)
echo  Il progetto e' in Ubuntu: \\wsl$\%DISTRO%\home\%WSLUSER%\homeserver
echo  Telefono: segui docs\tailscale.md
echo  Se un servizio non risulta "Up" qui sopra, aspetta un minuto e riprova:
echo    wsl -d %DISTRO% -e docker ps
echo ============================================================================

:fine
echo.
pause
endlocal
