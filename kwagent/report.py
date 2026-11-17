"""예측 결과 → 마크다운 표 + 확률 막대그림."""
from __future__ import annotations

from pathlib import Path

from .regions import REGION_LABELS

VAR_LABEL = {"temp": ("기온", "낮음", "비슷", "높음", "°C"),
             "cloud": ("운량", "적음", "비슷", "많음", "%"),
             "precip": ("강수량", "적음", "비슷", "많음", "mm")}


def _verdict(display: list[int], var: str) -> str:
    _, lo, mid, hi, _ = VAR_LABEL[var]
    words = (lo, mid, hi)
    top = sorted(range(3), key=lambda k: -display[k])
    if display[top[0]] == display[top[1]]:          # 예: 20/40/40 → '비슷하거나 높음'
        pair = {top[0], top[1]}
        if 1 in pair:
            return f"평년과 비슷하거나 {words[(pair - {1}).pop()]}"
        return "불확실 (양쪽 가능성)"
    i = top[0]
    if i == 1:
        return "평년과 비슷" if display[i] >= 50 else "평년과 대체로 비슷"
    return f"평년보다 {words[i]}" if display[i] >= 50 else f"평년보다 대체로 {words[i]}"


def to_markdown(result: dict) -> str:
    L = [f"# 1개월 기상전망 (발표 {result['issue']})", ""]
    ix = result.get("indices", {})
    if ix:
        L.append("기후지수: Niño3.4 {nino34:+.2f} · AO(7일) {ao:+.2f} · MJO RMM1/RMM2 {rmm1:+.2f}/{rmm2:+.2f}"
                 .format(**ix))
        L.append("")
    for region, rd in result["regions"].items():
        L += [f"## {REGION_LABELS.get(region, region)}", ""]
        for v in ("temp", "cloud", "precip"):
            name, lo, mid, hi, unit = VAR_LABEL[v]
            L += [f"### {name}", "", f"| 주 | 평년비슷범위({unit}) | {lo} | {mid} | {hi} | 전망 |",
                  "|---|---|---|---|---|---|"]
            for wk in rd["weeks"]:
                d = wk["vars"][v]
                a, b = d["normal_range"]
                L.append(f"| {wk['label']} | {a}~{b} | {d['display'][0]}% | {d['display'][1]}% | "
                         f"{d['display'][2]}% | {_verdict(d['display'], v)} |")
            L.append("")
        L += ["### 강수형태", "", "| 주 | 비 오는 날(일) | 눈 오는 날(일) | 눈 올 확률 | 평년 눈 확률 |",
              "|---|---|---|---|---|"]
        for wk in rd["weeks"]:
            p = wk["ptype"]
            L.append(f"| {wk['label']} | {p['rain_days']:.1f} | {p['snow_days']:.1f} | "
                     f"{p['p_snow']*100:.0f}% | {p['climatology']['p_snow']*100:.0f}% |")
        L += ["", f"사용한 역학모델: {', '.join(rd['dynamical_sources']) or '없음(통계모델만)'}", ""]
    return "\n".join(L)


def _korean_font():
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    for f in ("NanumGothic", "Noto Sans CJK KR", "Malgun Gothic", "AppleGothic"):
        if any(f in x.name for x in font_manager.fontManager.ttflist):
            plt.rcParams["font.family"] = f
            break
    plt.rcParams["axes.unicode_minus"] = False


def plot(result: dict, out_dir: Path) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    _korean_font()
    paths = []
    colors = {"temp": ("#4a7bd0", "#b5b5b5", "#d0574a"), "cloud": ("#e0b34a", "#b5b5b5", "#6b7a8f"),
              "precip": ("#b07d4a", "#b5b5b5", "#3f9a6b")}
    for region, rd in result["regions"].items():
        fig, axes = plt.subplots(1, 3, figsize=(12, 3.6), sharey=True)
        for ax, v in zip(axes, ("temp", "cloud", "precip")):
            name, lo, mid, hi, _ = VAR_LABEL[v]
            labels = [f"{w['lead']}주" for w in rd["weeks"]]
            bottom = [0] * len(labels)
            for k, (cat, c) in enumerate(zip((lo, mid, hi), colors[v])):
                vals = [w["vars"][v]["display"][k] for w in rd["weeks"]]
                ax.bar(labels, vals, bottom=bottom, color=c, label=cat, width=0.6)
                for i, (b, h) in enumerate(zip(bottom, vals)):
                    if h >= 15:
                        ax.text(i, b + h / 2, f"{h}", ha="center", va="center", fontsize=9, color="white")
                bottom = [b + h for b, h in zip(bottom, vals)]
            ax.set_title(name)
            ax.set_ylim(0, 100)
            ax.legend(fontsize=8, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.1))
            ax.spines[["top", "right"]].set_visible(False)
        axes[0].set_ylabel("확률(%)")
        fig.suptitle(f"{REGION_LABELS.get(region, region)} 1개월 전망 · 발표 {result['issue']}", y=1.0)
        fig.tight_layout()
        p = out_dir / f"forecast_{result['issue']}_{region}.png"
        fig.savefig(p, dpi=130, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))
    return paths
