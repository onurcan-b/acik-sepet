from __future__ import annotations

import csv
from pathlib import Path

import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
INDEX_PATH = ROOT / "data" / "index.csv"
CHART_PATH = ROOT / "charts" / "index.svg"
README_PATH = ROOT / "README.md"
START = "<!-- STATS_START -->"
END = "<!-- STATS_END -->"


def _read_rows() -> list[dict[str, str]]:
    if not INDEX_PATH.exists():
        return []
    with INDEX_PATH.open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _valid_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("index") not in (None, "")]


def _change(rows: list[dict[str, str]], days_back: int) -> float | None:
    valid = _valid_rows(rows)
    if len(valid) <= days_back:
        return None
    latest = float(valid[-1]["index"])
    previous = float(valid[-1 - days_back]["index"])
    return (latest / previous - 1.0) * 100.0


def render_chart(rows: list[dict[str, str]]) -> None:
    CHART_PATH.parent.mkdir(parents=True, exist_ok=True)
    valid = _valid_rows(rows)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    if valid:
        dates = [row["date"] for row in valid]
        values = [float(row["index"]) for row in valid]
        ax.plot(dates, values, linewidth=2)
        ax.axhline(100, linewidth=1, linestyle="--")
        ax.set_ylabel("Endeks (baz = 100)")
        ax.set_title("Açık Sepet Günlük Market Fiyat Endeksi")
        step = max(1, len(dates) // 8)
        ax.set_xticks(range(0, len(dates), step), [dates[i] for i in range(0, len(dates), step)], rotation=30, ha="right")
        ax.grid(True, alpha=0.2)
    else:
        ax.text(0.5, 0.55, "Henüz gerçek snapshot yok", ha="center", va="center", fontsize=16)
        ax.text(0.5, 0.43, "İlk GitHub Actions çalışmasından sonra grafik otomatik oluşacak.", ha="center", va="center")
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(CHART_PATH, format="svg")
    plt.close(fig)


def update_readme(rows: list[dict[str, str]]) -> None:
    text = README_PATH.read_text(encoding="utf-8")
    valid = _valid_rows(rows)
    if valid:
        latest = valid[-1]
        change_30 = _change(rows, 30)
        change_7 = _change(rows, 7)
        stats = [
            f"- **Son değer:** {float(latest['index']):.2f}",
            f"- **Son güncelleme:** {latest['date']}",
            f"- **Kapsama:** %{float(latest['coverage']) * 100:.0f} ({latest['items']} ürün)",
            f"- **7 günlük değişim:** {'—' if change_7 is None else f'{change_7:+.2f}%'}",
            f"- **30 günlük değişim:** {'—' if change_30 is None else f'{change_30:+.2f}%'}",
            f"- **Baz tarihi:** {latest['baseline_date']} = 100",
        ]
    else:
        stats = [
            "- **Durum:** İlk gerçek snapshot bekleniyor.",
            "- **Grafik:** İlk başarılı GitHub Actions koşusundan sonra otomatik güncellenecek.",
        ]
    replacement = START + "\n" + "\n".join(stats) + "\n" + END
    before, marker, tail = text.partition(START)
    if not marker:
        raise RuntimeError("README stats başlangıç işareti bulunamadı")
    _, marker2, after = tail.partition(END)
    if not marker2:
        raise RuntimeError("README stats bitiş işareti bulunamadı")
    README_PATH.write_text(before + replacement + after, encoding="utf-8")


def main() -> None:
    rows = _read_rows()
    render_chart(rows)
    update_readme(rows)
    print(f"chart={CHART_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
