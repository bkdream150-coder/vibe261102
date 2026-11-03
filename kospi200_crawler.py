"""
네이버 증권(stock.naver.com)에서 코스피200 지수 시세와 구성종목을 크롤링하는 GUI 앱 (PyQt6 + requests)

stock.naver.com/market/stock/kr 은 Next.js로 만든 페이지라서, 서버가 내려주는 HTML에는
시세 데이터가 없고 브라우저의 자바스크립트가 아래 JSON API를 호출해 화면을 채운다.
그래서 HTML을 BeautifulSoup으로 파싱해도 코스피200 숫자는 나오지 않으며,
페이지가 실제로 사용하는 API를 requests로 직접 호출하는 방식을 쓴다.

수집 항목
1. 지수 현재가   : polling.finance.naver.com/api/realtime/domestic/index/KPI200
2. 일별 시세      : m.stock.naver.com/api/index/KPI200/price
3. 구성종목(200개): m.stock.naver.com/api/index/KPI200/enrollStocks (50개씩 페이징)

크롤링은 별도 스레드(QThread)에서 실행되어 GUI가 멈추지 않는다.
구성종목 표의 행을 더블클릭하면 네이버 증권 종목 페이지가 브라우저로 열린다.

설치: pip install requests PyQt6 openpyxl
"""

import csv
import math
import os
import sys
import time

import requests
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
    QGridLayout,
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
    QVBoxLayout,
    QWidget,
)

INDEX_CODE = "KPI200"
REALTIME_URL = f"https://polling.finance.naver.com/api/realtime/domestic/index/{INDEX_CODE}"
DAILY_URL = f"https://m.stock.naver.com/api/index/{INDEX_CODE}/price"
STOCKS_URL = f"https://m.stock.naver.com/api/index/{INDEX_CODE}/enrollStocks"
STOCK_PAGE_URL = "https://stock.naver.com/domestic/stock/{code}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Referer": "https://stock.naver.com/market/stock/kr",
}

PAGE_SIZE = 50  # enrollStocks API는 100 이상을 주면 400 에러가 난다
MAX_STOCKS = 200  # API가 지수 변경 시기에 201개를 줄 때가 있어 시가총액 상위 200개만 남긴다
STOCK_PAGES = math.ceil(MAX_STOCKS / PAGE_SIZE)

# 표/CSV/엑셀 공통 열 정의: (키, 열 너비)
STOCK_COLUMNS = [
    ("순위", 6), ("종목코드", 10), ("종목명", 18), ("현재가", 12), ("전일대비", 11),
    ("등락률(%)", 10), ("거래량", 14), ("거래대금(원)", 20), ("시가총액(원)", 22),
]
DAILY_COLUMNS = [
    ("날짜", 12), ("종가", 11), ("전일대비", 10), ("등락률(%)", 10),
    ("시가", 11), ("고가", 11), ("저가", 11),
]
# 화면 표에 보여줄 구성종목 열 (금액이 큰 열은 억 원 단위로 변환해서 표시)
STOCK_TABLE_HEADERS = ["순위", "종목코드", "종목명", "현재가", "전일대비", "등락률", "거래량", "거래대금(억)", "시가총액(억)"]

# 상승은 빨강, 하락은 파랑 (국내 증시 관례)
UP_COLOR = "#ff5c6c"
DOWN_COLOR = "#4f9dff"
FLAT_COLOR = "#e8eaf6"

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
#IndexPrice { font-size: 26pt; font-weight: 800; }
#IndexChange { font-size: 13pt; font-weight: 700; }
#StatName { color: #9aa3d8; }
#StatValue { font-weight: 700; }
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


def change_color(value: float) -> str:
    if value > 0:
        return UP_COLOR
    if value < 0:
        return DOWN_COLOR
    return FLAT_COLOR


def to_number(text: str) -> float:
    """'1,234.56' 같은 API 문자열을 숫자로 변환"""
    return float(text.replace(",", ""))


# ---------------------------------------------------------------- 크롤링 로직
def get_json(url, params=None):
    res = requests.get(url, headers=HEADERS, params=params, timeout=10)
    res.raise_for_status()
    return res.json()


def fetch_index_now() -> dict:
    """코스피200 지수 현재가"""
    d = get_json(REALTIME_URL)["datas"][0]
    return {
        "지수명": d["stockName"],
        "현재가": d["closePrice"],
        "전일대비": d["compareToPreviousClosePrice"],
        "등락률(%)": d["fluctuationsRatio"],
        "시가": d["openPrice"],
        "고가": d["highPrice"],
        "저가": d["lowPrice"],
        "거래량": d["accumulatedTradingVolume"],
        "거래대금": d["accumulatedTradingValue"],
        "장상태": d["marketStatus"],
        "기준시각": d["localTradedAt"],
    }


def fetch_index_daily(days: int) -> list[dict]:
    """코스피200 일별 시세 (최근 days일)"""
    rows = get_json(DAILY_URL, {"page": 1, "pageSize": days})
    return [
        {
            "날짜": r["localTradedAt"],
            "종가": to_number(r["closePrice"]),
            "전일대비": to_number(r["compareToPreviousClosePrice"]),
            "등락률(%)": to_number(r["fluctuationsRatio"]),
            "시가": to_number(r["openPrice"]),
            "고가": to_number(r["highPrice"]),
            "저가": to_number(r["lowPrice"]),
        }
        for r in rows
    ]


def fetch_stock_page(page: int) -> list[dict]:
    """구성종목 한 페이지 (시가총액 순, PAGE_SIZE개)"""
    rows = get_json(STOCKS_URL, {"page": page, "pageSize": PAGE_SIZE})
    return [
        {
            "종목코드": r["itemCode"],
            "종목명": r["stockName"],
            "현재가": int(r["closePriceRaw"]),
            "전일대비": int(r["compareToPreviousClosePriceRaw"]),
            "등락률(%)": float(r["fluctuationsRatio"]),
            "거래량": int(r["accumulatedTradingVolumeRaw"]),
            "거래대금(원)": int(r["accumulatedTradingValueRaw"]),
            "시가총액(원)": int(r["marketValueRaw"]),
        }
        for r in rows
    ]


def write_csv(path: str, columns: list, rows: list[dict]):
    # utf-8-sig: 엑셀에서 열어도 한글이 깨지지 않도록 BOM 포함
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[key for key, _ in columns])
        writer.writeheader()
        writer.writerows(rows)


def write_sheet(ws, columns: list, rows: list[dict]):
    ws.append([key for key, _ in columns])
    for col, (_, width) in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="03C75A")
        cell.alignment = Alignment(horizontal="center")
        ws.column_dimensions[cell.column_letter].width = width
    ws.freeze_panes = "A2"
    for r in rows:
        ws.append([r[key] for key, _ in columns])
    # 숫자 열에 천 단위 구분 기호 적용
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if isinstance(cell.value, int):
                cell.number_format = "#,##0"
            elif isinstance(cell.value, float):
                cell.number_format = "#,##0.00"
    ws.auto_filter.ref = ws.dimensions


def write_excel(path: str, stocks: list[dict], daily: list[dict]):
    """구성종목 / 일별 시세를 시트 두 개로 엑셀(xlsx) 파일에 저장"""
    wb = Workbook()
    write_sheet(wb.active, STOCK_COLUMNS, stocks)
    wb.active.title = "구성종목"
    write_sheet(wb.create_sheet("일별시세"), DAILY_COLUMNS, daily)
    wb.save(path)


# ---------------------------------------------------------------- 작업 스레드
class CrawlWorker(QThread):
    status = pyqtSignal(str)
    step = pyqtSignal(int)
    index_now = pyqtSignal(dict)
    daily = pyqtSignal(list)
    stocks = pyqtSignal(list)
    failed = pyqtSignal(str)

    TOTAL_STEPS = 2 + STOCK_PAGES  # 현재가 + 일별 시세 + 구성종목 페이지 수

    def __init__(self, days: int):
        super().__init__()
        self.days = days

    def run(self):
        try:
            self.status.emit("지수 현재가 조회 중...")
            self.index_now.emit(fetch_index_now())
            self.step.emit(1)

            self.status.emit(f"일별 시세 {self.days}일 조회 중...")
            self.daily.emit(fetch_index_daily(self.days))
            self.step.emit(2)

            count = 0
            seen = set()  # 페이지 경계에서 순위가 바뀌어 같은 종목이 두 번 나오는 경우 방지
            for page in range(1, STOCK_PAGES + 1):
                if self.isInterruptionRequested():
                    self.status.emit("중지됨")
                    return
                self.status.emit(f"구성종목 {page}/{STOCK_PAGES}페이지 조회 중...")
                rows = [r for r in fetch_stock_page(page) if r["종목코드"] not in seen]
                rows = rows[: MAX_STOCKS - count]
                for r in rows:
                    seen.add(r["종목코드"])
                    count += 1
                    r["순위"] = count
                self.stocks.emit(rows)
                self.step.emit(2 + page)
                if len(rows) < PAGE_SIZE or count >= MAX_STOCKS:
                    break
                time.sleep(0.3)  # 서버 부담을 줄이기 위해 요청 사이 간격
        except requests.RequestException as e:
            self.failed.emit(f"요청 실패: {e}")
            return
        self.step.emit(self.TOTAL_STEPS)
        self.status.emit(f"완료: 구성종목 {count}개 수집 ({time.strftime('%H:%M:%S')})")


# ---------------------------------------------------------------- 메인 윈도우
class NumberItem(QTableWidgetItem):
    """표시 문자열과 별개로 숫자 값으로 정렬되는 셀"""

    def __init__(self, value: float, text: str, color: str | None = None):
        super().__init__(text)
        self.value = value
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if color:
            self.setForeground(QColor(color))

    def __lt__(self, other):
        if isinstance(other, NumberItem):
            return self.value < other.value
        return super().__lt__(other)


def make_table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(36)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    return table


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("코스피200 크롤러")
        self.resize(1360, 860)
        self.setStyleSheet(STYLESHEET)
        self.stocks: list[dict] = []
        self.daily_rows: list[dict] = []
        self.worker: CrawlWorker | None = None

        # 상단 배너 (그라데이션 + 수집 건수 배지)
        banner = QFrame()
        banner.setObjectName("Banner")
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(26, 18, 26, 18)
        title_box = QVBoxLayout()
        banner_title = QLabel("📈  KOSPI 200 CRAWLER")
        banner_title.setObjectName("BannerTitle")
        banner_sub = QLabel("네이버 증권에서 코스피200 지수 시세와 구성종목 200개를 수집하고 CSV · 엑셀로 저장합니다")
        banner_sub.setObjectName("BannerSub")
        title_box.addWidget(banner_title)
        title_box.addWidget(banner_sub)
        self.count_badge = QLabel("구성종목 0개")
        self.count_badge.setObjectName("CountBadge")
        banner_layout.addLayout(title_box, 1)
        banner_layout.addWidget(self.count_badge)
        add_shadow(banner, "#03c75a", 40)

        # 설정 / 버튼
        self.days_spin = QSpinBox()
        self.days_spin.setRange(1, 60)
        self.days_spin.setValue(20)
        self.days_spin.setPrefix("일별 시세 ")
        self.days_spin.setSuffix(" 일")
        self.days_spin.setMinimumWidth(150)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("🔍  종목명 또는 종목코드로 표 필터링")
        self.filter_edit.textChanged.connect(self.apply_filter)

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
        top.addWidget(self.filter_edit, 1)
        top.addWidget(self.days_spin)
        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        top.addWidget(self.save_btn)
        top.addWidget(self.excel_btn)

        # 지수 현재가 패널
        index_panel = QWidget()
        grid = QGridLayout(index_panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(28)
        self.price_label = QLabel("-")
        self.price_label.setObjectName("IndexPrice")
        self.change_label = QLabel("")
        self.change_label.setObjectName("IndexChange")
        grid.addWidget(self.price_label, 0, 0, 2, 1)
        grid.addWidget(self.change_label, 0, 1, 2, 1)
        self.stat_labels: dict[str, QLabel] = {}
        stat_keys = ["시가", "고가", "저가", "거래량", "거래대금", "장상태", "기준시각"]
        for i, key in enumerate(stat_keys):
            name = QLabel(key)
            name.setObjectName("StatName")
            value = QLabel("-")
            value.setObjectName("StatValue")
            grid.addWidget(name, 0, 2 + i)
            grid.addWidget(value, 1, 2 + i)
            self.stat_labels[key] = value
        grid.setColumnStretch(2 + len(stat_keys), 1)

        # 구성종목 / 일별 시세 표
        self.stock_table = make_table(STOCK_TABLE_HEADERS)
        self.stock_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.stock_table.setToolTip("더블클릭: 네이버 증권 종목 페이지 열기 / 열 제목 클릭: 정렬")
        self.stock_table.cellDoubleClicked.connect(self.open_stock_page)
        self.daily_table = make_table(["날짜", "종가", "전일대비", "등락률"])
        self.daily_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(make_card("📋  구성종목 (시가총액 순)", self.stock_table))
        splitter.addWidget(make_card("📅  지수 일별 시세", self.daily_table))
        splitter.setSizes([940, 400])

        # 하단 진행 상태
        self.progress = QProgressBar()
        self.progress.setFixedHeight(14)
        self.progress.setMaximum(CrawlWorker.TOTAL_STEPS)
        self.progress.setValue(0)
        self.status_label = QLabel("⚪  대기 중")
        self.status_label.setObjectName("Status")

        layout = QVBoxLayout()
        layout.setContentsMargins(20, 20, 20, 14)
        layout.setSpacing(14)
        layout.addWidget(banner)
        layout.addWidget(make_card("⚙️  수집 설정", input_row))
        layout.addWidget(make_card("💹  코스피200 지수", index_panel))
        layout.addWidget(splitter, 1)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

        central = QWidget()
        central.setLayout(layout)
        self.setCentralWidget(central)

    # ---- 크롤링 제어
    def start_crawl(self):
        if self.worker and self.worker.isRunning():
            return

        self.stocks.clear()
        self.daily_rows.clear()
        self.stock_table.setSortingEnabled(False)
        self.stock_table.setRowCount(0)
        self.daily_table.setRowCount(0)
        self.progress.setValue(0)
        self.count_badge.setText("구성종목 0개")
        self.set_running(True)

        self.worker = CrawlWorker(self.days_spin.value())
        self.worker.status.connect(self.status_label.setText)
        self.worker.step.connect(self.progress.setValue)
        self.worker.index_now.connect(self.show_index)
        self.worker.daily.connect(self.show_daily)
        self.worker.stocks.connect(self.add_stocks)
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
        self.days_spin.setEnabled(not running)
        self.save_btn.setEnabled(not running and bool(self.stocks))
        self.excel_btn.setEnabled(not running and bool(self.stocks))

    def on_failed(self, message: str):
        self.status_label.setText(f"🔴  {message}")
        QMessageBox.warning(self, "오류", message)

    def on_finished(self):
        self.stock_table.setSortingEnabled(True)
        self.set_running(False)

    # ---- 화면 표시
    def show_index(self, d: dict):
        change = to_number(d["전일대비"])
        color = change_color(change)
        arrow = "▲" if change > 0 else "▼" if change < 0 else "-"
        self.price_label.setText(d["현재가"])
        self.price_label.setStyleSheet(f"color: {color};")
        self.change_label.setText(f"{arrow} {abs(change):,.2f}\n{d['등락률(%)']}%")
        self.change_label.setStyleSheet(f"color: {color};")
        for key, label in self.stat_labels.items():
            label.setText(d[key])

    def show_daily(self, rows: list[dict]):
        self.daily_rows = rows
        self.daily_table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            color = change_color(r["전일대비"])
            self.daily_table.setItem(i, 0, QTableWidgetItem(r["날짜"]))
            self.daily_table.setItem(i, 1, NumberItem(r["종가"], f"{r['종가']:,.2f}"))
            self.daily_table.setItem(i, 2, NumberItem(r["전일대비"], f"{r['전일대비']:+,.2f}", color))
            self.daily_table.setItem(i, 3, NumberItem(r["등락률(%)"], f"{r['등락률(%)']:+.2f}%", color))

    def add_stocks(self, rows: list[dict]):
        for s in rows:
            self.stocks.append(s)
            row = self.stock_table.rowCount()
            self.stock_table.insertRow(row)
            color = change_color(s["전일대비"])
            items = [
                NumberItem(s["순위"], str(s["순위"])),
                QTableWidgetItem(s["종목코드"]),
                QTableWidgetItem(s["종목명"]),
                NumberItem(s["현재가"], f"{s['현재가']:,}"),
                NumberItem(s["전일대비"], f"{s['전일대비']:+,}", color),
                NumberItem(s["등락률(%)"], f"{s['등락률(%)']:+.2f}%", color),
                NumberItem(s["거래량"], f"{s['거래량']:,}"),
                NumberItem(s["거래대금(원)"], f"{s['거래대금(원)'] / 1e8:,.0f}"),
                NumberItem(s["시가총액(원)"], f"{s['시가총액(원)'] / 1e8:,.0f}"),
            ]
            for col, item in enumerate(items):
                self.stock_table.setItem(row, col, item)
        self.count_badge.setText(f"구성종목 {len(self.stocks)}개")
        self.apply_filter(self.filter_edit.text())

    def apply_filter(self, text: str):
        text = text.strip().lower()
        for row in range(self.stock_table.rowCount()):
            code = self.stock_table.item(row, 1).text()
            name = self.stock_table.item(row, 2).text().lower()
            self.stock_table.setRowHidden(row, bool(text) and text not in name and text not in code)

    def open_stock_page(self, row: int, _col: int):
        code = self.stock_table.item(row, 1).text()
        QDesktopServices.openUrl(QUrl(STOCK_PAGE_URL.format(code=code)))

    # ---- 저장
    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", "kospi200_stocks.csv", "CSV 파일 (*.csv)")
        if not path:
            return
        try:
            write_csv(path, STOCK_COLUMNS, self.stocks)
            # 일별 시세는 같은 폴더에 _daily를 붙여 함께 저장
            daily_path = os.path.splitext(path)[0] + "_daily.csv"
            write_csv(daily_path, DAILY_COLUMNS, self.daily_rows)
        except PermissionError:
            QMessageBox.warning(self, "오류", "파일이 다른 프로그램(엑셀 등)에서 열려 있어 저장할 수 없습니다.")
            return
        self.status_label.setText(f"저장 완료: {path}, {daily_path}")

    def save_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "엑셀 저장", "kospi200.xlsx", "엑셀 파일 (*.xlsx)")
        if not path:
            return
        try:
            write_excel(path, self.stocks, self.daily_rows)
        except PermissionError:
            QMessageBox.warning(self, "오류", "파일이 다른 프로그램(엑셀 등)에서 열려 있어 저장할 수 없습니다.")
            return
        self.status_label.setText(f"저장 완료: {path} (구성종목 {len(self.stocks)}개 + 일별 시세 {len(self.daily_rows)}일)")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(3000)
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setFont(QFont("Malgun Gothic", 10))
    app.setWindowIcon(QIcon(resource_path("assets/kospi200.ico")))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
