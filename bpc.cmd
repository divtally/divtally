@echo off
REM Launch the PoE2 build price checker from anywhere.
REM Usage: bpc "https://poe.ninja/poe2/builds/<league>/character/<account>/<name>"
python "%~dp0run.py" %*
