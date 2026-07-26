@echo off
REM Launch the PoE1 build price checker from anywhere.
REM Usage: bpc "https://poe.ninja/poe1/builds/<league>/character/<account>/<name>"
python "%~dp0run.py" %*
