@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==== 打包 灵动岛.exe ====
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name 灵动岛 ^
  --add-data "轮换图;轮换图" ^
  dynamic_island.py
if errorlevel 1 (
  echo.
  echo 打包失败：先装 PyInstaller  ^( python -m pip install pyinstaller ^)
  pause
  exit /b 1
)
echo.
echo 完成：dist\灵动岛.exe
pause
