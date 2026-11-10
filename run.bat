@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ======================================================================
echo  KOMPSAT Processor Launcher (Smart Environment Detection)
echo ======================================================================
echo.

set "PY_CMD="

REM 1. Check System Python with both Tkinter & GDAL (Fastest & Most Stable)
echo [*] Checking System Python environment...
where python >nul 2>&1
if not errorlevel 1 (
    python -c "import tkinter; import osgeo.gdal; print('OK')" >nul 2>&1
    if not errorlevel 1 (
        set "PY_CMD=python -u"
        echo [+] Found System Python with Tkinter and GDAL.
        goto :RUN_APP
    )
    
    REM Check if Python has Tkinter but missing GDAL
    python -c "import tkinter; print('OK')" >nul 2>&1
    if not errorlevel 1 (
        echo [*] Python detected with Tkinter, checking GDAL installation...
        for %%W in ("wheels\*.whl") do (
            if exist "%%~W" (
                echo [*] Installing local GDAL wheel: %%~nxW
                python -m pip install "%%~W" >nul 2>&1
                python -c "import osgeo.gdal; print('OK')" >nul 2>&1
                if not errorlevel 1 (
                    set "PY_CMD=python -u"
                    echo [+] Successfully configured GDAL via local wheel.
                    goto :RUN_APP
                )
            )
        )
    )
)

REM 2. Check QGIS Python environment (Only if Tkinter is supported)
echo [*] Checking QGIS Python environment...
for /d %%G in ("C:\Program Files\QGIS*") do (
    if not defined PY_CMD (
        if exist "%%G\bin\python-qgis-ltr.bat" (
            call "%%G\bin\python-qgis-ltr.bat" -c "import tkinter; import osgeo.gdal" >nul 2>&1
            if not errorlevel 1 (
                set "PY_CMD=call "%%G\bin\python-qgis-ltr.bat""
                echo [+] Found QGIS LTR with Tkinter support: %%G
            )
        ) else if exist "%%G\bin\python-qgis.bat" (
            call "%%G\bin\python-qgis.bat" -c "import tkinter; import osgeo.gdal" >nul 2>&1
            if not errorlevel 1 (
                set "PY_CMD=call "%%G\bin\python-qgis.bat""
                echo [+] Found QGIS with Tkinter support: %%G
            )
        )
    )
)

if defined PY_CMD goto :RUN_APP

REM 3. Check Conda Environment (Fallback)
echo [*] Checking Conda environment...
where conda >nul 2>&1
if not errorlevel 1 (
    conda info --envs | findstr /C:"komp " >nul 2>&1
    if not errorlevel 1 (
        echo [+] Found Conda 'komp' environment.
        call conda activate komp
        set "PY_CMD=python -u"
        goto :RUN_APP
    )
)

REM If no suitable environment found
echo.
echo [ERROR] No suitable Python environment with Tkinter + GDAL detected.
echo.
echo Please ensure Python (with Tkinter) and GDAL are installed.
echo If using standard Python, you can install GDAL using:
echo    pip install wheels\gdal-3.11.4-cp312-cp312-win_amd64.whl
echo.
pause
exit /b 1

:RUN_APP
echo.
echo [*] Starting KOMPSAT Processor GUI...
echo.
%PY_CMD% "src\gui.py"
if errorlevel 1 (
    echo.
    echo [ERROR] Application terminated with an error.
    pause
    exit /b 1
)

exit /b 0
