@echo off
REM Launch the auto-detecting screen recorder (captures all monitors + cursor,
REM full physical resolution, taskbar cropped out). Press q to stop.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0record-screens.ps1" %*
