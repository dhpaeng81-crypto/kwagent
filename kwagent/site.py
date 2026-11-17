"""정적 웹사이트 생성: reports/*.json + 검증 기록 → site/ (GitHub Pages 로 배포).

site/
  index.html            최신 전망 (전 영역)
  f/<발표일>.html        과거 전망 각각
  archive.html          지난 전망 목록
  verification.html     정확도 성적표 (RPSS) + 그래프
  img/                  확률 막대그림, 검증 그래프
외부 자원 없이 열리는 단일 HTML 들이라, 어떤 정적 호스팅에도 올릴 수 있다.
"""
from __future__ import annotations

import html
import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

from .regions import REGION_LABELS
from .report import VAR_LABEL, _verdict

SOURCE_LABEL = {"combined": "최종(결합)", "statistical": "통계모델", "ec46": "ECMWF EC46",
                "gefs": "NOAA GEFS", "blend_raw": "결합(수축 전)"}

CSS = """
:root{--ink:#1d2329;--quiet:#5b6670;--line:#e3e6ea;--bg:#fafbfc;--card:#fff;
--below:#3d6fc4;--normal:#8a939c;--above:#c9473b;--accent:#2f6fdb}
*{box-sizing:border-box}body{margin:0;font-family:'Noto Sans KR',system-ui,-apple-system,'Malgun Gothic',sans-serif;
color:var(--ink);background:var(--bg);line-height:1.6}
header{background:var(--card);border-bottom:1px solid var(--line)}
.wrap{max-width:980px;margin:0 auto;padding:0 20px}
header .wrap{display:flex;align-items:center;justify-content:space-between;height:60px}
header a.brand{font-weight:700;font-size:18px;color:var(--ink);text-decoration:none}
nav a{margin-left:18px;color:var(--quiet);text-decoration:none;font-size:14px}nav a.on{color:var(--accent);font-weight:600}
h1{font-size:26px;margin:28px 0 4px}h2{font-size:20px;margin:32px 0 10px}h3{font-size:16px;margin:22px 0 8px}
.sub{color:var(--quiet);font-size:14px;margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:center}
th{color:var(--quiet);font-weight:600;font-size:13px}td.l,th.l{text-align:left}
td.p{font-variant-numeric:tabular-nums}td.top{font-weight:700;color:#fff}
.verdict{font-weight:600}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0}
.tabs a{padding:5px 12px;border:1px solid var(--line);border-radius:999px;font-size:13px;color:var(--ink);text-decoration:none;background:var(--card)}
img.chart{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
.note{font-size:13px;color:var(--quiet)}.pos{color:#1f7a4d;font-weight:600}.neg{color:#b3372d}
.narr h2{font-size:17px;margin-top:4px}.narr ul{padding-left:20px}
footer{margin:40px 0 30px;color:var(--quiet);font-size:12px}
@media (max-width:640px){th,td{padding:6px 4px;font-size:12.5px}nav a{margin-left:10px}}
"""

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" '
        'rel="stylesheet">')


def _page(title: str, body: str, active: str, root: str = "") -> str:
    nav = "".join(f'<a href="{root}{href}" class="{"on" if key == active else ""}">{name}</a>'
                  for key, href, name in (("index", "index.html", "최신 전망"),
                                          ("archive", "archive.html", "지난 전망"),
                                          ("verify", "verification.html", "정확도")))
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{FONT}
<style>{CSS}</style></head><body><header><div class="wrap"><a class="brand" href="{root}index.html">
한국 1개월 기상전망</a><nav>{nav}</nav></div></header><main class="wrap">{body}</main>
<footer class="wrap">kwagent · 자료: ERA5, ECMWF EC46, NOAA GEFS (Open-Meteo), NOAA CPC, BoM ·
확률은 1991~2020 평년 삼분위 기준 · 생성 {datetime.now():%Y-%m-%d %H:%M}</footer></body></html>"""


def md_to_html(md: str) -> str:
    """해설용 최소 마크다운 변환(제목, 굵게, 목록, 문단)."""
    out, in_list = [], False
    for raw in md.splitlines():
        line = html.escape(raw.rstrip())
        line = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", line)
        if line.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{line[2:]}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if m := re.match(r"(#{1,4})\s+(.*)", line):
            lvl = min(len(m.group(1)) + 1, 4)
            out.append(f"<h{lvl}>{m.group(2)}</h{lvl}>")
        elif line.strip():
            out.append(f"<p>{line}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _prob_cells(display: list[int], var: str) -> str:
    colors = ("var(--below)", "var(--normal)", "var(--above)")
    if var == "precip":
        colors = ("#9c6b3c", "var(--normal)", "#2e8a5a")
    elif var == "cloud":
        colors = ("#c99a2e", "var(--normal)", "#56657a")
    top = max(range(3), key=lambda k: display[k])
    cells = []
    for k, v in enumerate(display):
        if k == top and display.count(v) == 1:
            cells.append(f'<td class="p top" style="background:{colors[k]}">{v}%</td>')
        else:
            alpha = 0.10 + 0.5 * v / 100
            cells.append(f'<td class="p" style="background:color-mix(in srgb,{colors[k]} '
                         f'{alpha*100:.0f}%,white)">{v}%</td>')
    return "".join(cells)


def forecast_body(result: dict, img_prefix: str) -> str:
    issue = result["issue"]
    ix = result.get("indices", {})
    regions = list(result["regions"])
    parts = [f"<h1>1개월 기상전망</h1><p class='sub'>발표 {issue} · 다음다음 주 월요일부터 4주</p>"]
    if len(regions) > 1:
        parts.append('<div class="tabs">' + "".join(
            f'<a href="#{r}">{REGION_LABELS.get(r, r)}</a>' for r in regions) + "</div>")
    if result.get("narrative"):
        parts.append(f'<div class="card narr">{md_to_html(result["narrative"])}</div>')
    for region in regions:
        rd = result["regions"][region]
        parts.append(f'<h2 id="{region}">{REGION_LABELS.get(region, region)}</h2>')
        parts.append(f'<img class="chart" alt="{REGION_LABELS.get(region, region)} 확률" '
                     f'src="{img_prefix}forecast_{issue}_{region}.png">')
        for v in ("temp", "cloud", "precip"):
            name, lo, mid, hi, unit = VAR_LABEL[v]
            rows = []
            for wk in rd["weeks"]:
                d = wk["vars"][v]
                a, b = d["normal_range"]
                rows.append(f"<tr><td class='l'>{wk['label']}</td><td>{a}~{b}</td>"
                            f"{_prob_cells(d['display'], v)}<td class='verdict l'>"
                            f"{_verdict(d['display'], v)}</td></tr>")
            parts.append(f"<div class='card'><h3>{name}</h3><table><tr><th class='l'>주</th>"
                         f"<th>평년비슷범위({unit})</th><th>{lo}</th><th>{mid}</th><th>{hi}</th>"
                         f"<th class='l'>전망</th></tr>{''.join(rows)}</table></div>")
        rows = "".join(
            f"<tr><td class='l'>{wk['label']}</td><td>{wk['ptype']['rain_days']:.1f}</td>"
            f"<td>{wk['ptype']['snow_days']:.1f}</td><td>{wk['ptype']['p_snow']*100:.0f}%</td>"
            f"<td>{wk['ptype']['climatology']['p_snow']*100:.0f}%</td></tr>" for wk in rd["weeks"])
        parts.append("<div class='card'><h3>강수형태 (비/눈)</h3><table><tr><th class='l'>주</th>"
                     "<th>비 오는 날(일)</th><th>눈 오는 날(일)</th><th>눈 올 확률</th><th>평년 눈 확률</th>"
                     f"</tr>{rows}</table></div>")
        src = ", ".join(SOURCE_LABEL.get(s, s) for s in rd.get("dynamical_sources", [])) or "없음(통계모델만)"
        parts.append(f"<p class='note'>사용한 역학모델: {src}</p>")
    if ix:
        parts.append("<p class='note'>발표 시점 기후지수 — Niño3.4 {nino34:+.2f}, AO(7일) {ao:+.2f}, "
                     "MJO RMM1/RMM2 {rmm1:+.2f}/{rmm2:+.2f}</p>".format(**ix))
    return "".join(parts)


def verification_body(store, img_dir: Path) -> str:
    summ = store.summary()
    parts = ["<h1>정확도</h1><p class='sub'>RPSS = 평년(33/33/33%) 예보 대비 개선율. "
             "0보다 크면 평년 예보보다 낫습니다. 4주 전 예측을 ERA5 로 채점해 매주 쌓입니다.</p>"]
    if summ.empty:
        parts.append("<div class='card'>아직 채점된 예측이 없습니다. 첫 예측 후 약 5주가 지나면 나타납니다.</div>")
        return "".join(parts)
    summ = summ[summ["source"] != "blend_raw"]
    _plot_verification(summ, img_dir / "verification.png")
    parts.append('<img class="chart" alt="RPSS" src="img/verification.png">')
    order = [r for r in ("korea", "central", "south") if r in set(summ["region"])]
    for region in order + [r for r in summ["region"].unique() if r not in order]:
        parts.append(f"<h2>{REGION_LABELS.get(region, region)}</h2>")
        for v in ("temp", "cloud", "precip"):
            sub = summ[(summ["region"] == region) & (summ["var"] == v)]
            if sub.empty:
                continue
            piv = sub.pivot_table(index="source", columns="lead", values="rpss")
            cnt = sub.groupby("source")["n"].max()
            head = "".join(f"<th>{c}주</th>" for c in piv.columns)
            rows = []
            for s in ["combined", "statistical", "ec46", "gefs"]:
                if s not in piv.index:
                    continue
                cells = "".join(
                    "<td>-</td>" if pd.isna(x) else
                    f"<td class='{'pos' if x > 0 else 'neg'}'>{x:+.2f}</td>" for x in piv.loc[s])
                rows.append(f"<tr><td class='l'>{SOURCE_LABEL.get(s, s)}</td>{cells}"
                            f"<td>{int(cnt.get(s, 0))}</td></tr>")
            parts.append(f"<div class='card'><h3>{VAR_LABEL[v][0]}</h3><table><tr><th class='l'>예측원</th>"
                         f"{head}<th>채점 수</th></tr>{''.join(rows)}</table></div>")
    snow = store.df("SELECT region, lead, p_snow, obs_snow FROM ptype_verification WHERE source='combined'")
    if not snow.empty:
        snow["bs"] = (snow["p_snow"] - snow["obs_snow"]) ** 2
        t = snow.groupby(["region", "lead"])["bs"].agg(["mean", "size"]).reset_index()
        rows = "".join(f"<tr><td class='l'>{REGION_LABELS.get(r.region, r.region)}</td><td>{r.lead}주</td>"
                       f"<td>{r.mean:.3f}</td><td>{r.size}</td></tr>" for r in t.itertuples())
        parts.append("<div class='card'><h3>눈 올 확률 (Brier 점수, 0이 완벽)</h3><table><tr>"
                     f"<th class='l'>영역</th><th>주</th><th>Brier</th><th>채점 수</th></tr>{rows}</table></div>")
    return "".join(parts)


def _plot_verification(summ: pd.DataFrame, path: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .report import _korean_font
    _korean_font()
    region = "korea" if "korea" in set(summ["region"]) else summ["region"].iloc[0]
    fig, axes = plt.subplots(1, 3, figsize=(12, 3.4), sharey=True)
    colors = {"combined": "#2f6fdb", "statistical": "#8a939c", "ec46": "#c9473b", "gefs": "#2e8a5a"}
    for ax, v in zip(axes, ("temp", "cloud", "precip")):
        sub = summ[(summ["region"] == region) & (summ["var"] == v)]
        for s, c in colors.items():
            d = sub[sub["source"] == s].sort_values("lead")
            if not d.empty:
                ax.plot(d["lead"], d["rpss"], marker="o", color=c, label=SOURCE_LABEL[s],
                        linewidth=2.4 if s == "combined" else 1.4)
        ax.axhline(0, color="#999", linewidth=1)
        ax.set_title(VAR_LABEL[v][0])
        ax.set_xticks([1, 2, 3, 4], ["1주", "2주", "3주", "4주"])
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("RPSS")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, fontsize=9, frameon=False, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.08))
    fig.suptitle(f"{REGION_LABELS.get(region, region)} 주차별 정확도 (0 위 = 평년 예보보다 나음)", y=1.02)
    fig.tight_layout()
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def build(cfg, store, out: str | Path | None = None) -> str:
    rep = cfg.path("reports")
    site = Path(out) if out else cfg.root / "site"
    (site / "f").mkdir(parents=True, exist_ok=True)
    img = site / "img"
    img.mkdir(exist_ok=True)
    for png in rep.glob("forecast_*.png"):
        shutil.copy2(png, img / png.name)
    results = sorted((json.loads(p.read_text(encoding="utf-8")) for p in rep.glob("forecast_*.json")),
                     key=lambda r: r["issue"], reverse=True)
    if results:
        latest = results[0]
        (site / "index.html").write_text(
            _page(f"1개월 기상전망 {latest['issue']}", forecast_body(latest, "img/"), "index"),
            encoding="utf-8")
    else:
        (site / "index.html").write_text(_page("1개월 기상전망", "<h1>아직 전망이 없습니다</h1>", "index"),
                                         encoding="utf-8")
    for r in results:
        (site / "f" / f"{r['issue']}.html").write_text(
            _page(f"1개월 기상전망 {r['issue']}", forecast_body(r, "../img/"), "archive", root="../"),
            encoding="utf-8")
    items = []
    for r in results:
        k = r["regions"].get("korea") or next(iter(r["regions"].values()))
        w1 = k["weeks"][0]["vars"]["temp"]["display"]
        items.append(f"<tr><td class='l'><a href='f/{r['issue']}.html'>{r['issue']}</a></td>"
                     f"<td class='l'>{_verdict(w1, 'temp')}</td></tr>")
    (site / "archive.html").write_text(_page("지난 전망", "<h1>지난 전망</h1><div class='card'><table>"
                                              "<tr><th class='l'>발표일</th><th class='l'>1주 기온</th></tr>"
                                              + "".join(items) + "</table></div>", "archive"),
                                       encoding="utf-8")
    (site / "verification.html").write_text(_page("정확도", verification_body(store, img), "verify"),
                                            encoding="utf-8")
    (site / ".nojekyll").write_text("")
    return str(site)
