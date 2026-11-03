@echo off
chcp 65001 > nul
REM S&P 500 분석기 실행파일(exe) 빌드 스크립트
REM 결과물: dist\SP500Analysis.exe

pip install pyinstaller pandas numpy matplotlib

pyinstaller --noconfirm --clean --onefile --console ^
    --name SP500Analysis ^
    --icon assets\sp500.ico ^
    --add-data "S&P 500 과거 데이터.csv;." ^
    --hidden-import matplotlib.backends.backend_tkagg ^
    --exclude-module PyQt6 ^
    --exclude-module PySide6 ^
    --exclude-module shiboken6 ^
    --exclude-module scipy ^
    --exclude-module seaborn ^
    --exclude-module IPython ^
    --exclude-module openpyxl ^
    --exclude-module selenium ^
    --exclude-module pygame ^
    sp500_analysis.py

echo.
echo 빌드 완료: dist\SP500Analysis.exe
pause
