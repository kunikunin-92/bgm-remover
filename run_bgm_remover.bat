@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
set "VENV_DIR=%ROOT_DIR%.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
set "PIP_EXE=%VENV_DIR%\Scripts\pip.exe"

cd /d "%ROOT_DIR%"

echo ========================================
echo   BGM Remover Launcher
echo ========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYTHON_LAUNCHER=py -3"
) else (
    where python >nul 2>nul
    if %errorlevel%==0 (
        set "PYTHON_LAUNCHER=python"
    ) else (
        echo [ERROR] Python 3 was not found.
        echo Install Python 3.10 or newer, then run this file again.
        pause
        exit /b 1
    )
)

if not exist "%PYTHON_EXE%" (
    echo [INFO] Creating virtual environment...
    call %PYTHON_LAUNCHER% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
)

set "BASE_READY=0"
set "GPU_READY=0"
set "GPU_FOUND=0"
set "NEED_PIP_UPGRADE=0"

echo [INFO] Checking base dependencies...
"%PYTHON_EXE%" -c "import customtkinter, ffmpeg, audio_separator, onnxruntime" >nul 2>nul
if not errorlevel 1 (
    set "BASE_READY=1"
    echo [INFO] Base dependencies already installed.
) else (
    echo [INFO] Base dependencies missing. Installing...
    set "NEED_PIP_UPGRADE=1"
)

if "%NEED_PIP_UPGRADE%"=="1" (
    echo [INFO] Upgrading pip...
    call "%PYTHON_EXE%" -m pip install --upgrade pip
    if errorlevel 1 (
        echo [ERROR] Failed to upgrade pip.
        pause
        exit /b 1
    )
)

if "%BASE_READY%"=="0" (
    call "%PIP_EXE%" install -r "%ROOT_DIR%requirements.txt"
    if errorlevel 1 (
        echo [ERROR] Failed to install requirements.txt.
        pause
        exit /b 1
    )
)

where nvidia-smi >nul 2>nul
if not errorlevel 1 (
    set "GPU_FOUND=1"
)

if "%GPU_FOUND%"=="1" (
    echo [INFO] NVIDIA GPU detected. Checking GPU runtime...
    "%PYTHON_EXE%" -c "import sys, torch, onnxruntime as ort; ok=bool(torch.cuda.is_available()) and ('CUDAExecutionProvider' in ort.get_available_providers()); sys.exit(0 if ok else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "GPU_READY=1"
        echo [INFO] GPU runtime already installed.
    ) else (
        echo [INFO] GPU runtime missing. Installing CUDA dependencies...

        if "%NEED_PIP_UPGRADE%"=="0" (
            echo [INFO] Upgrading pip...
            call "%PYTHON_EXE%" -m pip install --upgrade pip
            if errorlevel 1 (
                echo [ERROR] Failed to upgrade pip.
                pause
                exit /b 1
            )
            set "NEED_PIP_UPGRADE=1"
        )

        call "%PIP_EXE%" install --upgrade "audio-separator[gpu]" onnxruntime-gpu
        if errorlevel 1 (
            echo [WARNING] Failed to install audio-separator GPU extras.
        )

        call "%PIP_EXE%" install --force-reinstall --index-url https://download.pytorch.org/whl/cu124 torch torchvision torchaudio
        if errorlevel 1 (
            echo [WARNING] Failed to install CUDA PyTorch wheels.
        )

        "%PYTHON_EXE%" -c "import sys, torch, onnxruntime as ort; ok=bool(torch.cuda.is_available()) and ('CUDAExecutionProvider' in ort.get_available_providers()); sys.exit(0 if ok else 1)" >nul 2>nul
        if not errorlevel 1 (
            set "GPU_READY=1"
        )
    )
)

if "%GPU_READY%"=="1" (
    echo [INFO] GPU runtime check passed. CUDA mode is available.
) else (
    if "%GPU_FOUND%"=="1" (
        echo [WARNING] GPU runtime check failed. App can still run in CPU mode.
    ) else (
        echo [INFO] NVIDIA GPU not detected. Running in CPU-compatible setup.
    )
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
    echo [WARNING] ffmpeg was not found in PATH.
    echo The app may not work until ffmpeg is installed and added to PATH.
    echo.
)

echo [INFO] Runtime summary:
"%PYTHON_EXE%" -c "import sys; print('python=' + sys.version.split()[0])"
"%PYTHON_EXE%" -c "import torch; print('torch=' + torch.__version__ + ', cuda=' + str(torch.cuda.is_available()))" || echo [WARNING] torch runtime info unavailable
"%PYTHON_EXE%" -c "import onnxruntime as ort; print('onnxruntime providers=' + str(ort.get_available_providers()))" || echo [WARNING] onnxruntime runtime info unavailable
echo.

echo [INFO] Launching GUI...
call "%PYTHON_EXE%" "%ROOT_DIR%main.py"

if errorlevel 1 (
    echo.
    echo [ERROR] The application exited with an error.
    pause
    exit /b 1
)

endlocal
