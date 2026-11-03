@echo off
chcp 65001 > nul
REM 네이버 뉴스 크롤러 실행파일(exe) 빌드 스크립트
REM 결과물: dist\NaverNewsCrawler.exe

pip install pyinstaller requests beautifulsoup4 PyQt6 openpyxl

pyinstaller --noconfirm --clean --onefile --windowed ^
    --name NaverNewsCrawler ^
    --icon assets\app.ico ^
    --add-data "assets\app.ico;assets" ^
    --exclude-module PySide6 ^
    --exclude-module shiboken6 ^
    --exclude-module tkinter ^
    --exclude-module matplotlib ^
    --exclude-module numpy ^
    --exclude-module pandas ^
    naver_news_crawler.py

echo.
echo 빌드 완료: dist\NaverNewsCrawler.exe
pause
