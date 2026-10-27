@echo off
rem Builds WDA-Konfigurator.exe (single file).
rem Requirements: python -m pip install pyinstaller pillow
rem
rem   build.bat            full build: Gen 1 + Gen 1.5 firmware and wallpaper previews embedded.
rem                        ~60 MB, updates work offline. Contains Microsoft firmware -> private use only.
rem   build.bat --clean    release build: no firmware, no wallpaper previews. ~12 MB.
rem                        The app downloads the firmware from Microsoft when it is needed.
rem                        This is the only variant that may be published.
setlocal
set ROOT=%~dp0..
set WORK=%TEMP%\wda-konfigurator-build

set CLEAN=
if /i "%~1"=="--clean" set CLEAN=1
if /i "%~1"=="-clean" set CLEAN=1

set FW=
set THUMBS=
if defined CLEAN (
  echo Release build: no Microsoft firmware and no wallpaper previews are embedded.
) else (
  rem Official firmware for Gen 1 (Type_S) and Gen 1.5: download from Microsoft if it is not in the
  rem library yet. Gen 3 (128 MB) is never embedded; the app downloads it when a Gen 3 adapter needs it.
  dir /s /b "%ROOT%\firmware\Type_S\*.sbin" >nul 2>&1 || (
    python "%ROOT%\wda_tool.py" firmware fetch --type Type_S || exit /b 1
  )
  dir /s /b "%ROOT%\firmware\Gen-1.5\*.sbin" >nul 2>&1 || (
    python "%ROOT%\wda_tool.py" firmware fetch --type Gen-1.5 || exit /b 1
  )
  set FW=--add-data "%ROOT%\firmware\Type_S;firmware\Type_S" --add-data "%ROOT%\firmware\Gen-1.5;firmware\Gen-1.5"

  rem Wallpaper previews only if a copy of the original app is present (app-source\)
  if exist "%ROOT%\app-source\Images\Wallpapers\1.png" (
    python "%~dp0make_thumbs.py" "%ROOT%\app-source\Images\Wallpapers" "%~dp0thumbs" || exit /b 1
  )
  if exist "%~dp0thumbs\1.png" set THUMBS=--add-data "%~dp0thumbs;thumbs"
)

python "%~dp0make_icon.py" "%~dp0wda.ico" || exit /b 1

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WDA-Konfigurator ^
  --icon "%~dp0wda.ico" ^
  --add-data "%~dp0wda.ico;." ^
  --add-data "%ROOT%\locales;locales" ^
  %THUMBS% ^
  %FW% ^
  --exclude-module numpy ^
  --workpath "%WORK%" --specpath "%WORK%" --distpath "%ROOT%" ^
  "%ROOT%\wda_gui.py" || exit /b 1
echo.
echo Done: %ROOT%\WDA-Konfigurator.exe
if not defined CLEAN echo Note: this build embeds Microsoft firmware - do not publish it.
