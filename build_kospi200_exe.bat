@echo off
chcp 65001 > nul
REM 코스피200 크롤러 실행파일(exe) 빌드 스크립트
REM 결과물: dist\Kospi200Crawler.exe

pip install pyinstaller requests PyQt6 openpyxl

pyinstaller --noconfirm --clean --onefile --windowed ^
    --name Kospi200Crawler ^
    --icon assets\kospi200.ico ^
    --add-data "assets\kospi200.ico;assets" ^
    --exclude-module PySide6 ^
    --exclude-module shiboken6 ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    --exclude-module bs4 ^
    kospi200_crawler.py

echo.
echo 빌드 완료: dist\Kospi200Crawler.exe
pause
