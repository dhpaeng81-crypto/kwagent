"""예측 결과 → 마크다운 표 + 확률 막대그림."""
from __future__ import annotations

from pathlib import Path

from .features import VARS
from .regions import REGION_LABELS

VAR_LABEL = {"temp": ("기온", "낮음", "비슷", "높음", "°C"),
             "cloud": ("운량", "적음", "비슷", "많음", "%"),
             "srad": ("일사량", "적음", "비슷", "많음", "MJ/m²"),
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


def result_vars(rd: dict) -> list[str]:
    """이 예측에 들어 있는 변수 (일사량이 없던 옛 예측도 그대로 표시)."""
    have = rd["weeks"][0]["vars"] if rd.get("weeks") else {}
    return [v for v in VARS if v in have]


def to_markdown(result: dict) -> str:
    L = [f"# 1개월 기상전망 (발표 {result['issue']})", ""]
    ix = result.get("indices", {})
    if ix:
        L.append("기후지수: Niño3.4 {nino34:+.2f} · AO(7일) {ao:+.2f} · MJO RMM1/RMM2 {rmm1:+.2f}/{rmm2:+.2f}"
                 .format(**ix))
        L.append("")
    for region, rd in result["regions"].items():
        L += [f"## {REGION_LABELS.get(region, region)}", ""]
        for v in result_vars(rd):
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
              "srad": ("#7d8aa3", "#b5b5b5", "#e08a1e"),
              "precip": ("#b07d4a", "#b5b5b5", "#3f9a6b")}
    for region, rd in result["regions"].items():
        vs = result_vars(rd)
        fig, axes = plt.subplots(1, len(vs), figsize=(4 * len(vs), 3.6), sharey=True, squeeze=False)
        axes = axes[0]
        for ax, v in zip(axes, vs):
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


SOURCE_NAME = {"statistical": "통계모델", "ec46": "ECMWF EC46", "gefs": "NOAA GEFS"}


def to_excel(result: dict, path) -> Path:
    """1개월 전망을 엑셀(.xlsx)로: 영역마다 '확률' 시트 + '강수형태' 시트, 그리고 설명 시트."""
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    path = Path(path)

    def style(ws, widths):
        fill = PatternFill("solid", fgColor="E8EEF8")
        for c in ws[1]:
            c.font = Font(bold=True)
            c.fill = fill
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.row_dimensions[1].height = 32
        ws.freeze_panes = "C2"
        for i, c in enumerate(ws[1], start=1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(c.value, 11)

    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for region, rd in result["regions"].items():
            rname = REGION_LABELS.get(region, region)
            rows, prow = [], []
            for wk in rd["weeks"]:
                for v in result_vars(rd):
                    name, lo, mid, hi, unit = VAR_LABEL[v]
                    d = wk["vars"][v]
                    row = {"주": wk["label"].split(" ")[0], "시작": wk["start"], "끝": wk["end"], "변수": name,
                           "단위": unit, "평년비슷 하한": d["normal_range"][0], "평년비슷 상한": d["normal_range"][1],
                           "역학모델 예측 중심": None if d.get("ens_mean_corrected") is None
                           else round(d["ens_mean_corrected"], 1),
                           f"낮음·적음(%)": d["display"][0], f"비슷(%)": d["display"][1], f"높음·많음(%)": d["display"][2],
                           "전망": _verdict(d["display"], v),
                           "반올림 전 낮음": round(d["prob"][0], 3), "반올림 전 비슷": round(d["prob"][1], 3),
                           "반올림 전 높음": round(d["prob"][2], 3)}
                    for s, p in (d.get("sources") or {}).items():
                        sn = SOURCE_NAME.get(s, s)
                        row[f"{sn} 낮음/비슷/높음(%)"] = "/".join(f"{q*100:.0f}" for q in p)
                        row[f"{sn} 가중치(%)"] = round((d.get("weights") or {}).get(s, 0) * 100)
                    rows.append(row)
                pt = wk["ptype"]
                prow.append({"주": wk["label"].split(" ")[0], "시작": wk["start"], "끝": wk["end"],
                             "비 오는 날(일)": round(pt["rain_days"], 1), "평년 비 오는 날": round(pt["climatology"]["rain_days"], 1),
                             "눈 오는 날(일)": round(pt["snow_days"], 1), "평년 눈 오는 날": round(pt["climatology"]["snow_days"], 1),
                             "눈 올 확률(%)": round(pt["p_snow"] * 100), "평년 눈 확률(%)": round(pt["climatology"]["p_snow"] * 100)})
            sh = f"{rname} 확률"[:31]
            pd.DataFrame(rows).to_excel(xw, sheet_name=sh, index=False)
            style(xw.sheets[sh], {"시작": 12, "끝": 12, "전망": 24})
            sh = f"{rname} 강수형태"[:31]
            pd.DataFrame(prow).to_excel(xw, sheet_name=sh, index=False)
            style(xw.sheets[sh], {"시작": 12, "끝": 12})
        ix = result.get("indices") or {}
        info = pd.DataFrame({"항목": ["발표일", "대상", "확률", "평년비슷 범위", "역학모델 예측 중심", "모델별",
                                     "강수형태", "기후지수", "만든 곳"], "설명": [
            result["issue"], "발표일이 속한 주의 다음다음 주 월요일부터 4주, 영역평균(주요 지점 단순평균)",
            "1991~2020 평년을 셋으로 나눈 구간(낮음/비슷/높음)에 들 확률. 표시는 10% 단위(합 100)",
            "평년의 가운데 1/3 구간 (기온·운량·일사량은 주평균, 강수량은 주합)",
            "EC46·GEFS 앙상블 평균을 편향 보정한 값 (참고용)",
            "통계모델·EC46·GEFS 각각의 확률과 결합 가중치",
            "일강수 1 mm 이상인 날 = 강수일, 그중 비가 아닌 비율이 절반 이상이면 눈 오는 날",
            ", ".join(f"{k} {v:+.2f}" for k, v in ix.items()) or "-",
            "kwagent (https://dhpaeng81-crypto.github.io/kwagent/)"]})
        info.to_excel(xw, sheet_name="설명", index=False)
        ws = xw.sheets["설명"]
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 90
        for c in ws[1]:
            c.font = Font(bold=True)
    return path
