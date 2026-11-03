"""
대한민국 출생아수·합계출산율 분석 결과를 보여주는 GUI 앱 (PyQt6 + matplotlib)

- 엑셀(KOSIS 「인구동향조사」)을 불러와 birth_analysis.py의 클렌징·분석을 그대로 실행
- 요약 카드, 차트 5종(출생아수 라인 그래프 1970~2025 포함), 정제 데이터 표, 분석 리포트를 탭으로 표시
- 연도 범위를 바꾸면 모든 차트에 바로 반영

설치: pip install pandas openpyxl matplotlib PyQt6
실행: python birth_gui.py [엑셀파일경로]
"""
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from birth_analysis import COLUMN_MAP, DEFAULT_PATH, analyze, load_and_clean

# 차트 색상 (다크 테마)
BG = "#161a33"
FG = "#e8eaf6"
SUB = "#9aa3d8"
GRID = "#2c3260"
BLUE = "#4f9dff"
RED = "#ff5c6c"
GREEN = "#7cf5b0"
PURPLE = "#b392f0"

# 정제 데이터 표에 보여줄 열
TABLE_COLUMNS = [
    ("births", "출생아수(명)", "{:,.0f}"),
    ("deaths", "사망자수(명, 추정)", "{:,.0f}"),
    ("natural_increase", "자연증가(명)", "{:,.0f}"),
    ("births_yoy_pct", "전년대비(%)", "{:+.2f}"),
    ("crude_birth_rate", "조출생률(천명당)", "{:.1f}"),
    ("tfr", "합계출산율(명)", "{:.3f}"),
    ("sex_ratio", "출생성비", "{:.1f}"),
    ("est_population", "추정 총인구(명)", "{:,.0f}"),
]

# ---------------------------------------------------------------- 디자인 (다크 테마)
STYLESHEET = """
QMainWindow {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #0f1226, stop:1 #1b1f3b);
}
QWidget { color: #e8eaf6; font-family: "Malgun Gothic"; font-size: 10pt; }
QLabel { background: transparent; }
#Banner {
    border-radius: 16px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #ff7a90, stop:0.5 #b392f0, stop:1 #4f9dff);
}
#BannerTitle { color: white; font-size: 20pt; font-weight: 800; }
#BannerSub { color: rgba(255,255,255,0.88); font-size: 10pt; }
#Card {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
}
#KpiName { color: #9aa3d8; font-size: 9pt; }
#KpiValue { font-size: 17pt; font-weight: 800; }
#KpiSub { color: #9aa3d8; font-size: 9pt; }
QSpinBox {
    background: rgba(0,0,0,0.25); border: 1px solid rgba(255,255,255,0.35);
    border-radius: 8px; padding: 5px 8px; color: white; font-weight: 700;
}
QSpinBox::up-button, QSpinBox::down-button { width: 16px; border: none; background: transparent; }
QPushButton {
    border: none; border-radius: 10px; padding: 8px 16px;
    font-weight: 700; color: white; background: rgba(0,0,0,0.28);
}
QPushButton:hover { background: rgba(0,0,0,0.45); }
QTabWidget::pane { border: none; }
QTabBar::tab {
    background: transparent; color: #9aa3d8; padding: 9px 18px; font-weight: 700;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected { color: white; border-bottom: 2px solid #ff7a90; }
QTabBar::tab:hover { color: white; }
QTableWidget {
    background: transparent; border: none; gridline-color: transparent;
    alternate-background-color: rgba(255,255,255,0.03);
    selection-background-color: rgba(179,146,240,0.35); selection-color: white;
}
QTableWidget::item { padding: 4px; border-bottom: 1px solid rgba(255,255,255,0.05); }
QHeaderView { background: transparent; border: none; }
QTableCornerButton::section { background: transparent; border: none; }
QHeaderView::section {
    background: transparent; color: #9aa3d8; font-weight: 700;
    border: none; border-bottom: 2px solid #b392f0; padding: 6px;
}
QPlainTextEdit {
    background: rgba(0,0,0,0.25); border: none; border-radius: 10px; padding: 10px;
    font-family: "D2Coding", "Consolas", "Malgun Gothic"; font-size: 10pt;
}
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a4180; border-radius: 5px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #3a4180; border-radius: 5px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
"""


def man(v: float, _=None) -> str:
    """축 눈금을 '만' 단위로 표시"""
    return f"{v / 10000:,.0f}만"


class ChartTab(QWidget):
    """matplotlib Figure + 확대/이동/저장 툴바"""

    def __init__(self) -> None:
        super().__init__()
        self.figure = Figure(facecolor=BG, layout="tight")
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setStyleSheet(f"background: {BG}; border-radius: 12px;")
        toolbar = NavigationToolbar2QT(self.canvas, self)
        toolbar.setStyleSheet("background: rgba(255,255,255,0.06); border-radius: 8px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.addWidget(toolbar)
        layout.addWidget(self.canvas, 1)

    def new_axes(self):
        self.figure.clear()
        ax = self.figure.add_subplot(111, facecolor=BG)
        ax.tick_params(colors=SUB)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        ax.grid(color=GRID, alpha=0.6)
        ax.title.set_color(FG)
        ax.xaxis.label.set_color(SUB)
        ax.yaxis.label.set_color(SUB)
        return ax

    def legend(self, ax) -> None:
        leg = ax.legend(facecolor=BG, edgecolor=GRID)
        for text in leg.get_texts():
            text.set_color(FG)


class MainWindow(QMainWindow):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.setWindowTitle("대한민국 출생아수 분석")
        self.resize(1360, 900)
        self.setStyleSheet(STYLESHEET)
        self.df: pd.DataFrame | None = None

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)
        self.setCentralWidget(central)

        root.addWidget(self.build_banner())

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(12)
        self.kpi_labels: list[tuple[QLabel, QLabel, QLabel]] = []
        for i in range(5):
            card = QFrame(objectName="Card")
            box = QVBoxLayout(card)
            box.setContentsMargins(16, 12, 16, 12)
            name, value, sub = QLabel(objectName="KpiName"), QLabel(objectName="KpiValue"), QLabel(objectName="KpiSub")
            for w in (name, value, sub):
                box.addWidget(w)
            self.kpi_grid.addWidget(card, 0, i)
            self.kpi_labels.append((name, value, sub))
        root.addLayout(self.kpi_grid)

        self.tabs = QTabWidget()
        self.births_tab = ChartTab()
        self.deaths_tab = ChartTab()
        self.tfr_tab = ChartTab()
        self.yoy_tab = ChartTab()
        self.ratio_tab = ChartTab()
        self.table = self.build_table()
        self.report = QPlainTextEdit(readOnly=True)
        self.tabs.addTab(self.births_tab, "출생아수 추이")
        self.tabs.addTab(self.deaths_tab, "출생 vs 사망")
        self.tabs.addTab(self.tfr_tab, "합계출산율")
        self.tabs.addTab(self.yoy_tab, "전년 대비 증감")
        self.tabs.addTab(self.ratio_tab, "출생성비")
        self.tabs.addTab(self.table, "정제 데이터")
        self.tabs.addTab(self.report, "분석 리포트")
        root.addWidget(self.tabs, 1)

        self.births_tab.canvas.mpl_connect("motion_notify_event", self.on_hover)
        self.load(path)

    # ---------------------------------------------------------------- 화면 구성
    def build_banner(self) -> QFrame:
        banner = QFrame(objectName="Banner")
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(24, 16, 24, 16)

        titles = QVBoxLayout()
        titles.addWidget(QLabel("대한민국 출생아수 분석", objectName="BannerTitle"))
        self.sub_label = QLabel("", objectName="BannerSub")
        titles.addWidget(self.sub_label)
        layout.addLayout(titles, 1)

        layout.addWidget(QLabel("기간", objectName="BannerSub"))
        self.start_spin, self.end_spin = QSpinBox(), QSpinBox()
        for spin in (self.start_spin, self.end_spin):
            spin.setSuffix("년")
            spin.valueChanged.connect(self.redraw)
            layout.addWidget(spin)
            if spin is self.start_spin:
                layout.addWidget(QLabel("~", objectName="BannerSub"))

        reset = QPushButton("전체 기간")
        reset.clicked.connect(self.reset_range)
        open_btn = QPushButton("엑셀 열기")
        open_btn.clicked.connect(self.choose_file)
        save_btn = QPushButton("CSV 저장")
        save_btn.clicked.connect(self.save_csv)
        for b in (reset, open_btn, save_btn):
            layout.addWidget(b)
        return banner

    def build_table(self) -> QTableWidget:
        table = QTableWidget(0, len(TABLE_COLUMNS) + 1)
        table.setHorizontalHeaderLabels(["연도"] + [h for _, h, _ in TABLE_COLUMNS])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    # ---------------------------------------------------------------- 데이터
    def load(self, path: Path) -> None:
        if not path.exists():
            picked, _ = QFileDialog.getOpenFileName(self, "출생아수 엑셀 파일 선택", str(Path.home()), "Excel (*.xlsx *.xls)")
            if not picked:
                return
            path = Path(picked)
        try:
            log = io.StringIO()
            with redirect_stdout(log):
                df = load_and_clean(path)
                print("=" * 70)
                print(f"원본 파일: {path}")
                print(f"기간: {df.index.min()}~{df.index.max()} ({len(df)}개 연도), "
                      f"결측치 {int(df[list(COLUMN_MAP.values())].isna().sum().sum())}개")
                analyze(df)
        except Exception as e:  # 형식이 다른 파일을 열었을 때
            QMessageBox.critical(self, "불러오기 실패", f"{path.name}\n\n{e}")
            return

        self.df = df
        self.sub_label.setText(f"{path.name}  ·  자료: 통계청 「인구동향조사」 (KOSIS)")
        self.report.setPlainText(log.getvalue())
        lo, hi = int(df.index.min()), int(df.index.max())
        for spin in (self.start_spin, self.end_spin):
            spin.blockSignals(True)
            spin.setRange(lo, hi)
            spin.blockSignals(False)
        self.start_spin.blockSignals(True)
        self.start_spin.setValue(max(lo, 1970))
        self.start_spin.blockSignals(False)
        self.end_spin.setValue(min(hi, 2025))
        self.fill_kpis()
        self.fill_table()
        self.redraw()

    def choose_file(self) -> None:
        picked, _ = QFileDialog.getOpenFileName(self, "출생아수 엑셀 파일 선택", str(Path.home() / "Downloads"), "Excel (*.xlsx *.xls)")
        if picked:
            self.load(Path(picked))

    def save_csv(self) -> None:
        if self.df is None:
            return
        target, _ = QFileDialog.getSaveFileName(self, "정제 데이터 저장", "births_clean.csv", "CSV (*.csv)")
        if target:
            self.df.to_csv(target, encoding="utf-8-sig")
            QMessageBox.information(self, "저장 완료", target)

    def reset_range(self) -> None:
        if self.df is not None:
            self.start_spin.setValue(int(self.df.index.min()))
            self.end_spin.setValue(int(self.df.index.max()))

    def selected(self) -> pd.DataFrame:
        lo, hi = sorted((self.start_spin.value(), self.end_spin.value()))
        return self.df.loc[lo:hi]

    # ---------------------------------------------------------------- 요약 카드
    def fill_kpis(self) -> None:
        df = self.df
        births = df["births"].astype(float)
        peak, low, last = births.idxmax(), births.idxmin(), df.index.max()
        yoy = df.loc[last, "births_yoy_pct"]
        tfr_low = df["tfr"].idxmin()
        dead = df.index[df["natural_increase"] < 0]
        cards = [
            ("최고 출생아수", f"{births[peak]:,.0f}명", f"{peak}년", FG),
            ("최저 출생아수", f"{births[low]:,.0f}명", f"{low}년 · 최고 대비 {(births[low] / births[peak] - 1) * 100:.1f}%", FG),
            (f"{last}년 출생아수", f"{births[last]:,.0f}명", f"전년 대비 {yoy:+.1f}%", RED if yoy < 0 else BLUE),
            ("합계출산율 최저", f"{df.loc[tfr_low, 'tfr']:.3f}명", f"{tfr_low}년 · {last}년 {df.loc[last, 'tfr']:.3f}명", FG),
            ("데드크로스", f"{dead.min()}년" if len(dead) else "없음", f"자연감소 {len(dead)}년째", RED if len(dead) else FG),
        ]
        for (name, value, sub), (n, v, s, color) in zip(self.kpi_labels, cards):
            name.setText(n)
            value.setText(v)
            value.setStyleSheet(f"color: {color};")
            sub.setText(s)

    def fill_table(self) -> None:
        df = self.df
        self.table.setRowCount(len(df))
        for r, (year, row) in enumerate(df.iterrows()):
            item = QTableWidgetItem(str(year))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table.setItem(r, 0, item)
            for c, (col, _, fmt) in enumerate(TABLE_COLUMNS, start=1):
                value = row[col]
                item = QTableWidgetItem("" if pd.isna(value) else fmt.format(value))
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if col in ("births_yoy_pct", "natural_increase") and not pd.isna(value):
                    item.setForeground(QColor(RED if value < 0 else BLUE))
                self.table.setItem(r, c, item)

    # ---------------------------------------------------------------- 차트
    def redraw(self) -> None:
        if self.df is None:
            return
        df = self.selected()
        self.draw_births(df)
        self.draw_deaths(df)
        self.draw_tfr(df)
        self.draw_yoy(df)
        self.draw_ratio(df)

    def draw_births(self, df: pd.DataFrame) -> None:
        """출생아수 라인 그래프 (기본 1970~2025)"""
        tab = self.births_tab
        ax = tab.new_axes()
        births = df["births"].astype(float)
        self.births_line, = ax.plot(df.index, births, color=BLUE, lw=2.5, marker="o", ms=4, label="출생아수")
        ax.plot(df.index, df["births_ma5"], color=SUB, lw=1.2, ls="--", label="5년 이동평균")

        peak, low = births.idxmax(), births.idxmin()
        marks = {df.index.min(): ("", (-10, -40)), peak: ("최고", (45, 12)),
                 low: ("최저", (0, -40)), df.index.max(): ("", (0, 18))}
        for year, (tag, offset) in marks.items():
            ax.scatter(year, births[year], color=RED, zorder=5, s=45)
            ax.annotate(f"{year}년{' ' + tag if tag else ''}\n{births[year]:,.0f}명", (year, births[year]),
                        textcoords="offset points", xytext=offset, ha="center", fontsize=9, color=FG,
                        arrowprops=dict(arrowstyle="-", color=SUB, lw=0.6))

        ax.set_title(f"대한민국 연도별 출생아수 ({df.index.min()}~{df.index.max()})", fontsize=14, pad=12)
        ax.set_xlabel("연도")
        ax.set_ylim(0, births.max() * 1.18)
        ax.yaxis.set_major_formatter(man)
        tab.legend(ax)

        self.hover = ax.annotate("", (0, 0), xytext=(12, 12), textcoords="offset points", color="white",
                                 bbox=dict(boxstyle="round", fc="#3a4180", ec=BLUE), zorder=10)
        self.hover.set_visible(False)
        self.births_ax, self.births_df = ax, df
        tab.canvas.draw_idle()

    def on_hover(self, event) -> None:
        """출생아수 그래프에서 마우스 위치의 연도 값을 말풍선으로 표시"""
        if self.df is None or event.inaxes is not self.births_ax or event.xdata is None:
            if getattr(self, "hover", None) is not None and self.hover.get_visible():
                self.hover.set_visible(False)
                self.births_tab.canvas.draw_idle()
            return
        df = self.births_df
        year = int(min(max(round(event.xdata), df.index.min()), df.index.max()))
        row = df.loc[year]
        yoy = "" if pd.isna(row["births_yoy_pct"]) else f"\n전년 대비 {row['births_yoy_pct']:+.1f}%"
        self.hover.xy = (year, float(row["births"]))
        self.hover.set_text(f"{year}년\n{row['births']:,.0f}명{yoy}\n합계출산율 {row['tfr']:.3f}")
        self.hover.set_visible(True)
        self.births_tab.canvas.draw_idle()

    def draw_deaths(self, df: pd.DataFrame) -> None:
        tab = self.deaths_tab
        ax = tab.new_axes()
        births, deaths = df["births"].astype(float), df["deaths"].astype(float)
        ax.plot(df.index, births, color=BLUE, lw=2, label="출생아수")
        ax.plot(df.index, deaths, color=RED, lw=2, label="사망자수(추정)")
        ax.fill_between(df.index, births, deaths, where=df["natural_increase"] < 0,
                        color=RED, alpha=0.2, label="자연감소 구간")
        ax.set_title("출생아수 vs 사망자수", fontsize=14, pad=12)
        ax.yaxis.set_major_formatter(man)
        tab.legend(ax)
        tab.canvas.draw_idle()

    def draw_tfr(self, df: pd.DataFrame) -> None:
        tab = self.tfr_tab
        ax = tab.new_axes()
        ax.plot(df.index, df["tfr"], color=GREEN, lw=2, marker="o", ms=3)
        for t, label in [(2.1, "인구대체수준 2.1"), (1.3, "초저출산 1.3"), (1.0, "1.0")]:
            ax.axhline(t, ls="--", lw=1, color=SUB)
            ax.text(df.index.min(), t + 0.05, label, color=SUB, fontsize=9)
        ax.set_title("합계출산율 추이", fontsize=14, pad=12)
        ax.set_ylabel("명")
        tab.canvas.draw_idle()

    def draw_yoy(self, df: pd.DataFrame) -> None:
        tab = self.yoy_tab
        ax = tab.new_axes()
        yoy = df["births_yoy_pct"]
        ax.bar(df.index, yoy, color=[RED if v < 0 else BLUE for v in yoy.fillna(0)])
        ax.axhline(0, color=SUB, lw=0.8)
        ax.set_title("출생아수 전년 대비 증감률(%)", fontsize=14, pad=12)
        tab.canvas.draw_idle()

    def draw_ratio(self, df: pd.DataFrame) -> None:
        tab = self.ratio_tab
        ax = tab.new_axes()
        ax.plot(df.index, df["sex_ratio"], color=PURPLE, lw=2)
        ax.axhspan(103, 107, color=GREEN, alpha=0.12, label="정상범위(103~107)")
        ax.set_title("출생성비 (여아 100명당 남아)", fontsize=14, pad=12)
        tab.legend(ax)
        tab.canvas.draw_idle()


def main() -> None:
    import matplotlib
    matplotlib.rcParams["font.family"] = "Malgun Gothic"
    matplotlib.rcParams["axes.unicode_minus"] = False

    app = QApplication(sys.argv)
    app.setFont(QFont("Malgun Gothic", 10))
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    window = MainWindow(path)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
