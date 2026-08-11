@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\pythonw.exe" (
    echo [ERROR] Virtual environment not found.
    echo Please run setup.bat first to install dependencies.
    pause
    exit /b 1
)

if not exist "models\*.onnx" (
    echo [HINT] No model downloaded yet.
    echo After the app opens, go to "Model Manager" to download the model.
)

start "" ".venv\Scripts\pythonw.exe" "run.py"
echo AIMatting is starting... If nothing happens, check crash.log in this folder.
