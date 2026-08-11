@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

echo [1/3] Checking PyInstaller...
".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo Installing PyInstaller...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
)

echo [2/3] Building (one-dir bundle)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean AIMatting.spec
if errorlevel 1 (
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo [3/3] Copying models and settings into dist...
if exist "models\*.onnx" (
    if not exist "dist\AIMatting\models" mkdir "dist\AIMatting\models"
    xcopy /E /I /Y "models" "dist\AIMatting\models" >nul
)
if exist "settings.json" (
    copy /Y "settings.json" "dist\AIMatting\settings.json" >nul
)
if exist "licenses" (
    if not exist "dist\AIMatting\licenses" mkdir "dist\AIMatting\licenses"
    xcopy /E /I /Y "licenses" "dist\AIMatting\licenses" >nul
)

echo.
echo Done! App is in dist\AIMatting\AIMatting.exe
pause
