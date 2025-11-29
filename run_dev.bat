@echo off
echo Starting FA CS Automator Dev Server...
echo.
echo Note: This will launch both the React Server and the Electron App.
echo Please wait for the window to appear...
echo.

SET PATH=%PATH%;C:\Program Files\nodejs

SET ELECTRON_RUN_AS_NODE=
call venv\Scripts\activate.bat
call npm run dev
pause
