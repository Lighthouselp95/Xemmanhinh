@echo off
setlocal EnableDelayedExpansion

fltmc >nul 2>&1 || (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

title Quan Ly Man Hinh Ao (Virtual Display Driver)
color 0e

set "CURR_DIR=%~dp0"
set "LOCAL_TOOLS=C:\Users\Hai Dang\Xemmanhinh\tools\virtual_display_driver"
set "WINGET_DIR=%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe\Dependencies"

if exist "%CURR_DIR%devcon.exe" (
    set "DEVCON=%CURR_DIR%devcon.exe"
) else if exist "%LOCAL_TOOLS%\devcon.exe" (
    set "DEVCON=%LOCAL_TOOLS%\devcon.exe"
) else (
    set "DEVCON=%WINGET_DIR%\devcon.exe"
)

echo ==============================================================================
echo                 QUAN LY TRANG THAI MAN HINH AO (VDD)
echo ==============================================================================
echo.
echo 1. BAT man hinh ao (Enable)
echo 2. TAT man hinh ao (Disable)
echo 3. GO BO man hinh ao khoi he thong (Remove)
echo 4. KIEM TRA trang thai thiet bi (Status)
echo.
set /p opt="Nhap lua chon cua ban (1/2/3/4): "
echo.

if "%opt%"=="1" (
    echo Dang BAT man hinh ao...
    "%DEVCON%" enable "Root\MttVDD"
)
if "%opt%"=="2" (
    echo Dang TAT man hinh ao...
    "%DEVCON%" disable "Root\MttVDD"
)
if "%opt%"=="3" (
    echo Dang GO BO man hinh ao...
    "%DEVCON%" remove "Root\MttVDD"
)
if "%opt%"=="4" (
    echo Trang thai thiet bi hien tai:
    "%DEVCON%" status "Root\MttVDD"
)

echo.
pause
