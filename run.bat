@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
if exist .env for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
  if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
)
uv run python -m audiobook %*
