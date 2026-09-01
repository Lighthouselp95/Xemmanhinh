@echo off
setlocal EnableDelayedExpansion

:: 1. Kiem tra va yeu cau quyen Administrator (UAC Auto-Elevation)
fltmc >nul 2>&1 || (
    echo [INFO] Dang yeu cau quyen Administrator de cai dat Driver...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

title Cai Dat Man Hinh Ao (Virtual Display Driver - VDD)
color 0b
echo ==============================================================================
echo        HE THONG CAI DAT MAN HINH AO (VIRTUAL DISPLAY DRIVER)
echo ==============================================================================
echo.

:: 2. Tim kiem thu muc chua Driver (Uu tien thu muc hien tai hoac tools project)
set "CURR_DIR=%~dp0"
set "LOCAL_TOOLS=C:\Users\Hai Dang\Xemmanhinh\tools\virtual_display_driver"
set "WINGET_DIR=%LOCALAPPDATA%\Microsoft\WinGet\Packages\VirtualDrivers.Virtual-Display-Driver_Microsoft.Winget.Source_8wekyb3d8bbwe"

set "DRIVER_DIR="

if exist "%CURR_DIR%MttVDD.inf" (
    set "DRIVER_DIR=%CURR_DIR%"
) else if exist "%LOCAL_TOOLS%\MttVDD.inf" (
    set "DRIVER_DIR=%LOCAL_TOOLS%"
) else if exist "%WINGET_DIR%\SignedDrivers\x86\VDD\MttVDD.inf" (
    set "DRIVER_DIR=%WINGET_DIR%\SignedDrivers\x86\VDD"
)

:: 3. Neu khong tim thay driver, tu dong tai qua WinGet
if "%DRIVER_DIR%"=="" (
    echo [WARN] Chua tim thay Driver tren may. Dang tu dong tai qua WinGet...
    winget install --id=VirtualDrivers.Virtual-Display-Driver -e --accept-source-agreements --accept-package-agreements
    if exist "%WINGET_DIR%\SignedDrivers\x86\VDD\MttVDD.inf" (
        set "DRIVER_DIR=%WINGET_DIR%\SignedDrivers\x86\VDD"
    )
)

if "%DRIVER_DIR%"=="" (
    echo [LOI] Khong tim thay tep driver MttVDD.inf. Vui long kiem tra lai!
    pause
    exit /b 1
)

:: Xac dinh duong dan file thiet yeu
set "INF_PATH=%DRIVER_DIR%\MttVDD.inf"

if exist "%DRIVER_DIR%\devcon.exe" (
    set "DEVCON=%DRIVER_DIR%\devcon.exe"
) else if exist "%LOCAL_TOOLS%\devcon.exe" (
    set "DEVCON=%LOCAL_TOOLS%\devcon.exe"
) else (
    set "DEVCON=%WINGET_DIR%\Dependencies\devcon.exe"
)

if exist "%DRIVER_DIR%\vdd_settings.xml" (
    set "CONFIG_SRC=%DRIVER_DIR%\vdd_settings.xml"
) else if exist "%LOCAL_TOOLS%\vdd_settings.xml" (
    set "CONFIG_SRC=%LOCAL_TOOLS%\vdd_settings.xml"
) else (
    set "CONFIG_SRC=%WINGET_DIR%\Dependencies\vdd_settings.xml"
)

set "TARGET_DIR=C:\VirtualDisplayDriver"

echo [1/3] Thiet lap thu muc cau hinh: %TARGET_DIR%...
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"
copy /y "%CONFIG_SRC%" "%TARGET_DIR%\vdd_settings.xml" >nul

echo [2/3] Nap Driver vao he thong Windows (pnputil)...
pnputil /add-driver "%INF_PATH%" /install

echo [3/3] Khoi tao thiet bi Man Hinh Ao (Root\MttVDD)...
"%DEVCON%" install "%INF_PATH%" "Root\MttVDD"

echo.
echo ==============================================================================
echo   [THANH CONG] Man hinh ao da duoc cai dat va kich hoat!
echo   Thiet bi: Generic Monitor (VDD by MTT)
echo   Ban co the rut day HDMI ma luong stream van chay muot ma khong bi den.
echo ==============================================================================
echo.
pause
