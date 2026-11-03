"""
S&P 500 과거 데이터 클렌징 + 다각도 분석 + 종가 라인그래프 (2000-01 ~ 2019-12)

사용법:
    python sp500_analysis.py [CSV경로]
    SP500Analysis.exe [CSV경로]   (CSV 파일을 exe 위로 끌어다 놓아도 됨)
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("TkAgg")  # PyQt6/PySide6가 같이 설치된 환경에서 Qt 백엔드 충돌 방지
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

# 한글 폰트 (Windows: 맑은 고딕)
plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

CSV_NAME = "S&P 500 과거 데이터.csv"
FROZEN = getattr(sys, "frozen", False)
# exe로 실행 시 __file__은 임시 압축해제 폴더이므로 exe가 있는 폴더를 기준으로 삼음
BASE_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).parent
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))


def find_csv() -> Path:
    """CSV 위치 우선순위: 명령행 인자 → exe/스크립트 옆 → exe에 내장된 기본 데이터"""
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    for d in (BASE_DIR, BUNDLE_DIR):
        if (d / CSV_NAME).exists():
            return d / CSV_NAME
    raise FileNotFoundError(f"'{CSV_NAME}' 파일을 찾을 수 없습니다. 실행파일과 같은 폴더에 두세요.")


OUT_DIR = BASE_DIR / "sp500_output"


# ------------------------------------------------------------------
# 1. 데이터 클렌징
# ------------------------------------------------------------------
def load_and_clean(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    print(f"[원본] {df.shape[0]}행 x {df.shape[1]}열")
    print("결측치 개수:\n", df.isna().sum(), "\n")

    # 컬럼명 영문화
    df = df.rename(columns={
        "날짜": "Date", "종가": "Close", "시가": "Open", "고가": "High",
        "저가": "Low", "거래량": "Volume", "변동 %": "Change",
    })

    # 날짜: "2019- 11- 14" 처럼 공백이 섞여 있으므로 제거 후 변환
    df["Date"] = pd.to_datetime(df["Date"].str.replace(" ", ""), format="%Y-%m-%d", errors="coerce")

    # 가격: 천단위 콤마 제거 후 float
    for col in ["Close", "Open", "High", "Low"]:
        df[col] = pd.to_numeric(df[col].str.replace(",", ""), errors="coerce")

    # 변동 %: "%" 제거 후 float
    df["Change"] = pd.to_numeric(df["Change"].str.replace("%", ""), errors="coerce")

    # 거래량: 전부 비어 있으면 열 제거
    if df["Volume"].isna().all():
        print("거래량 열이 전부 비어 있어 제거합니다.")
        df = df.drop(columns="Volume")

    # 날짜/종가가 없는 행, 중복 날짜 제거
    before = len(df)
    df = df.dropna(subset=["Date", "Close"]).drop_duplicates(subset="Date")
    print(f"유효하지 않은 행/중복 제거: {before - len(df)}행")

    # 논리 오류 검사 (고가 < 저가 등)
    bad = df[(df["High"] < df["Low"]) | (df["Close"] <= 0)]
    if not bad.empty:
        print(f"논리 오류 행 {len(bad)}개 제거")
        df = df.drop(bad.index)

    # 날짜 오름차순 정렬 + 인덱스 지정
    df = df.sort_values("Date").set_index("Date")
    print(f"[클렌징 후] {df.shape[0]}행, 기간 {df.index.min():%Y-%m-%d} ~ {df.index.max():%Y-%m-%d}\n")
    return df


# ------------------------------------------------------------------
# 2. 다각도 분석
# ------------------------------------------------------------------
def analyze(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Return"] = df["Close"].pct_change()
    df["MA50"] = df["Close"].rolling(50).mean()
    df["MA200"] = df["Close"].rolling(200).mean()
    df["Vol20"] = df["Return"].rolling(20).std() * np.sqrt(252)  # 연환산 변동성
    df["CumMax"] = df["Close"].cummax()
    df["Drawdown"] = df["Close"] / df["CumMax"] - 1

    print("=" * 60)
    print("① 기술통계 (종가/일간수익률)")
    print("=" * 60)
    print(df[["Close", "Return"]].describe().round(4), "\n")

    # 전체 기간 성과
    years = (df.index[-1] - df.index[0]).days / 365.25
    total = df["Close"].iloc[-1] / df["Close"].iloc[0] - 1
    cagr = (1 + total) ** (1 / years) - 1
    ann_vol = df["Return"].std() * np.sqrt(252)
    sharpe = df["Return"].mean() * 252 / ann_vol
    print("=" * 60)
    print("② 전체 기간 성과")
    print("=" * 60)
    print(f"시작 종가 {df['Close'].iloc[0]:,.2f} → 마지막 종가 {df['Close'].iloc[-1]:,.2f}")
    print(f"누적 수익률 {total:.2%}, CAGR {cagr:.2%}, 연 변동성 {ann_vol:.2%}, 샤프(무위험 0) {sharpe:.2f}\n")

    # 연도별 수익률
    yearly = df["Close"].resample("YE").last()
    yearly_ret = yearly.pct_change()
    yearly_ret.iloc[0] = yearly.iloc[0] / df["Close"].iloc[0] - 1
    yearly_tbl = pd.DataFrame({
        "연말종가": yearly.round(2),
        "연수익률(%)": (yearly_ret * 100).round(2),
        "연간최고": df["Close"].resample("YE").max().round(2),
        "연간최저": df["Close"].resample("YE").min().round(2),
    })
    yearly_tbl.index = yearly_tbl.index.year
    print("=" * 60)
    print("③ 연도별 수익률")
    print("=" * 60)
    print(yearly_tbl.to_string(), "\n")

    # 월별 계절성
    monthly_ret = df["Close"].resample("ME").last().pct_change()
    seasonality = monthly_ret.groupby(monthly_ret.index.month).agg(["mean", lambda s: (s > 0).mean()])
    seasonality.columns = ["평균수익률", "상승확률"]
    print("=" * 60)
    print("④ 월별 계절성")
    print("=" * 60)
    print((seasonality * 100).round(2).to_string(), "\n")

    # 요일 효과
    dow = df.groupby(df.index.dayofweek)["Return"].agg(["mean", "std", "count"])
    dow.index = ["월", "화", "수", "목", "금"][: len(dow)]
    print("=" * 60)
    print("⑤ 요일별 일간수익률(%)")
    print("=" * 60)
    print((dow[["mean", "std"]] * 100).round(3).join(dow["count"]).to_string(), "\n")

    # 최대낙폭 (MDD)
    mdd_date = df["Drawdown"].idxmin()
    peak_date = df.loc[:mdd_date, "Close"].idxmax()
    recovered = df.loc[mdd_date:][df.loc[mdd_date:, "Close"] >= df.loc[peak_date, "Close"]]
    print("=" * 60)
    print("⑥ 최대낙폭 (MDD)")
    print("=" * 60)
    print(f"MDD {df['Drawdown'].min():.2%}: 고점 {peak_date:%Y-%m-%d} → 저점 {mdd_date:%Y-%m-%d}, "
          f"회복 {recovered.index[0]:%Y-%m-%d}" if not recovered.empty else "회복 안 됨")
    print()

    # 극단적 등락일
    print("=" * 60)
    print("⑦ 일간 상승/하락 Top 5")
    print("=" * 60)
    print("상승:\n", df["Change"].nlargest(5).to_string())
    print("하락:\n", df["Change"].nsmallest(5).to_string(), "\n")

    # 골든/데드 크로스
    ma = df[["MA50", "MA200"]].dropna()  # 200일선이 계산되기 전 구간 제외
    signal = (ma["MA50"] > ma["MA200"]).astype(int).diff()
    crosses = signal[signal != 0].dropna()
    print("=" * 60)
    print("⑧ 50/200일 이동평균 교차")
    print("=" * 60)
    for d, v in crosses.items():
        print(f"{d:%Y-%m-%d}  {'골든크로스' if v > 0 else '데드크로스'}")
    print()

    yearly_tbl.to_csv(OUT_DIR / "yearly_returns.csv", encoding="utf-8-sig")
    df.to_csv(OUT_DIR / "sp500_cleaned.csv", encoding="utf-8-sig")
    return df


# ------------------------------------------------------------------
# 3. 종가 라인그래프 (2000-01 ~ 2019-12)
# ------------------------------------------------------------------
def plot_close(df: pd.DataFrame) -> None:
    data = df.loc["2000-01-01":"2019-12-31"]

    fig, ax = plt.subplots(figsize=(14, 6))
    ax.plot(data.index, data["Close"], color="#1f77b4", linewidth=1.2, label="종가")
    ax.plot(data.index, data["MA200"], color="#ff7f0e", linewidth=1, alpha=0.8, label="200일 이동평균")

    # 주요 이벤트 음영
    for start, end, label in [("2000-03-24", "2002-10-09", "닷컴 버블 붕괴"),
                              ("2007-10-09", "2009-03-09", "글로벌 금융위기")]:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end), color="gray", alpha=0.15)
        ax.text(pd.Timestamp(start), data["Close"].max() * 0.95, label, fontsize=9, color="dimgray")

    ax.set_title(f"S&P 500 종가 추이 ({data.index.min():%Y.%m} ~ {data.index.max():%Y.%m})", fontsize=15)
    ax.set_xlabel("연도")
    ax.set_ylabel("종가 (포인트)")
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(alpha=0.3)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "sp500_close_2000_2019.png", dpi=150)

    # 보조 차트: 낙폭 + 연도별 수익률
    fig2, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8))
    ax1.fill_between(data.index, data["Drawdown"] * 100, 0, color="crimson", alpha=0.4)
    ax1.set_title("고점 대비 낙폭 (Drawdown, %)")
    ax1.grid(alpha=0.3)

    yr = data["Close"].resample("YE").last().pct_change() * 100
    yr.iloc[0] = (data["Close"].resample("YE").last().iloc[0] / data["Close"].iloc[0] - 1) * 100
    ax2.bar(yr.index.year, yr.values, color=np.where(yr.values >= 0, "seagreen", "crimson"))
    ax2.set_title("연도별 수익률 (%)")
    ax2.set_xticks(yr.index.year)
    ax2.grid(alpha=0.3, axis="y")
    fig2.tight_layout()
    fig2.savefig(OUT_DIR / "sp500_drawdown_yearly.png", dpi=150)

    print(f"그래프 저장: {OUT_DIR}")
    plt.show()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    csv_path = find_csv()
    print(f"입력 파일: {csv_path}\n")
    sp = load_and_clean(csv_path)
    sp = analyze(sp)
    plot_close(sp)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n[오류] {e}")
    finally:
        # 더블클릭 실행 시 콘솔 창이 바로 닫히지 않도록 대기
        if FROZEN:
            input("\n엔터를 누르면 종료합니다...")
