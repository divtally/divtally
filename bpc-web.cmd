@echo off
REM Launch the PoE1 build price checker web UI (opens http://127.0.0.1:8765).
REM Optional args pass through, e.g.: bpc-web.cmd --port 9000 --no-browser
python "%~dp0run.py" --web %*
if errorlevel 1 (
  echo.
  echo [bpc-web] The server exited with an error ^(see the message above^).
  echo If 'python' was not found, install Python 3 or use the full path to python.exe.
  pause
)
