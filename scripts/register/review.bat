@echo off
rem Double-click to rebuild the findings review page and open it with notes saving to disk.
rem Leave this window open while you review; close it (or Ctrl+C) when done.
cd /d "%~dp0\..\.."
set PY=python
where python >nul 2>nul || set PY=C:\Apps\Anaconda3\python.exe
%PY% scripts\register\build_review.py || (pause & exit /b 1)
%PY% scripts\register\review_server.py
pause
