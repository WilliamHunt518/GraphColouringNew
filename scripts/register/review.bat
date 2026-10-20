@echo off
rem Double-click to rebuild the findings review page and open it with notes saving to disk.
rem Leave this window open while you review; close it (or Ctrl+C) when done.
cd /d "%~dp0\..\.."
set PY=python
where python >nul 2>nul || set PY=C:\Apps\Anaconda3\python.exe
rem the on-screen clips: cuts only missing ones; harmless if it fails on a machine without the recordings or ffmpeg
%PY% scripts\register\build_demos.py
rem the quote audio clips: likewise cuts only missing or moved ones (needs Results\Narration\ and ffmpeg)
%PY% scripts\register\build_audio.py
%PY% scripts\register\build_review.py || (pause & exit /b 1)
%PY% scripts\register\review_server.py
pause
