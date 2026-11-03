"""
네이버 검색 결과에서 신문기사 내용을 크롤링하는 GUI 앱 (PyQt6 + requests + BeautifulSoup4)

동작 방식
1. 입력한 네이버 검색 URL(또는 검색어)에서 검색어(query)를 꺼낸다.
2. 통합검색 페이지 + 뉴스탭(where=news) 페이지에서 기사 링크를 수집한다.
   - 네이버뉴스(n.news.naver.com) 링크가 있으면 본문 파싱이 안정적이므로 우선 사용
3. 각 기사 페이지에 들어가 제목 / 언론사 / 작성일 / 본문을 추출한다.
4. 결과를 표에 보여주고, 행을 선택하면 본문을 표시한다. CSV 또는 엑셀(xlsx)로 저장할 수 있다.

크롤링은 별도 스레드(QThread)에서 실행되어 GUI가 멈추지 않는다.

설치: pip install requests beautifulsoup4 PyQt6 openpyxl
"""

import csv
import html
import os
import re
import sys
import time
from urllib.parse import parse_qs, quote, urlparse

import requests
from bs4 import BeautifulSoup
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from PyQt6.QtCore import QThread, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices, QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

SEARCH_URL = (
    "https://search.naver.com/search.naver?where=nexearch&sm=top_sug.pre&fbm=0"
    "&acr=1&acq=%EB%B0%98%EB%8F%84%EC%B2%B4&qdt=0&ie=utf8"
    "&query=%EB%B0%98%EB%8F%84%EC%B2%B4&ackey=7vxg44xe"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Referer": "https://www.naver.com/",
}

NAVER_NEWS_RE = re.compile(r"^https?://n\.news\.naver\.com/(?:mnews/)?article/\d+/\d+")

FIELDS = ["title", "press", "date", "url", "content"]

# 엑셀 저장 시 사용할 한글 헤더와 열 너비
EXCEL_COLUMNS = [("제목", 50), ("언론사", 14), ("작성일", 20), ("URL", 45), ("본문", 100)]

# ---------------------------------------------------------------- 디자인 (다크 테마 + 네온 그린 포인트)
STYLESHEET = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f1226, stop:1 #1b1f3b);
}
QWidget {
    color: #e8eaf6;
    font-family: "Malgun Gothic";
    font-size: 10pt;
}
#Banner {
    border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #03c75a, stop:0.5 #00b3a4, stop:1 #5b5bf7);
}
#BannerTitle { color: white; font-size: 22pt; font-weight: 800; background: transparent; }
#BannerSub { color: rgba(255,255,255,0.85); font-size: 10pt; background: transparent; }
#CountBadge {
    color: white; font-size: 11pt; font-weight: 700;
    background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.35);
    border-radius: 14px; padding: 6px 16px;
}
#Card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
}
#CardTitle { color: #7cf5b0; font-size: 11pt; font-weight: 700; background: transparent; }
QLabel { background: transparent; }
QLineEdit, QSpinBox {
    background: #141833; border: 2px solid #2c3260; border-radius: 10px;
    padding: 8px 12px; selection-background-color: #03c75a;
}
QLineEdit:focus, QSpinBox:focus { border: 2px solid #03c75a; }
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: transparent; }
QPushButton {
    border: none; border-radius: 10px; padding: 9px 18px;
    font-weight: 700; color: white; background: #2c3260;
}
QPushButton:hover { background: #3a4180; }
QPushButton:disabled { background: #22264a; color: #5d6390; }
#StartBtn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #03c75a, stop:1 #00b3a4);
}
#StartBtn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #1de87a, stop:1 #12d6c6);
}
#StopBtn { background: #e5484d; }
#StopBtn:hover { background: #ff6369; }
#CsvBtn { background: #5b5bf7; }
#CsvBtn:hover { background: #7878ff; }
#ExcelBtn { background: #1d8f4e; }
#ExcelBtn:hover { background: #25b062; }
QPushButton:disabled#StopBtn, QPushButton:disabled#CsvBtn,
QPushButton:disabled#ExcelBtn, QPushButton:disabled#StartBtn { background: #22264a; color: #5d6390; }
QTableWidget {
    background: transparent; border: none; gridline-color: transparent;
    alternate-background-color: rgba(255,255,255,0.03);
    selection-background-color: rgba(3,199,90,0.35); selection-color: white;
}
QTableWidget::item { padding: 6px; border-bottom: 1px solid rgba(255,255,255,0.05); }
QTableWidget::item:hover { background: rgba(91,91,247,0.18); }
QHeaderView { background: transparent; border: none; }
QTableCornerButton::section { background: transparent; border: none; }
QHeaderView::section {
    background: transparent; color: #9aa3d8; font-weight: 700;
    border: none; border-bottom: 2px solid #03c75a; padding: 8px;
}
QTextBrowser { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a4180; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #03c75a; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { height: 0; }
QSplitter::handle { background: transparent; width: 12px; }
QProgressBar {
    background: #141833; border: none; border-radius: 7px; height: 14px;
    text-align: center; color: white; font-size: 8pt; font-weight: 700;
}
QProgressBar::chunk {
    border-radius: 7px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #03c75a, stop:0.5 #00b3a4, stop:1 #5b5bf7);
}
#Status { color: #9aa3d8; }
QMessageBox { background: #1b1f3b; }
"""

# 본문 보기 HTML 템플릿
ARTICLE_HTML = """
<div style="font-family:'Malgun Gothic'; color:#e8eaf6;">
  <span style="background:#03c75a; color:white; font-weight:700; padding:2px 8px;">&nbsp;{press}&nbsp;</span>
  <span style="color:#9aa3d8;">&nbsp;&nbsp;🕒 {date}</span>
  <h2 style="color:white; margin-top:10px;">{title}</h2>
  <p><a href="{url}" style="color:#7cf5b0;">🔗 원문 보기</a></p>
  <hr style="border:0; height:1px; background:#2c3260;">
  {paragraphs}
</div>
"""


def resource_path(relative: str) -> str:
    """PyInstaller로 빌드한 exe 안에서도 리소스 파일 경로를 찾을 수 있게 변환"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative)


def add_shadow(widget: QWidget, color: str = "#000000", blur: int = 30):
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, 6)
    shadow.setColor(QColor(color))
    widget.setGraphicsEffect(shadow)


def make_card(title: str, body: QWidget) -> QFrame:
    """제목이 있는 둥근 카드 패널"""
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(16, 14, 16, 14)
    label = QLabel(title)
    label.setObjectName("CardTitle")
    layout.addWidget(label)
    layout.addWidget(body, 1)
    add_shadow(card)
    return card


# ---------------------------------------------------------------- 크롤링 로직
def get_soup(url: str) -> BeautifulSoup:
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")


def to_search_url(text: str) -> str:
    """URL이 아니라 검색어를 입력한 경우 통합검색 URL로 변환"""
    text = text.strip()
    if text.startswith("http"):
        return text
    return f"https://search.naver.com/search.naver?where=nexearch&ie=utf8&query={quote(text)}"


def collect_article_links(search_url: str, max_count: int = 10) -> list[str]:
    """검색 결과 페이지에서 네이버뉴스 기사 링크를 수집"""
    query = parse_qs(urlparse(search_url).query).get("query", [""])[0]
    news_tab_url = f"https://search.naver.com/search.naver?where=news&ie=utf8&query={quote(query)}"

    links: list[str] = []
    for url in (search_url, news_tab_url):
        soup = get_soup(url)
        for a in soup.select("a[href]"):
            href = a["href"].split("?")[0]
            if NAVER_NEWS_RE.match(href) and href not in links:
                links.append(href)
        if len(links) >= max_count:
            break
    return links[:max_count]


def parse_article(url: str) -> dict:
    """네이버뉴스 기사 페이지에서 제목/언론사/날짜/본문 추출"""
    soup = get_soup(url)

    title = soup.select_one("#title_area span, h2.media_end_head_headline")
    press = soup.select_one("a.media_end_head_top_logo img")
    date = soup.select_one("span.media_end_head_info_datestamp_time")
    body = soup.select_one("#dic_area, #newsct_article")

    if body:
        # 사진 설명, 스크립트 등 본문이 아닌 요소 제거
        for tag in body.select("script, style, em.img_desc, span.end_photo_org, div.ab_photo"):
            tag.decompose()
        content = re.sub(r"\n\s*\n+", "\n", body.get_text("\n", strip=True))
    else:
        content = ""

    return {
        "title": title.get_text(strip=True) if title else "",
        "press": press.get("title") or press.get("alt", "") if press else "",
        "date": date.get("data-date-time", date.get_text(strip=True)) if date else "",
        "url": url,
        "content": content,
    }


def write_excel(path: str, articles: list[dict]):
    """기사 목록을 엑셀(xlsx) 파일로 저장"""
    wb = Workbook()
    ws = wb.active
    ws.title = "뉴스"

    # 헤더: 굵게 + 배경색, 열 너비 지정
    ws.append([name for name, _ in EXCEL_COLUMNS])
    for col, (_, width) in enumerate(EXCEL_COLUMNS, 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="03C75A")
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"

    for a in articles:
        # 엑셀 셀 최대 글자 수(32,767자) 제한
        ws.append([a[key][:32767] for key in FIELDS])
        row = ws.max_row
        url_cell = ws.cell(row=row, column=4)
        url_cell.hyperlink = a["url"]
        url_cell.font = Font(color="0563C1", underline="single")
        for col in range(1, len(FIELDS) + 1):
            ws.cell(row=row, column=col).alignment = Alignment(vertical="top", wrap_text=(col == 5))

    ws.auto_filter.ref = ws.dimensions
    wb.save(path)


# ---------------------------------------------------------------- 작업 스레드
class CrawlWorker(QThread):
    status = pyqtSignal(str)
    total = pyqtSignal(int)
    article = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, search_url: str, max_count: int):
        super().__init__()
        self.search_url = search_url
        self.max_count = max_count

    def run(self):
        try:
            self.status.emit("기사 링크 수집 중...")
            links = collect_article_links(self.search_url, self.max_count)
        except requests.RequestException as e:
            self.failed.emit(f"검색 페이지 요청 실패: {e}")
            return

        self.total.emit(len(links))
        for i, link in enumerate(links, 1):
            if self.isInterruptionRequested():
                self.status.emit("중지됨")
                return
            self.status.emit(f"[{i}/{len(links)}] {link}")
            try:
                self.article.emit(parse_article(link))
            except requests.RequestException as e:
                self.status.emit(f"요청 실패: {link} ({e})")
            time.sleep(0.5)  # 서버 부담을 줄이기 위한 딜레이
        self.status.emit(f"완료: {len(links)}개 링크 처리")


# ---------------------------------------------------------------- 메인 윈도우
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("네이버 뉴스 크롤러")
        self.resize(1280, 800)
        self.setStyleSheet(STYLESHEET)
        self.articles: list[dict] = []
        self.worker: CrawlWorker | None = None

        # 상단 배너 (그라데이션 + 수집 건수 배지)
        banner = QFrame()
        banner.setObjectName("Banner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(26, 18, 26, 18)
        title_box = QVBoxLayout()
        banner_title = QLabel("📰  NAVER NEWS CRAWLER")
        banner_title.setObjectName("BannerTitle")
        banner_sub = QLabel("네이버 검색 결과에서 뉴스 기사를 수집하고 CSV · 엑셀로 저장합니다")
        banner_sub.setObjectName("BannerSub")
        title_box.addWidget(banner_title)
        title_box.addWidget(banner_sub)
        self.count_badge = QLabel("수집 0건")
        self.count_badge.setObjectName("CountBadge")
        banner_layout.addLayout(title_box, 1)
        banner_layout.addWidget(self.count_badge)
        add_shadow(banner, "#03c75a", 40)

        # 입력부
        self.url_edit = QLineEdit(SEARCH_URL)
        self.url_edit.setPlaceholderText("🔍  네이버 검색 URL 또는 검색어를 입력하세요")
        self.url_edit.returnPressed.connect(self.start_crawl)

        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(10)
        self.count_spin.setSuffix(" 건")
        self.count_spin.setMinimumWidth(90)

        self.start_btn = QPushButton("🚀  크롤링 시작")
        self.start_btn.setObjectName("StartBtn")
        self.start_btn.clicked.connect(self.start_crawl)
        self.stop_btn = QPushButton("■  중지")
        self.stop_btn.setObjectName("StopBtn")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_crawl)
        self.save_btn = QPushButton("📄  CSV 저장")
        self.save_btn.setObjectName("CsvBtn")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.save_csv)
        self.excel_btn = QPushButton("📊  엑셀 저장")
        self.excel_btn.setObjectName("ExcelBtn")
        self.excel_btn.setEnabled(False)
        self.excel_btn.clicked.connect(self.save_excel)
        for btn in (self.start_btn, self.stop_btn, self.save_btn, self.excel_btn):
            btn.setCursor(Qt.CursorShape.PointingHandCursor)

        input_row = QWidget()
        top = QHBoxLayout(input_row)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(10)
        top.addWidget(self.url_edit, 1)
        top.addWidget(self.count_spin)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.excel_btn)

        # 기사 목록 표
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["제목", "언론사", "작성일"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.itemSelectionChanged.connect(self.show_article)
        self.table.cellDoubleClicked.connect(self.open_in_browser)

        # 본문 보기
        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        self.viewer.setPlaceholderText("기사를 선택하면 본문이 표시됩니다. (더블클릭: 브라우저로 열기)")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(make_card("📋  기사 목록", self.table))
        splitter.addWidget(make_card("📖  기사 본문", self.viewer))
        splitter.setSizes([620, 620])

        # 하단 진행 상태
        self.progress = QProgressBar()
        self.progress.setFixedHeight(14)
        self.status_label = QLabel("⚪  대기 중")
        self.status_label.setObjectName("Status")

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(14)
        layout.addWidget(banner)
        layout.addWidget(make_card("⚙️  검색 설정", input_row))
        layout.addWidget(splitter, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    # ---- 크롤링 제어
    def start_crawl(self):
        text = self.url_edit.text().strip()
        if not text or (self.worker and self.worker.isRunning()):
            return

        self.articles.clear()
        self.table.setRowCount(0)
        self.viewer.clear()
        self.progress.setValue(0)
        self.progress.setMaximum(0)  # 링크 수집 중에는 무한 진행 표시
        self.set_running(True)

        self.worker = CrawlWorker(to_search_url(text), self.count_spin.value())
        self.worker.status.connect(self.status_label.setText)
        self.worker.total.connect(self.progress.setMaximum)
        self.worker.article.connect(self.add_article)
        self.worker.failed.connect(self.on_failed)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def stop_crawl(self):
        if self.worker:
            self.worker.requestInterruption()
            self.stop_btn.setEnabled(False)

    def set_running(self, running: bool):
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.save_btn.setEnabled(not running and bool(self.articles))
        self.excel_btn.setEnabled(not running and bool(self.articles))

    def add_article(self, article: dict):
        self.articles.append(article)
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col, key in enumerate(["title", "press", "date"]):
            item = QTableWidgetItem(article[key])
            item.setToolTip(article["title"])
            if col == 1:
                item.setForeground(QColor("#7cf5b0"))
            elif col == 2:
                item.setForeground(QColor("#9aa3d8"))
            self.table.setItem(row, col, item)
        self.progress.setValue(len(self.articles))
        self.count_badge.setText(f"수집 {len(self.articles)}건")

    def on_failed(self, message: str):
        QMessageBox.warning(self, "오류", message)

    def on_finished(self):
        if self.progress.maximum() == 0:
            self.progress.setMaximum(1)
        self.set_running(False)

    # ---- 기사 보기
    def show_article(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        a = self.articles[rows[0].row()]
        paragraphs = "".join(
            f'<p style="line-height:160%; margin:8px 0;">{html.escape(line)}</p>'
            for line in a["content"].splitlines()
        )
        self.viewer.setHtml(
            ARTICLE_HTML.format(
                press=html.escape(a["press"] or "언론사"),
                date=html.escape(a["date"]),
                title=html.escape(a["title"]),
                url=html.escape(a["url"]),
                paragraphs=paragraphs,
            )
        )

    def open_in_browser(self, row: int, _col: int):
        QDesktopServices.openUrl(QUrl(self.articles[row]["url"]))

    # ---- 저장
    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "naver_news.csv", "CSV 파일 (*.csv)")
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.articles)
        self.status_label.setText(f"저장 완료: {path} ({len(self.articles)}건)")

    def save_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "엑셀 저장", "naver_news.xlsx", "엑셀 파일 (*.xlsx)")
        if not path:
            return
        try:
            write_excel(path, self.articles)
        except PermissionError:
            QMessageBox.warning(self, "오류", "파일이 다른 프로그램(엑셀 등)에서 열려 있어 저장할 수 없습니다.")
            return
        self.status_label.setText(f"저장 완료: {path} ({len(self.articles)}건)")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setWindowIcon(QIcon(resource_path("assets/app.ico")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
