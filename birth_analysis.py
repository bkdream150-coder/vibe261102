"""
대한민국 출생아수·합계출산율·자연증가 데이터 클렌징 및 다각도 분석

원본: KOSIS 「인구동향조사」 (통계표 INH_1B8000F_01), 1970~2025
사용법: python birth_analysis.py [엑셀파일경로]
결과물: birth_output/ 폴더 (정제 데이터 CSV, 분석 결과 CSV, 차트 PNG)
"""
import sys
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

DEFAULT_PATH = Path.home() / "Downloads" / "출생아수__합계출산율__자연증가_등.xlsx"
OUT_DIR = Path(__file__).parent / "birth_output"

# 원본 항목명 -> 분석용 컬럼명
COLUMN_MAP = {
    "출생아수(명)": "births",
    "자연증가건수(명)": "natural_increase",
    "조출생률(천명당)": "crude_birth_rate",
    "자연증가율(천명당)": "natural_increase_rate",
    "합계출산율(명)": "tfr",
    "출생성비(명)": "sex_ratio",
}
KOREAN_LABEL = {v: k for k, v in COLUMN_MAP.items()} | {
    "deaths": "사망자수(명, 추정)",
    "est_population": "추정 총인구(명)",
}

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


# ---------------------------------------------------------------------------
# 1. 데이터 클렌징
# ---------------------------------------------------------------------------
def load_and_clean(path: Path) -> pd.DataFrame:
    """KOSIS 가로형(연도가 열) 시트를 연도 x 지표의 세로형 DataFrame으로 정제한다."""
    raw = pd.read_excel(path, sheet_name=0, header=0, index_col=0)

    # (1) 행/열 전치: 연도를 행 인덱스로
    df = raw.T

    # (2) 컬럼명 공백 제거 후 영문명으로 변경, 정의되지 않은 항목은 제외
    df.columns = df.columns.astype(str).str.strip()
    unknown = set(df.columns) - set(COLUMN_MAP)
    if unknown:
        print(f"[클렌징] 매핑되지 않은 항목 제외: {sorted(unknown)}")
    df = df.rename(columns=COLUMN_MAP)[list(COLUMN_MAP.values())]
    df.columns.name = None

    # (3) 연도 인덱스 정수화 ('1970.0', '2025 p)' 같은 표기도 처리)
    years = pd.to_numeric(
        df.index.astype(str).str.extract(r"(\d{4})")[0], errors="coerce"
    )
    df.index = years
    df = df[df.index.notna()]
    df.index = df.index.astype(int)
    df.index.name = "year"

    # (4) 값 숫자형 변환: 쉼표, 공백, '-', 'x' 등 비수치 표기는 결측 처리
    for col in df.columns:
        cleaned = df[col].astype(str).str.replace(",", "").str.strip()
        df[col] = pd.to_numeric(cleaned, errors="coerce")

    # (5) 중복 연도 제거, 연도순 정렬
    dup = df.index.duplicated(keep="last")
    if dup.any():
        print(f"[클렌징] 중복 연도 제거: {df.index[dup].tolist()}")
    df = df[~dup].sort_index()

    # (6) 정수형이어야 하는 인원 수 컬럼은 nullable 정수로
    for col in ["births", "natural_increase"]:
        df[col] = df[col].round().astype("Int64")

    # (7) 이상치/범위 검증 (논리적으로 불가능한 값은 결측 처리)
    rules = {
        "births": (0, None),
        "crude_birth_rate": (0, 100),
        "tfr": (0, 10),
        "sex_ratio": (80, 150),
    }
    for col, (lo, hi) in rules.items():
        bad = (df[col] < lo) if lo is not None else pd.Series(False, df.index)
        if hi is not None:
            bad |= df[col] > hi
        if bad.any():
            print(f"[클렌징] {col} 범위 이탈값 결측 처리: {df.index[bad].tolist()}")
            df.loc[bad, col] = pd.NA

    # (8) 결측 처리: 연도 사이 결측은 선형 보간 (양 끝은 그대로 둠)
    missing = df.isna().sum()
    if missing.any():
        print(f"[클렌징] 결측치 개수:\n{missing[missing > 0]}")
        df = df.interpolate(method="linear", limit_area="inside")

    # (9) 파생 변수
    #   사망자수 = 출생아수 - 자연증가건수
    #   추정 총인구 = 출생아수 / 조출생률 * 1000
    df["deaths"] = df["births"] - df["natural_increase"]
    df["est_population"] = (df["births"] / df["crude_birth_rate"] * 1000).round()
    df["births_yoy_pct"] = df["births"].astype(float).pct_change() * 100
    df["births_ma5"] = df["births"].astype(float).rolling(5, center=True).mean()
    df["decade"] = (df.index // 10 * 10).astype(str) + "년대"

    return df


def report_cleaning(df: pd.DataFrame) -> None:
    print("=" * 70)
    print("1. 데이터 클렌징 결과")
    print("=" * 70)
    print(f"기간: {df.index.min()}~{df.index.max()} ({len(df)}개 연도)")
    expected = set(range(df.index.min(), df.index.max() + 1))
    print(f"누락 연도: {sorted(expected - set(df.index)) or '없음'}")
    print(f"남은 결측치: {int(df[list(COLUMN_MAP.values())].isna().sum().sum())}개")
    print("\n[자료형]")
    print(df.dtypes.to_string())
    print("\n[정제 데이터 앞 5행]")
    print(df.head().to_string())


# ---------------------------------------------------------------------------
# 2. 다각도 분석
# ---------------------------------------------------------------------------
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def analyze(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    results: dict[str, pd.DataFrame] = {}
    births = df["births"].astype(float)

    # 2-1. 기술통계
    section("2-1. 기술통계")
    cols = ["births", "natural_increase", "deaths", "crude_birth_rate", "tfr", "sex_ratio"]
    desc = df[cols].astype(float).describe().T
    desc.index = [KOREAN_LABEL[c] for c in desc.index]
    print(desc.round(2).to_string())
    results["descriptive_stats"] = desc

    # 2-2. 정점 대비 감소
    section("2-2. 출생아수 최고·최저와 감소 폭")
    peak_year, low_year = births.idxmax(), births.idxmin()
    last_year = df.index.max()
    print(f"최고: {peak_year}년 {births[peak_year]:,.0f}명")
    print(f"최저: {low_year}년 {births[low_year]:,.0f}명")
    print(f"최고 대비 최저 감소율: {(births[low_year] / births[peak_year] - 1) * 100:.1f}%")
    print(f"{df.index.min()}년 대비 {last_year}년: "
          f"{(births[last_year] / births.iloc[0] - 1) * 100:.1f}%")

    # 2-3. 연대별 평균
    section("2-3. 연대별 평균")
    decade = df.groupby("decade")[["births", "deaths", "crude_birth_rate", "tfr", "sex_ratio"]].mean()
    decade["births_change_pct"] = decade["births"].pct_change() * 100
    print(decade.round(2).to_string())
    results["decade_summary"] = decade

    # 2-4. 전년 대비 증감
    section("2-4. 전년 대비 출생아수 증감률 (상·하위 5개 연도)")
    yoy = df["births_yoy_pct"].dropna()
    print("[가장 크게 감소]")
    print(yoy.nsmallest(5).round(2).to_string())
    print("[가장 크게 증가]")
    print(yoy.nlargest(5).round(2).to_string())
    print(f"감소한 해: {(yoy < 0).sum()}회 / 증가한 해: {(yoy > 0).sum()}회")
    # 최장 연속 감소 구간
    streak, best, end = 0, 0, None
    for y, v in yoy.items():
        streak = streak + 1 if v < 0 else 0
        if streak > best:
            best, end = streak, y
    print(f"최장 연속 감소: {end - best + 1}~{end}년 ({best}년 연속)")

    # 2-5. 구간별 연평균 증가율(CAGR)
    section("2-5. 구간별 출생아수 연평균 증가율(CAGR)")
    periods = [(1970, 1983), (1983, 2000), (2000, 2015), (2015, 2023), (2023, last_year)]
    cagr = pd.DataFrame(
        [
            {
                "구간": f"{s}~{e}",
                "시작": births[s],
                "끝": births[e],
                "CAGR(%)": ((births[e] / births[s]) ** (1 / (e - s)) - 1) * 100,
            }
            for s, e in periods
            if s in births.index and e in births.index and e > s
        ]
    ).set_index("구간")
    print(cagr.round(2).to_string())
    results["cagr"] = cagr

    # 2-6. 합계출산율 기준선 통과 시점
    section("2-6. 합계출산율 주요 기준선 하회 시점")
    thresholds = {
        "인구대체수준(2.1)": 2.1,
        "저출산(1.5)": 1.5,
        "초저출산(1.3)": 1.3,
        "1.0명": 1.0,
    }
    for name, t in thresholds.items():
        below = df.index[df["tfr"] < t]
        print(f"{name:<14} 최초 하회: {below.min() if len(below) else '없음'}년")
    tfr_low = df["tfr"].idxmin()
    print(f"합계출산율 최저: {tfr_low}년 {df.loc[tfr_low, 'tfr']}명")

    # 2-7. 인구 데드크로스
    section("2-7. 출생 vs 사망 (데드크로스)")
    dead = df.index[df["natural_increase"] < 0]
    print(f"자연감소(사망>출생) 최초 연도: {dead.min() if len(dead) else '없음'}년")
    print(f"자연감소 지속 연수: {len(dead)}년")
    print(df.loc[df.index >= 2015, ["births", "deaths", "natural_increase"]].to_string())

    # 2-8. 출생성비
    section("2-8. 출생성비 (정상범위 103~107)")
    ratio = df["sex_ratio"]
    abnormal = df.index[ratio > 107]
    print(f"최고: {ratio.idxmax()}년 {ratio.max()} (여아 100명당 남아)")
    print(f"정상범위 초과 연도 수: {len(abnormal)}개, 마지막 초과 연도: {abnormal.max()}년")
    print(df.groupby("decade")["sex_ratio"].agg(["mean", "max", "min"]).round(1).to_string())

    # 2-9. 상관관계
    section("2-9. 지표 간 상관계수")
    corr = df[["births", "deaths", "crude_birth_rate", "tfr", "sex_ratio", "est_population"]].astype(float).corr()
    print(corr.round(3).to_string())
    results["correlation"] = corr

    # 2-10. 최근 반등 여부
    section("2-10. 최근 추세 (2020년 이후)")
    print(df.loc[df.index >= 2020, ["births", "births_yoy_pct", "tfr", "crude_birth_rate"]]
          .round(2).to_string())

    return results


# ---------------------------------------------------------------------------
# 3. 분석 차트
# ---------------------------------------------------------------------------
def save_charts(df: pd.DataFrame) -> None:
    years = df.index

    # (1) 출생 vs 사망
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(years, df["births"], color="#1f6feb", lw=2, label="출생아수")
    ax.plot(years, df["deaths"], color="#d1495b", lw=2, label="사망자수(추정)")
    ax.fill_between(years, df["births"].astype(float), df["deaths"].astype(float),
                    where=df["natural_increase"] < 0, color="#d1495b", alpha=0.15,
                    label="자연감소 구간")
    ax.set_title("출생아수 vs 사망자수")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 10000:,.0f}만")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "births_vs_deaths.png", dpi=150)
    plt.close(fig)

    # (2) 합계출산율과 기준선
    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(years, df["tfr"], color="#2a9d8f", lw=2, marker="o", ms=3)
    for t, label in [(2.1, "인구대체수준 2.1"), (1.3, "초저출산 1.3"), (1.0, "1.0")]:
        ax.axhline(t, ls="--", lw=1, color="gray")
        ax.text(years.min(), t + 0.05, label, color="gray", fontsize=9)
    ax.set_title("합계출산율 추이")
    ax.set_ylabel("명")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "tfr_trend.png", dpi=150)
    plt.close(fig)

    # (3) 전년 대비 증감률
    fig, ax = plt.subplots(figsize=(12, 5))
    yoy = df["births_yoy_pct"]
    ax.bar(years, yoy, color=["#d1495b" if v < 0 else "#1f6feb" for v in yoy.fillna(0)])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title("출생아수 전년 대비 증감률(%)")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT_DIR / "births_yoy.png", dpi=150)
    plt.close(fig)

    # (4) 출생성비
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(years, df["sex_ratio"], color="#6c4ab6", lw=2)
    ax.axhspan(103, 107, color="green", alpha=0.1, label="정상범위(103~107)")
    ax.set_title("출생성비 (여아 100명당 남아)")
    ax.grid(alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "sex_ratio.png", dpi=150)
    plt.close(fig)


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    OUT_DIR.mkdir(exist_ok=True)

    df = load_and_clean(path)
    report_cleaning(df)
    df.to_csv(OUT_DIR / "births_clean.csv", encoding="utf-8-sig")

    results = analyze(df)
    for name, table in results.items():
        table.to_csv(OUT_DIR / f"{name}.csv", encoding="utf-8-sig")

    save_charts(df)
    print(f"\n결과 저장 위치: {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
