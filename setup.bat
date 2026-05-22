@echo off
REM NodeAva Workshop Kit — Windows launcher.
REM
REM Double-click this from Windows Explorer. It checks WSL2 is available,
REM then hands off to setup.sh inside a WSL2 shell.
REM
REM Everything installs and runs inside WSL2 — Docker, Ollama, and the
REM container stack. We do NOT use Docker Desktop on Windows; native
REM Docker inside WSL2 is simpler, faster on the WSL2 filesystem, and
REM has no licensing constraints.

setlocal enabledelayedexpansion

echo.
echo  ┌─────────────────────────────────────────────────────────────────┐
echo  │   NodeAva Workshop Kit — Windows launcher                       │
echo  │                                                                 │
echo  │   This kit runs inside WSL2 (Windows Subsystem for Linux).      │
echo  │   We'll check for WSL2 then launch the setup script there.      │
echo  └─────────────────────────────────────────────────────────────────┘
echo.

REM Check WSL2 is available
where wsl >nul 2>&1
if errorlevel 1 (
    echo  [!] WSL is not installed.
    echo.
    echo      Open PowerShell as Administrator and run:
    echo          wsl --install
    echo.
    echo      Reboot when prompted, then double-click setup.bat again.
    echo.
    pause
    exit /b 1
)

echo  [+] WSL detected. Checking distros...
wsl --list --quiet 2>nul | findstr /v "^$" >nul
if errorlevel 1 (
    echo  [!] No WSL distribution installed.
    echo.
    echo      Install Ubuntu from the Microsoft Store, OR run:
    echo          wsl --install -d Ubuntu
    echo.
    echo      Then re-run this script.
    echo.
    pause
    exit /b 1
)

echo  [+] WSL distro found.
echo.
echo  [*] Launching setup.sh inside WSL2...
echo.

REM Determine WSL path equivalent of this folder
set "WIN_PATH=%~dp0"
REM Replace backslashes with forward slashes
set "WSL_PATH=%WIN_PATH:\=/%"
REM Convert drive letter C: → /mnt/c
set "DRIVE=%WSL_PATH:~0,1%"
set "DRIVE_LC=%DRIVE%"
for %%i in (a b c d e f g h i j k l m n o p q r s t u v w x y z) do (
    if /i "%DRIVE%"=="%%i" set "DRIVE_LC=%%i"
)
set "WSL_PATH=/mnt/%DRIVE_LC%%WSL_PATH:~2%"

echo  WSL path:  %WSL_PATH%
echo.
echo  ────────────────────────────────────────────────────────────────────
echo  Note: from here you'll see Linux-style output. This is normal —
echo  the kit runs entirely inside WSL2. Docker, Ollama, and the
echo  containers all install natively inside your WSL distro (no Docker
echo  Desktop required). You will be prompted for your WSL sudo password
echo  at a couple of steps.
echo  ────────────────────────────────────────────────────────────────────
echo.
wsl -- bash -c "cd '%WSL_PATH%' && chmod +x setup.sh && ./setup.sh"

echo.
echo  Setup script finished. Browse to:
echo      http://localhost:3000
echo.
echo  (Docker and the stack are running inside WSL2 — they keep running
echo  as long as the WSL distro is up. To stop: wsl -- cd ~/nodeava-workshop ^&^& docker compose down)
echo.
pause
endlocal
