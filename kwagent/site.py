"""정적 웹사이트 생성: reports/*.json + 검증 기록 → site/ (GitHub Pages 로 배포).

site/
  index.html            2주 일별 예측 (기본 화면; daily.html 도 같은 내용 — 옛 주소용)
  month.html            최신 1개월 전망 (전 영역)
  f/<발표일>.html        과거 전망 각각
  archive.html          지난 전망 목록
  verification.html     정확도 성적표 (RPSS) + 그래프
  img/                  확률 막대그림, 검증 그래프
  icon-*.png, apple-touch-icon.png, favicon.*, manifest.webmanifest   홈 화면 추가용 아이콘
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
from .features import VARS
from .report import VAR_LABEL, _verdict, result_vars

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
header a.brand{font-weight:700;font-size:18px;color:var(--ink);text-decoration:none;display:inline-flex;align-items:center;gap:8px}
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
tr.far td{color:var(--quiet)}td small{color:var(--quiet);font-size:11.5px}
td.warm{background:#fbe3df}td.cool{background:#dfe8f8}
.note{font-size:13px;color:var(--quiet)}.pos{color:#1f7a4d;font-weight:600}.neg{color:#b3372d}
.narr h2{font-size:17px;margin-top:4px}.narr ul{padding-left:20px}
footer{margin:40px 0 30px;color:var(--quiet);font-size:12px}
th,td{word-break:keep-all}th .u{display:block;font-size:11px;font-weight:400}
.card.tbl{overflow-x:auto}
@media (max-width:640px){
.wrap{padding:0 14px}
header .wrap{height:auto;flex-wrap:wrap;padding-top:10px;padding-bottom:4px;row-gap:2px}
header a.brand{font-size:17px;white-space:nowrap}
nav{width:100%;display:flex;overflow-x:auto;white-space:nowrap;-webkit-overflow-scrolling:touch}
nav a{margin:0 16px 0 0;padding:6px 0;font-size:14.5px}nav a.on{border-bottom:2px solid var(--accent)}
h1{font-size:22px;margin-top:20px}.sub{font-size:13px}
.card{padding:12px 8px}.card.tbl{padding:4px 4px}
th,td{padding:7px 3px;font-size:13px}th{font-size:12px}
td small{display:block;font-size:10.5px;line-height:1.3}
table.daily td.l{white-space:nowrap;font-size:12.5px}
}
"""

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" '
        'rel="stylesheet">')


STATIC = Path(__file__).parent / "static"
ICON_FILES = ("favicon.svg", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
              "icon-maskable-512.png")
ICON_HEAD = ('<link rel="icon" href="{root}favicon.svg" type="image/svg+xml">'
             '<link rel="icon" href="{root}favicon-32.png" sizes="32x32" type="image/png">'
             '<link rel="apple-touch-icon" href="{root}apple-touch-icon.png">'
             '<link rel="manifest" href="{root}manifest.webmanifest">'
             '<meta name="theme-color" content="#1f6fd1">'
             '<meta name="apple-mobile-web-app-capable" content="yes">'
             '<meta name="mobile-web-app-capable" content="yes">'
             '<meta name="apple-mobile-web-app-title" content="기상전망">'
             '<meta name="apple-mobile-web-app-status-bar-style" content="default">')
MANIFEST = {
    "name": "한국 기상전망", "short_name": "기상전망", "lang": "ko",
    "description": "2주 일별 예측과 1개월 기상전망",
    "start_url": "./index.html", "scope": "./", "display": "standalone",
    "background_color": "#fafbfc", "theme_color": "#1f6fd1",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        {"src": "favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
    ],
}


def _page(title: str, body: str, active: str, root: str = "") -> str:
    nav = "".join(f'<a href="{root}{href}" class="{"on" if key == active else ""}">{name}</a>'
                  for key, href, name in (("daily", "index.html", "2주 일별"),
                                          ("month", "month.html", "1개월 전망"),
                                          ("archive", "archive.html", "지난 전망"),
                                          ("verify", "verification.html", "정확도")))
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{FONT}
{ICON_HEAD.format(root=root)}
<style>{CSS}</style></head><body><header><div class="wrap"><a class="brand" href="{root}index.html">
<img src="{root}favicon.svg" alt="" width="26" height="26">한국 기상전망</a><nav>{nav}</nav></div></header><main class="wrap">{body}</main>
<footer class="wrap">kwagent · 자료: ERA5, ECMWF EC46·IFS·AIFS, NOAA GEFS, DWD ICON (Open-Meteo), NOAA CPC, BoM ·
평년은 1991~2020 · 생성 {datetime.now():%Y-%m-%d %H:%M}</footer></body></html>"""


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
    elif var == "srad":
        colors = ("#6f7d96", "var(--normal)", "#d9831a")
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
        for v in result_vars(rd):
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


def daily_body(result: dict, img_prefix: str) -> str:
    from .daily import MODEL_LABEL, num, sky_label
    issue = result["issue"]
    models = ", ".join(f"{MODEL_LABEL.get(k, k)}({v}멤버)" for k, v in result["models"].items()) or "없음"
    parts = [f"<h1>2주 일별 예측</h1><p class='sub'>발표 {issue} · 내일부터 14일 · "
             "괄호는 10~90% 범위 · 빨강/파랑 칸은 평년보다 2°C 이상 높음/낮음</p>"]
    regions = list(result["regions"])
    if len(regions) > 1:
        parts.append('<div class="tabs">' + "".join(
            f'<a href="#d-{r}">{REGION_LABELS.get(r, r)}</a>' for r in regions) + "</div>")

    def temp_cell(v):
        if not v:
            return "<td>-</td>"
        cls = ""
        if v.get("normal") is not None:
            an = v["q50"] - v["normal"]
            cls = " class='warm'" if an >= 2 else (" class='cool'" if an <= -2 else "")
        return f"<td{cls}>{num(v['q50'])}<small> ({num(v['q10'])}~{num(v['q90'])})</small></td>"

    for region in regions:
        rd = result["regions"][region]
        parts.append(f'<h2 id="d-{region}">{REGION_LABELS.get(region, region)}</h2>')
        parts.append(f'<img class="chart" alt="{REGION_LABELS.get(region, region)} 2주 일별" '
                     f'src="{img_prefix}daily_{issue}_{region}.png">')
        rows = []
        for day in rd["days"]:
            v = day["vars"]
            p = v.get("precip", {})
            pop = "-" if "pop" not in p else f"{p['pop']*100:.0f}%"
            if p.get("pop_normal") is not None:
                pop += f"<small> (평년 {p['pop_normal']*100:.0f}%)</small>"
            amt = "-" if not p else (f"{p['q50']:.0f}" if p["q90"] < 1 else
                                     f"{p['q50']:.0f}<small> (~{p['q90']:.0f})</small>")
            snow = "-" if p.get("p_snow") is None or p["p_snow"] < 0.05 else f"{p['p_snow']*100:.0f}%"
            sr = v.get("srad")
            srad = "-" if not sr else f"{sr['q50']:.1f}<small> ({sr['q10']:.0f}~{sr['q90']:.0f})</small>"
            far = " class='far'" if day["lead"] >= 8 else ""
            rows.append(f"<tr{far}><td class='l'>{day['label']}</td>{temp_cell(v.get('tmin'))}"
                        f"{temp_cell(v.get('tmax'))}<td>{sky_label(v.get('cloud'))}</td><td>{pop}</td>"
                        f"<td>{amt}</td><td>{snow}</td><td>{srad}</td></tr>")
        parts.append("<div class='card tbl'><table class='daily'><tr><th class='l'>날짜</th>"
                     "<th>최저<span class='u'>°C</span></th><th>최고<span class='u'>°C</span></th>"
                     "<th>하늘</th><th>강수<br>확률</th><th>강수량<span class='u'>mm</span></th><th>눈</th>"
                     "<th>일사량<span class='u'>MJ/m²</span></th></tr>"
                     + "".join(rows) + "</table></div>")
    parts.append(f"<p class='note'>사용한 모델: {models}. 8일 이후(흐린 글씨)는 불확실성이 커서 "
                 "평년과 크게 다르지 않으면 참고만 하세요.</p>")
    return "".join(parts)


def daily_verification_body(store) -> str:
    from .daily import DLABEL, LEAD_BINS, MODEL_LABEL, summary
    s = summary(store)
    head = ("<h2>2주 일별 예측</h2><p class='sub'>정답 ERA5. 평년 대비 개선 = 1 − 오차/평년예보 오차 "
            "(0보다 크면 평년보다 나음). 범위 적중률은 10~90% 범위에 실제 값이 든 비율(80%가 이상적).</p>")
    if s.empty:
        return head + "<div class='card'>아직 채점된 일별 예측이 없습니다. 첫 예측 후 약 1주가 지나면 나타납니다.</div>"
    region = "korea" if "korea" in set(s["region"]) else s["region"].iloc[0]
    c = s[(s["region"] == region) & (s["source"] == "combined")]
    bins = [b for _, _, b in LEAD_BINS]
    rows = []
    for var in DLABEL:
        sub = c[c["var"] == var].set_index("bin")
        if sub.empty:
            continue
        cells = []
        for b in bins:
            if b not in sub.index:
                cells.append("<td>-</td>")
                continue
            r = sub.loc[b]
            sk = "" if pd.isna(r["skill"]) else (f"<span class='{'pos' if r['skill'] > 0 else 'neg'}'>"
                                                 f"{r['skill']:+.2f}</span>")
            cells.append(f"<td>{r['mae']:.2f} {sk}<small> · 적중 {r['cover']*100:.0f}% · {int(r['n'])}건</small></td>")
        rows.append(f"<tr><td class='l'>{DLABEL[var][0]} ({DLABEL[var][1]})</td>{''.join(cells)}</tr>")
    out = head + ("<div class='card'><h3>최종(결합) — 평균 오차 · 평년 대비 개선</h3><table><tr><th class='l'>변수</th>"
                  + "".join(f"<th>{b}</th>" for b in bins) + "</tr>" + "".join(rows) + "</table></div>")
    pc = c[c["var"] == "precip"].set_index("bin")
    if not pc.empty and pc["brier"].notna().any():
        cells = "".join("<td>-</td>" if b not in pc.index or pd.isna(pc.at[b, "brier"]) else
                        f"<td>{pc.at[b, 'brier']:.3f}" + ("" if pd.isna(pc.at[b, "bss"]) else
                                                          f" <span class='{'pos' if pc.at[b, 'bss'] > 0 else 'neg'}'>"
                                                          f"{pc.at[b, 'bss']:+.2f}</span>") + "</td>" for b in bins)
        out += ("<div class='card'><h3>강수확률 (Brier 점수 · 평년 대비 개선)</h3><table><tr><th class='l'></th>"
                + "".join(f"<th>{b}</th>" for b in bins) + f"</tr><tr><td class='l'>최종(결합)</td>{cells}</tr></table></div>")
    m = s[(s["region"] == region) & (s["var"] == "tmax")]
    if not m.empty:
        piv = m.pivot_table(index="source", columns="bin", values="mae")
        rows = "".join(f"<tr><td class='l'>{MODEL_LABEL.get(src, src)}</td>" + "".join(
            "<td>-</td>" if b not in piv.columns or pd.isna(piv.at[src, b]) else f"<td>{piv.at[src, b]:.2f}</td>"
            for b in bins) + "</tr>" for src in piv.index)
        out += ("<div class='card'><h3>모델별 최고기온 평균 오차(°C)</h3><table><tr><th class='l'>모델</th>"
                + "".join(f"<th>{b}</th>" for b in bins) + "</tr>" + rows + "</table></div>")
    return out


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
        for v in VARS:
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
    vs = [v for v in VARS if v in set(summ["var"])] or list(VARS)
    fig, axes = plt.subplots(1, len(vs), figsize=(4 * len(vs), 3.4), sharey=True, squeeze=False)
    axes = axes[0]
    colors = {"combined": "#2f6fdb", "statistical": "#8a939c", "ec46": "#c9473b", "gefs": "#2e8a5a"}
    for ax, v in zip(axes, vs):
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
        (site / "month.html").write_text(
            _page(f"1개월 기상전망 {latest['issue']}", forecast_body(latest, "img/"), "month"),
            encoding="utf-8")
    else:
        (site / "month.html").write_text(_page("1개월 기상전망", "<h1>아직 전망이 없습니다</h1>", "month"),
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
    (site / "verification.html").write_text(
        _page("정확도", verification_body(store, img) + daily_verification_body(store), "verify"),
        encoding="utf-8")
    # 2주 일별 예측 (최신 1개)
    dd = rep / "daily"
    dailies = sorted(dd.glob("daily_*.json")) if dd.exists() else []
    if dailies:
        for png in dd.glob(f"{dailies[-1].stem}_*.png"):
            shutil.copy2(png, img / png.name)
        latest = json.loads(dailies[-1].read_text(encoding="utf-8"))
        body = daily_body(latest, "img/")
    else:
        body = "<h1>2주 일별 예측</h1><div class='card'>아직 일별 예측이 없습니다. 매일 아침 6시 40분에 만들어집니다.</div>"
    page = _page("2주 일별 예측", body, "daily")
    for name in ("index.html", "daily.html"):          # 기본 화면 = 2주 일별 (daily.html 은 옛 주소)
        (site / name).write_text(page, encoding="utf-8")
    # 홈 화면 추가용 아이콘·매니페스트
    for name in ICON_FILES:
        shutil.copy2(STATIC / name, site / name)
    (site / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    (site / ".nojekyll").write_text("")
    return str(site)
