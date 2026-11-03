"""
대한민국 출생아수 1970~2025 라인 그래프

사용법: python birth_line_chart.py [엑셀파일경로]
결과물: birth_output/births_1970_2025.png
"""
import sys
from pathlib import Path

import matplotlib.pyplot as plt

from birth_analysis import DEFAULT_PATH, OUT_DIR, load_and_clean

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False


def main() -> None:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH
    df = load_and_clean(path).loc[1970:2025]
    births = df["births"].astype(float)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.plot(df.index, births, color="#1f6feb", lw=2.5, marker="o", ms=4, label="출생아수")
    ax.plot(df.index, df["births_ma5"], color="gray", lw=1.2, ls="--", label="5년 이동평균")

    # 주요 시점 표시: 첫해, 최고, 최저, 마지막 해 (라벨이 겹치지 않도록 위치를 따로 지정)
    peak, low = births.idxmax(), births.idxmin()
    points = {
        df.index.min(): ("", (-10, -40)),
        peak: ("최고", (45, 12)),
        low: ("최저", (0, -40)),
        df.index.max(): ("", (0, 18)),
    }
    for year, (tag, offset) in points.items():
        value = births[year]
        text = f"{year}년{' ' + tag if tag else ''}\n{value:,.0f}명"
        ax.annotate(text, (year, value), textcoords="offset points",
                    xytext=offset, ha="center", fontsize=9,
                    arrowprops=dict(arrowstyle="-", color="gray", lw=0.6))
        ax.scatter(year, value, color="#d1495b", zorder=5, s=40)

    ax.set_title("대한민국 연도별 출생아수 (1970~2025)", fontsize=16, pad=15)
    ax.set_xlabel("연도")
    ax.set_ylabel("출생아수")
    ax.set_xticks(range(1970, 2026, 5))
    ax.set_xlim(1968, 2027)
    ax.set_ylim(0, births.max() * 1.15)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 10000:,.0f}만")
    ax.grid(alpha=0.3)
    ax.legend(loc="upper right")
    fig.text(0.99, 0.01, "자료: 통계청 「인구동향조사」 (KOSIS)", ha="right", fontsize=8, color="gray")
    fig.tight_layout()

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / "births_1970_2025.png"
    fig.savefig(out, dpi=150)
    print(f"저장: {out.resolve()}")
    plt.show()


if __name__ == "__main__":
    main()
