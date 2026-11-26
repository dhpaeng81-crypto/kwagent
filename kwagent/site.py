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

from . import rights
from .methods import METHODS_CSS, methods_block
from .regions import REGION_LABELS, REGION_ORDER
from .features import VARS
from .report import VAR_LABEL, _verdict, result_vars

SOURCE_LABEL = {"combined": "최종(결합)", "statistical": "통계모델", "ec46": "ECMWF EC46",
                "gefs": "NOAA GEFS", "blend_raw": "결합(수축 전)", "kma": "기상청 1개월전망"}

CSS = """
:root{--ink:#1d2329;--quiet:#5b6670;--line:#e3e6ea;--bg:#fafbfc;--card:#fff;
--below:#3d6fc4;--normal:#8a939c;--above:#c9473b;--accent:#2f6fdb}
*{box-sizing:border-box}body{margin:0;font-family:'Noto Sans KR',system-ui,-apple-system,'Malgun Gothic',sans-serif;
color:var(--ink);background:var(--bg);line-height:1.6}
header{background:var(--card);border-bottom:1px solid var(--line)}
.wrap{max-width:980px;margin:0 auto;padding:0 20px}
header .wrap{display:flex;align-items:center;height:60px;gap:8px}header nav{margin-left:auto}
.rf{display:inline-flex;align-items:center;gap:5px;font:inherit;font-size:13px;color:var(--accent);background:var(--card);
border:1px solid var(--line);border-radius:999px;padding:5px 11px 5px 9px;cursor:pointer;margin-left:10px}
.rf:hover{border-color:var(--accent)}.rf.spin svg{animation:kwspin .6s linear infinite}
@keyframes kwspin{to{transform:rotate(360deg)}}
#kwToast{position:fixed;left:50%;bottom:24px;transform:translate(-50%,20px);background:rgba(24,30,38,.94);color:#fff;
padding:10px 16px;border-radius:12px;font-size:14px;opacity:0;pointer-events:none;transition:.25s;z-index:50;
max-width:calc(100% - 32px);box-shadow:0 6px 20px rgba(0,0,0,.2)}
#kwToast.show{opacity:1;transform:translate(-50%,0);pointer-events:auto}
#kwToast{display:flex;align-items:center;gap:10px;white-space:nowrap}
#kwToast button{font:inherit;margin-left:0;flex:none;background:#fff;color:var(--accent);border:0;border-radius:8px;padding:4px 10px;
font-weight:600;cursor:pointer}
header a.brand{font-weight:700;font-size:18px;color:var(--ink);text-decoration:none;display:inline-flex;align-items:center;gap:8px}
nav a{margin-left:18px;color:var(--quiet);text-decoration:none;font-size:14px}nav a.on{color:var(--accent);font-weight:600}
h1{font-size:26px;margin:28px 0 4px}h2{font-size:20px;margin:32px 0 10px}h3{font-size:16px;margin:22px 0 8px}
.sub{color:var(--quiet);font-size:14px;margin:0 0 18px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px 20px;margin:14px 0}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:7px 8px;border-bottom:1px solid var(--line);text-align:center}
th{color:var(--quiet);font-weight:600;font-size:13px}td.l,th.l{text-align:left}
td.p{font-variant-numeric:tabular-nums}td.top{font-weight:700;color:#fff}
.rtabs{position:sticky;top:0;z-index:5;display:flex;gap:6px;flex-wrap:wrap;padding:10px 0;margin:4px 0 6px;
background:var(--bg)}.rtabs button{font:inherit;font-size:14px;padding:6px 16px;border:1px solid var(--line);border-radius:999px;
background:var(--card);color:var(--ink);cursor:pointer}.rtabs button.on{background:var(--accent);border-color:var(--accent);color:#fff;font-weight:600}
.rsec[hidden]{display:none}
.verdict{font-weight:600}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 0}
.tabs a{padding:5px 12px;border:1px solid var(--line);border-radius:999px;font-size:13px;color:var(--ink);text-decoration:none;background:var(--card)}
img.chart{width:100%;height:auto;border:1px solid var(--line);border-radius:8px;background:#fff}
tr.far td{color:var(--quiet)}td small{color:var(--quiet);font-size:11.5px}
td.warm{background:#fbe3df}td.cool{background:#dfe8f8}
.note{font-size:13px;color:var(--quiet)}.pos{color:#1f7a4d;font-weight:600}.neg{color:#b3372d}
.narr h2{font-size:17px;margin-top:4px}.narr ul{padding-left:20px}
footer{margin:40px 0 30px;color:var(--quiet);font-size:12px;line-height:1.6}footer p{margin:4px 0}footer .cr{color:var(--ink);font-weight:500}footer a{color:var(--accent)}
.terms h3{margin:18px 0 6px;font-size:16px}.terms p,.terms li{font-size:14px;line-height:1.75}
.headrow{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;flex-wrap:wrap}
.btn{display:inline-block;padding:8px 16px;border-radius:8px;background:var(--accent);color:#fff;text-decoration:none;
font-size:14px;font-weight:600;margin-bottom:18px;white-space:nowrap}.btn:hover{filter:brightness(1.08)}
.chartcard{padding:16px 20px 12px;margin:0 0 22px}.chartcard h3{margin:0 0 2px;font-size:17px}.chartcard .note{margin:0 0 6px}
.cbox{position:relative;height:300px}h3.rg{font-size:18px;margin:26px 0 10px}
.sel{font:inherit;font-size:14px;padding:6px 10px;border:1px solid var(--line);border-radius:8px;background:#fff;margin-bottom:8px}.cbox.m{height:230px}table.mt{margin-top:12px}
th,td{word-break:keep-all}th .u{display:block;font-size:11px;font-weight:400}
.card.tbl{overflow-x:auto}
/* ---- 2026-11 화면 정리: 한눈에 요약, 버튼으로 고르는 그래프, 펼치는 날짜 줄 ---- */
.phead{display:flex;justify-content:space-between;align-items:flex-end;gap:12px;margin:28px 0 4px}
.phead h1{margin:0}.meta{margin:4px 0 0;color:var(--quiet);font-size:14px}
.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent);padding:5px 14px;margin:0 0 2px;font-size:13px}
.heads{list-style:none;margin:14px 0 14px;padding:4px 16px;background:var(--card);border:1px solid var(--line);border-radius:14px}
.hl{padding:10px 0;font-size:15px;display:flex;gap:10px;align-items:center;line-height:1.45}
.hl+.hl{border-top:1px solid #eef0f3}
.hl::before{content:"";width:9px;height:9px;border-radius:50%;flex:none;background:#b8c0c8}
.hl.warm::before{background:var(--above)}.hl.cool::before{background:var(--below)}
.hl.rain::before{background:#3a7bd5}.hl.snow::before{background:#8fb3e8}
.strip{display:flex;gap:8px;overflow-x:auto;scroll-snap-type:x proximity;padding:2px 2px 10px;-webkit-overflow-scrolling:touch}
.dc{flex:1 0 62px;scroll-snap-align:start;background:var(--card);border:1px solid var(--line);border-radius:14px;
padding:9px 2px 10px;text-align:center}
.dc.far{opacity:.5}
.dd{font-size:13px;font-weight:600;line-height:1.3}.dd span{display:block;font-size:11.5px;color:var(--quiet);font-weight:400}
.dc .wx{display:block;margin:5px auto 3px}
.tt{display:flex;justify-content:center;align-items:baseline;gap:2px;font-size:14px;line-height:1.3}.tt i{font-style:normal;color:#c3c9d0;font-size:12px}
.pp .drop{width:8px;height:10px;fill:currentColor;margin-right:2px;vertical-align:-1px;opacity:.75}
.tt,.drow summary,table,.tc,.tile b{font-variant-numeric:tabular-nums}.drow.far summary b{opacity:.8}
b.hi{color:#d0453a}b.lo{color:#2f6fd0}
.pp{font-size:12px;color:var(--quiet);margin-top:3px;min-height:16px}.pp.wet{color:#2563c9;font-weight:600}
.hint{font-size:12px;color:var(--quiet);margin:0 0 20px}
.seg{display:flex;gap:4px;background:#eef1f5;border-radius:11px;padding:4px;margin-bottom:10px}
.seg button{flex:1;font:inherit;font-size:14px;padding:7px 0;border:0;border-radius:8px;background:transparent;
color:var(--quiet);cursor:pointer}
.seg button.on{background:#fff;color:var(--ink);font-weight:600;box-shadow:0 1px 3px rgba(0,0,0,.12)}
.seggroup .note{margin:0 0 6px;font-size:12.5px}
.cbox[hidden],.note[hidden]{display:none}
h3.sec{font-size:17px;margin:30px 0 10px}h3.sec .q{font-size:12.5px;font-weight:400}
.q{color:var(--quiet);font-size:.88em;font-weight:400}
.card.days{padding:0;overflow:hidden}
.dhead,.drow summary{display:grid;grid-template-columns:92px 30px 1fr 52px 14px;align-items:center;gap:6px;padding:10px 16px}
.dhead{font-size:12px;color:var(--quiet);border-bottom:1px solid var(--line);padding-top:8px;padding-bottom:8px}
.dhead span:nth-child(3),.c-t{text-align:center}.dhead span:nth-child(4),.c-p{text-align:right}
.drow{border-bottom:1px solid var(--line)}.drow:last-child{border-bottom:0}
.drow summary{list-style:none;cursor:pointer;font-size:14.5px}.drow summary::-webkit-details-marker{display:none}
.drow summary::after{content:"›";color:#a0a8b0;font-size:19px;line-height:1;justify-self:end;transition:transform .15s}
.drow[open] summary::after{transform:rotate(90deg)}.drow[open] summary{background:#f8fafc}
.drow.far summary{color:var(--quiet)}.c-p{color:#2563c9;font-weight:500}.drow .wx{display:block}
.dmore{display:grid;grid-template-columns:auto 1fr;gap:7px 16px;margin:0;padding:6px 16px 16px;font-size:13.5px;background:#f8fafc}
.dmore dt{color:var(--quiet)}.dmore dd{margin:0}
details.about{margin:30px 0 0;color:var(--quiet);font-size:13px;line-height:1.7}
details.about summary{cursor:pointer;font-weight:600;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin:16px 0 12px}
.chip{padding:7px 14px;border-radius:999px;font-size:15px;font-weight:600;color:var(--c);
background:color-mix(in srgb,var(--c) 12%,white);border:1px solid color-mix(in srgb,var(--c) 30%,white)}
.card.grid4{padding:10px 12px 8px}
table.mgrid{table-layout:fixed}table.mgrid th,table.mgrid td{border:0;padding:4px 3px}
table.mgrid tr:first-child th{font-size:13px;color:var(--ink);font-weight:600}
table.mgrid tr:first-child th span{display:block;font-size:11px;color:var(--quiet);font-weight:400}
table.mgrid th.l{width:76px;font-size:13.5px;color:var(--ink)}
table.mgrid td{background:color-mix(in srgb,var(--c) calc(var(--s)*100%),white);border-radius:8px;
border:3px solid var(--bg);height:54px;line-height:1.25}
table.mgrid td b{display:block;font-size:14px}table.mgrid td span{font-size:12px;opacity:.8}
table.mgrid td.dk{color:#fff}
table.mgrid td.sn{background:#f1f4f8;--c:#fff}table.mgrid td.sn.up{background:#e2ecfb;color:#2357a8}
table.mgrid td.sn b{font-size:14px}
.kc .kchead{margin:2px 4px 8px;font-size:14px}.kc table.mgrid tr.src th{font-size:11.5px;color:var(--quiet);font-weight:500;padding-top:0}
.kc table.mgrid th.l span{display:block;font-size:11px;color:var(--quiet);font-weight:400}
.kc table.mgrid td{height:50px}.kc table.mgrid td:nth-child(3),.kc table.mgrid td:nth-child(5){box-shadow:inset 0 0 0 1.5px rgba(17,24,39,.18)}
.dgrid.st .gcol>.card.kc{flex:none;margin-bottom:14px}
.grid4 .note{margin:6px 4px 2px;font-size:12px}
details.fold{margin:10px 0 0}details.fold>summary{cursor:pointer;font-size:13.5px;color:var(--accent);font-weight:600;
list-style:none;padding:6px 0}details.fold>summary::-webkit-details-marker{display:none}
details.fold>summary::before{content:"＋ ";}details.fold[open]>summary::before{content:"－ ";}
details.fold.narr{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:4px 16px;margin:0 0 8px}
details.fold.narr .foldbody{font-size:14px}.foldbody h2{display:none}
.segpane[hidden]{display:none}
.tiles{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin:16px 0 4px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px}
.tile b{display:block;font-size:24px;line-height:1.2;margin-bottom:2px}.tile span{display:block;font-size:13px;color:var(--quiet);line-height:1.45}
.tile.good b{color:#1f7a4d}.tile.bad b{color:#b3372d}
.card.empty{color:var(--quiet);font-size:14px;text-align:center;justify-content:center;padding:28px 18px}.card.empty b{color:var(--ink);font-size:15px}.card.empty p{margin:6px 0 0}
.seggroup .sel{margin:0 0 6px}
.tcal{display:grid;grid-template-columns:repeat(7,1fr);gap:6px;margin-top:4px}
.tc{border-radius:10px;padding:6px 2px 7px;text-align:center;background:color-mix(in srgb,var(--c) calc(var(--s)*100%),white);
line-height:1.25;min-width:0}
.tc .td{display:block;font-size:12px;font-weight:600;color:var(--ink)}.tc .td i{font-style:normal;font-weight:400;color:var(--quiet);margin-left:2px}
.tc b{display:block;font-size:13px;margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.tc .tp{font-size:11.5px;opacity:.8}
.tc .tb{display:flex;height:4px;border-radius:2px;overflow:hidden;margin:5px 7px 0;box-shadow:0 0 0 1px rgba(255,255,255,.6)}.tc .tb i{display:block;height:100%}
.warn{font-size:12.5px;color:#8a5a00;background:#fff6e0;border-radius:8px;padding:7px 10px;margin:0 0 8px}
.warn.soft{color:#3d5a80;background:#eef4fb}.tc.dk,.tc.dk .td,.tc.dk .td i{color:#fff}
/*METHODS*//* ---- 넓은 화면(PC): 화면을 넓게 쓰고 두 칸 배치. 휴대폰·좁은 창은 위아래 한 줄 그대로 ---- */
@media (max-width:1099px){
.days2 .card.days:first-child{border-bottom:0;border-radius:14px 14px 0 0;margin-bottom:0}
.days2 .card.days:last-child{border-radius:0 0 14px 14px;margin-top:0}
.days2 .card.days:last-child .dhead{display:none}
}
@media (min-width:1100px){
.wrap{max-width:1360px;padding:0 36px}
header .wrap{height:64px}
.dgrid{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(0,1fr);gap:28px;align-items:start}
.dgrid.st{align-items:stretch}.dgrid.st .gcol{display:flex;flex-direction:column}
.dgrid.st .gcol>.card{flex:1;display:flex;flex-direction:column;margin-top:0;margin-bottom:0}
.dgrid.st .segpane:not([hidden]){flex:1;display:flex;flex-direction:column}
.dgrid.st .card.grid4{justify-content:space-between}.dgrid.st .card.grid4 table{flex:1}
.dgrid.m+details.narr{margin-top:16px}
.dgrid.d .tcal{flex:1;grid-auto-rows:1fr;gap:8px;margin-top:8px}
.dgrid.d .tc{display:flex;flex-direction:column;justify-content:center;padding:8px 2px}
.dgrid.d .tc .td{font-size:13px}.dgrid.d .tc b{font-size:15px;margin-top:6px}.dgrid.d .tc .tp{font-size:12.5px;margin-top:2px}
.dgrid.d .tc .tb{height:5px;margin:8px 10px 0}
.dgrid.m{grid-template-columns:minmax(0,1fr) minmax(0,1.1fr)}
.dgrid.eq{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
.gcol>:first-child{margin-top:0}.gcol>.chips:first-child{margin-top:4px}
.dgrid .gcol>h3.sec:first-child{margin-top:24px}
.days2{display:grid;grid-template-columns:1fr 1fr;gap:24px;align-items:start}
.days2 .card.days{margin:0}
.heads{display:grid;grid-template-columns:1fr 1fr;column-gap:36px;padding:4px 20px}
.heads .hl{border-top:1px solid #eef0f3}.heads .hl:nth-child(-n+2){border-top:0}
.strip{overflow:visible;padding-bottom:6px}.dc{flex:1 1 0;min-width:0}
.m-only{display:none}
.cbox{height:340px}.cbox.m{height:250px}
.mgrid2{columns:2;column-gap:20px}.mgrid2 details.mth{break-inside:avoid;display:block}
.tiles{grid-template-columns:repeat(auto-fit,minmax(230px,1fr))}
table.mgrid td{height:58px}
}
@media (max-width:640px){
.wrap{padding:0 14px}
header .wrap{height:auto;flex-wrap:wrap;padding-top:10px;padding-bottom:4px;row-gap:2px}
header a.brand{font-size:17px;white-space:nowrap;order:1}
.rf{order:2;margin-left:auto}header nav{order:3;margin-left:0}
nav{width:100%;display:flex;overflow-x:auto;white-space:nowrap;-webkit-overflow-scrolling:touch}
nav a{margin:0 16px 0 0;padding:6px 0;font-size:14.5px}nav a.on{border-bottom:2px solid var(--accent)}
h1{font-size:22px;margin-top:20px}.sub{font-size:13px}
.card{padding:12px 8px}.card.tbl{padding:4px 4px}
th,td{padding:7px 3px;font-size:13px}th{font-size:12px}
td small{display:block;font-size:10.5px;line-height:1.3}
table.daily td.l{white-space:nowrap;font-size:12.5px}
.cbox{height:240px}.cbox.m{height:220px}
.phead{margin-top:20px}.hl{font-size:14.5px}.heads{padding:2px 14px}.dc{flex-basis:62px}
.dhead,.drow summary{grid-template-columns:74px 26px 1fr 42px 12px;padding:10px 12px}
table.mgrid th.l{width:58px;font-size:12.5px}table.mgrid td{height:50px;border-width:2px}table.mgrid td b{font-size:12.5px}.chip{font-size:14px;padding:6px 12px}.tcal{gap:4px}.tc b{font-size:11px}.tc .td{font-size:11px}.tc .tp{font-size:10.5px}.tiles{grid-template-columns:1fr 1fr;gap:8px}.tile{padding:10px 12px}.tile b{font-size:20px}.tile span{font-size:12px}.seg button{font-size:13px}.dmore{padding:6px 12px 14px}.chartcard{padding:12px 8px 8px;margin-bottom:16px}.btn{margin:0 0 14px;padding:6px 14px;font-size:13px}
}
"""
CSS = CSS.replace("/*METHODS*/", METHODS_CSS)

FONT = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;600;700&display=swap" '
        'rel="stylesheet">')


STATIC = Path(__file__).parent / "static"
ICON_FILES = ("chart.umd.min.js", "daily.js", "month.js", "verify.js", "favicon.svg", "favicon-32.png", "apple-touch-icon.png", "icon-192.png", "icon-512.png",
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
    "description": "4주 일별 예측과 1개월 기상전망",
    "start_url": "./index.html", "scope": "./", "display": "standalone",
    "background_color": "#fafbfc", "theme_color": "#1f6fd1",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        {"src": "favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
    ],
}


_BUILT: str | None = None     # 이번 사이트 생성 시각 (version.json 과 같은 값 → 새로고침 버튼이 비교)


def _page(title: str, body: str, active: str, root: str = "") -> str:
    built = _BUILT or f"{datetime.now():%Y-%m-%d %H:%M}"
    nav = "".join(f'<a href="{root}{href}" class="{"on" if key == active else ""}">{name}</a>'
                  for key, href, name in (("daily", "index.html", "4주 일별"),
                                          ("month", "month.html", "1개월 전망"),
                                          ("archive", "archive.html", "지난 전망"),
                                          ("verify", "verification.html", "정확도")))
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>{FONT}
{ICON_HEAD.format(root=root)}{rights.HEAD_META}
<meta name="kw-built" content="{built}">
<style>{CSS}</style></head><body><header><div class="wrap"><a class="brand" href="{root}index.html">
<img src="{root}favicon.svg" alt="" width="26" height="26">한국 기상전망</a><nav>{nav}</nav>
<button type="button" class="rf" data-root="{root}" aria-label="새 자료 확인" title="새 자료 확인 · {built} 갱신"><svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/></svg><span>새로고침</span></button>
</div></header><main class="wrap">{body}</main>{REGION_JS}{REFRESH_JS}
<footer class="wrap"><p class="cr">{rights.COPYRIGHT}. All rights reserved. 무단 전재·재배포·상업적 이용과
AI 학습·자동 수집을 금지합니다. <a href="{root}terms.html">이용약관</a></p>
<p>{rights.SOURCES} 평년은 1991~2020 · 갱신 {built} ·
<a href="https://github.com/{rights.OWNER}/kwagent/actions/workflows/daily.yml" rel="nofollow">예측 다시 돌리기(관리자용)</a></p></footer></body></html>"""


def _region_tabs(regions) -> str:
    """권역 고르기 버튼 (전국·중부·호남·경상). 고른 권역은 다른 화면에서도 유지(브라우저에 기억)."""
    regions = [r for r in REGION_ORDER if r in set(regions)] + [r for r in regions if r not in REGION_ORDER]
    if len(regions) < 2:
        return ""
    return ("<div class='rtabs' role='tablist'>" + "".join(
        f"<button type='button' role='tab' data-r='{r}'>{REGION_LABELS.get(r, r)}</button>" for r in regions)
        + "</div>")


# 새로고침: 서버의 version.json 과 이 화면의 생성 시각을 비교. 다르면 새로 불러오고(주소에 ?r= 를 붙여 캐시를 피함),
# 같으면 '이미 최신'. 화면을 다시 열 때도 몰래 확인해 새 예측이 있으면 알림. (홈 화면 앱에는 브라우저 새로고침이 없음)
REFRESH_JS = """<script>(function(){var b=document.querySelector('.rf');if(!b)return;
var m=document.querySelector('meta[name="kw-built"]'),built=m?m.content:'',root=b.dataset.root||'';
function go(){location.replace(location.pathname+'?r='+Date.now()+location.hash)}
function toast(h,keep){var e=document.getElementById('kwToast');if(!e){e=document.createElement('div');e.id='kwToast';
e.setAttribute('role','status');document.body.appendChild(e)}e.innerHTML=h;e.className='show';clearTimeout(e._t);
e._t=setTimeout(function(){e.className=''},keep?9000:3500);var x=e.querySelector('button');if(x)x.onclick=go}
function check(manual){return fetch(root+'version.json?t='+Date.now(),{cache:'no-store'}).then(function(r){return r.json()})
.then(function(v){if(v.built&&v.built!==built){if(manual){toast('새 자료를 불러옵니다…');setTimeout(go,350)}
else toast('새 예측이 나왔습니다 <button type="button">불러오기</button>',true)}
else if(manual)toast('이미 최신입니다 · '+built+' 갱신')})
.catch(function(){if(manual){toast('화면을 다시 불러옵니다…');setTimeout(go,350)}})}
b.addEventListener('click',function(){b.classList.add('spin');check(true).then(function(){setTimeout(function(){b.classList.remove('spin')},500)})});
setTimeout(function(){check(false)},1500);
document.addEventListener('visibilitychange',function(){if(!document.hidden)check(false)})})();</script>"""

REGION_JS = """<script>document.querySelectorAll('.seggroup').forEach(function(g){var bs=g.querySelectorAll('.seg button');
bs.forEach(function(b){b.addEventListener('click',function(){bs.forEach(function(x){x.classList.toggle('on',x===b)});
g.querySelectorAll(':scope>[data-k]').forEach(function(el){el.hidden=el.dataset.k!==b.dataset.k})})})});
(function(){var b=document.querySelectorAll('.rtabs button');if(!b.length)return;
var s=document.querySelectorAll('.rsec');function pick(r){var ok=false;b.forEach(function(x){if(x.dataset.r===r)ok=true});
if(!ok)r=b[0].dataset.r;b.forEach(function(x){x.classList.toggle('on',x.dataset.r===r);x.setAttribute('aria-selected',x.dataset.r===r)});
s.forEach(function(x){x.hidden=x.dataset.region!==r});try{localStorage.setItem('kw-region',r)}catch(e){}}
b.forEach(function(x){x.addEventListener('click',function(){pick(x.dataset.r);history.replaceState(null,'','#'+x.dataset.r)})});
var r=location.hash.slice(1);if(!r){try{r=localStorage.getItem('kw-region')}catch(e){}}pick(r||'korea')})();</script>"""


def _split_narrative(md: str, regions) -> dict | None:
    """해설을 권역별로 나눔 ('**전국**' 같은 줄 기준). 모든 권역 제목을 못 찾으면 None (통째로 표시)."""
    if not md or len(regions) < 2:
        return None
    lines = md.splitlines()
    title = next((ln for ln in lines if ln.startswith("#")), "## 해설")
    marks = {}
    for i, ln in enumerate(lines):
        for r in regions:
            if ln.strip() in (f"**{REGION_LABELS.get(r, r)}**", f"### {REGION_LABELS.get(r, r)}"):
                marks[r] = i
    if set(marks) != set(regions):
        return None
    starts = sorted(marks.values()) + [len(lines)]
    return {r: "\n".join([title] + lines[i + 1:starts[starts.index(i) + 1]]).strip() for r, i in marks.items()}


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


def _seg_card(tabs: list[tuple[str, str, str, str]]) -> str:
    """버튼으로 골라 보는 카드. tabs = [(키, 버튼 이름, 설명, 내용 html)]."""
    seg = "".join(f"<button type='button' data-k='{k}'{' class=on' if i == 0 else ''}>{name}</button>"
                  for i, (k, name, _, _) in enumerate(tabs))
    body = "".join(f"<div class='segpane' data-k='{k}'{'' if i == 0 else ' hidden'}>"
                   f"{f'<p class=note>{desc}</p>' if desc else ''}{html_}</div>"
                   for i, (k, _, desc, html_) in enumerate(tabs))
    return f"<div class='card chartcard seggroup'><div class='seg' role='tablist'>{seg}</div>{body}</div>"


def _fold(title: str, html_: str, cls: str = "") -> str:
    return f"<details class='fold {cls}'><summary>{title}</summary><div class='foldbody'>{html_}</div></details>"


def forecast_body(result: dict, img_prefix: str) -> str:
    from .ui import month_cell, month_chips
    issue = result["issue"]
    ix = result.get("indices", {})
    regions = list(result["regions"])
    root = img_prefix[:-len("img/")]
    first = next(iter(result["regions"].values()))["weeks"]
    span = f"{first[0]['start'][5:].replace('-', '.')}~{first[-1]['end'][5:].replace('-', '.')}"
    _, mo, dd = issue.split("-")
    parts = [f"<div class='phead'><div><h1>1개월 전망</h1><p class='meta'>{int(mo)}월 {int(dd)}일 발표 · "
             f"{span} (4주)</p></div><a class='btn ghost' href='{root}forecast_{issue}.xlsx' download>엑셀</a></div>"]
    parts.append(_region_tabs(regions))
    narr = _split_narrative(result.get("narrative") or "", regions)
    for region in regions:
        rd = result["regions"][region]
        vs = result_vars(rd)
        parts.append(f"<section class='rsec' data-region='{region}'>")
        # 1) 한눈에: 4주 경향 낱말 + 4주 × 변수 색깔표  (PC: 왼쪽 칸, 그래프는 오른쪽 칸)
        chips = month_chips(rd, vs)
        parts.append("<div class='chips'>" + "".join(
            f"<span class='chip' style='--c:{c}'>{w}</span>" for _, c, w in chips) + "</div>")
        bsrc = rd.get("bias") or {}          # 기록이 없는 옛 전망은 보정 전
        if rd.get("dynamical_sources"):
            raw_vars = [VAR_LABEL[v][0] for v in vs if v != "temp" and v not in bsrc]
            if raw_vars:
                parts.append(f"<p class='warn'>보정 전: {'·'.join(raw_vars)}은(는) 모델 버릇 때문에 비·구름 '많음' 쪽으로 "
                             "기울 수 있습니다 · 약 3주 뒤부터 자동 보정</p>")
        # PC: 색깔표(왼쪽)와 주별 확률 그래프(오른쪽)를 같은 높이로 나란히
        parts.append("<div class='dgrid m st'><div class='gcol'><h3 class='sec first'>4주 한눈에 "
                     "<span class='q'>· 칸 색이 진할수록 확률이 높음</span></h3>")
        head = "".join(f"<th>{wk['label'].split(' ')[0]}<span>{wk['start'][5:].replace('-', '.')}~</span></th>"
                       for wk in rd["weeks"])
        rows = []
        for v in vs:
            cats = tuple(VAR_LABEL[v][1:4])
            cells = []
            for wk in rd["weeks"]:
                d = wk["vars"][v]
                word, col, s = month_cell(d["display"], v, cats)
                pct = max(d["display"])
                dark = s >= 0.8
                cells.append(f"<td style='--c:{col};--s:{0.18 + 0.72 * s:.2f}' class='{'dk' if dark else ''}' "
                             f"title='{_verdict(d['display'], v)} ({'/'.join(str(x) for x in d['display'])}%)'>"
                             f"<b>{word}</b><span>{pct}%</span></td>")
            rows.append(f"<tr><th class='l'>{VAR_LABEL[v][0]}</th>{''.join(cells)}</tr>")
        snow = "".join(
            f"<td class='sn{' up' if wk['ptype']['p_snow'] > wk['ptype']['climatology']['p_snow'] + 0.05 else ''}'>"
            f"<b>{wk['ptype']['p_snow']*100:.0f}%</b><span>평년 {wk['ptype']['climatology']['p_snow']*100:.0f}%</span></td>"
            for wk in rd["weeks"])
        rows.append(f"<tr><th class='l'>눈 올 확률</th>{snow}</tr>")
        parts.append(f"<div class='card grid4'><table class='mgrid'><tr><th></th>{head}</tr>{''.join(rows)}</table>"
                     "<p class='note'>숫자는 가장 큰 쪽 확률 · 눈은 하루라도 올 확률</p></div>")
        narr_html = ""
        if narr and narr.get(region):
            narr_html = _fold("자동 해설 전문", md_to_html(narr[region]), "narr")
        elif narr is None and result.get("narrative") and region == regions[0]:
            narr_html = _fold("자동 해설 전문", md_to_html(result["narrative"]), "narr")
        # 2) 그래프: 변수 버튼 + 표 접기
        tabs = []
        for v in vs:
            name, lo, mid, hi, unit = VAR_LABEL[v]
            trs = []
            for wk in rd["weeks"]:
                d = wk["vars"][v]
                a, b = d["normal_range"]
                trs.append(f"<tr><td class='l'>{wk['label'].split(' ')[0]}</td><td>{a}~{b}</td>"
                           f"{_prob_cells(d['display'], v)}<td class='verdict l'>{_verdict(d['display'], v)}</td></tr>")
            table = (f"<table class='mt'><tr><th class='l'>주</th><th>평년 범위<span class='u'>{unit}</span></th>"
                     f"<th>{lo}</th><th>{mid}</th><th>{hi}</th><th class='l'>전망</th></tr>{''.join(trs)}</table>")
            tabs.append((v, name, MONTH_DESC.get(v, ""),
                         f"<div class='cbox m'><canvas id='m-{region}-{v}' aria-label='{name} 확률'></canvas></div>"
                         + _fold("표로 보기", table)))
        trs = "".join(
            f"<tr><td class='l'>{wk['label'].split(' ')[0]}</td><td>{wk['ptype']['rain_days']:.1f}</td>"
            f"<td>{wk['ptype']['snow_days']:.1f}</td><td>{wk['ptype']['p_snow']*100:.0f}%</td>"
            f"<td>{wk['ptype']['climatology']['p_snow']*100:.0f}%</td></tr>" for wk in rd["weeks"])
        tabs.append(("ptype", "비·눈", "막대는 주별 비·눈 오는 날 수, 선은 눈이 하루라도 올 확률",
                     f"<div class='cbox m'><canvas id='m-{region}-ptype' aria-label='강수형태'></canvas></div>"
                     + _fold("표로 보기", "<table class='mt'><tr><th class='l'>주</th><th>비 오는 날</th><th>눈 오는 날</th>"
                                       f"<th>눈 확률</th><th>평년 눈 확률</th></tr>{trs}</table>")))
        parts.append("</div><div class='gcol'><h3 class='sec first'>주별 확률 <span class='q'>· 막대를 누르면 평년 범위와 모델별 확률</span></h3>")
        parts.append(_seg_card(tabs) + "</div></div>" + narr_html)
        parts.append(f'<noscript><img class="chart" alt="{REGION_LABELS.get(region, region)} 확률" '
                     f'src="{img_prefix}forecast_{issue}_{region}.png"></noscript></section>')
    srcs = sorted({s for rd in result["regions"].values() for s in rd.get("dynamical_sources", [])})
    src = ", ".join(SOURCE_LABEL.get(s, s) for s in srcs) or "없음(통계모델만)"
    ixs = ("Niño3.4 {nino34:+.2f}, AO(7일) {ao:+.2f}, MJO RMM1/RMM2 {rmm1:+.2f}/{rmm2:+.2f}".format(**ix)) if ix else "-"
    parts.append(f"<p class='note'>이번 발표에 쓴 역학모델: {src} · 발표 시점 기후지수: {ixs}</p>" + methods_block("month"))
    data = {"regions": {}}
    for region in regions:
        rd = result["regions"][region]
        vs = result_vars(rd)
        data["regions"][region] = {
            "vars": [{"key": v, "cats": list(VAR_LABEL[v][1:4]), "unit": VAR_LABEL[v][4]} for v in vs],
            "weeks": [{"name": wk["label"].split(" ")[0],
                       "range": wk["label"].split(" ", 1)[1].strip("()") if " " in wk["label"] else "",
                       "ptype": {"rain_days": wk["ptype"]["rain_days"], "snow_days": wk["ptype"]["snow_days"],
                                 "p_snow": wk["ptype"]["p_snow"], "clim": wk["ptype"]["climatology"]},
                       "vars": {v: {"display": wk["vars"][v]["display"], "normal": wk["vars"][v]["normal_range"],
                                    "center": wk["vars"][v].get("ens_mean_corrected"),
                                    "sources": wk["vars"][v].get("sources"), "weights": wk["vars"][v].get("weights"),
                                    "verdict": _verdict(wk["vars"][v]["display"], v)} for v in vs}}
                      for wk in rd["weeks"]]}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    parts.append(f'<script id="mdata" type="application/json">{blob}</script>'
                 f'<script src="{root}chart.umd.min.js"></script><script src="{root}month.js"></script>')
    return "".join(parts)


MONTH_DESC = {
    "temp": "주평균 기온이 평년보다 낮을·비슷할·높을 확률",
    "cloud": "주평균 운량(하늘을 덮은 구름 비율)이 적을·비슷할·많을 확률",
    "srad": "주평균 일사량(땅에 닿는 햇빛)이 적을·비슷할·많을 확률",
    "precip": "한 주 강수량 합계가 적을·비슷할·많을 확률",
}


TREND_DESC = {"temp": "쌀쌀할·비슷할·따뜻할", "precip": "건조할·비슷할·비가 많을",
              "cloud": "구름이 적을·비슷할·많을", "srad": "햇빛이 적을·비슷할·많을"}

DAILY_CHARTS = (
    ("temp", "기온", "°C · 선은 예측, 띠는 10~90% 범위, 점선은 평년"),
    ("precip", "강수", "막대 강수량(mm, 연한 색은 많으면) · 선 강수확률(%)"),
    ("cloud", "구름", "운량 % · 55% 미만 맑음, 85% 이상 흐림"),
    ("srad", "일사량", "MJ/m² · 하루 동안 땅에 닿는 햇빛 에너지"),
)


_DROP = ('<svg class="drop" viewBox="0 0 10 12" aria-hidden="true">'
         '<path d="M5 0C5 0 0 6 0 8.2A5 5 0 0 0 10 8.2C10 6 5 0 5 0Z"/></svg>')


def daily_body(result: dict, img_prefix: str) -> str:
    from .daily import MODEL_LABEL, num, sky_label
    from .ui import CAT_COLORS, WX_LABEL, daily_headlines, trend_cell, wx_icon, wx_kind
    issue = result["issue"]
    y, m, d = issue.split("-")
    models = ", ".join(f"{MODEL_LABEL.get(k, k)}({v}멤버)" for k, v in result["models"].items()) or "없음"
    ndays = max((len(rd["days"]) for rd in result["regions"].values()), default=14)
    title = "4주 일별 예측" if ndays > 14 else "2주 일별 예측"
    parts = [f"<div class='phead'><div><h1>{title}</h1><p class='meta'>{int(m)}월 {int(d)}일 발표 · 내일부터 {ndays}일"
             f"{' · 15일째부터는 경향' if ndays > 14 else ''}</p></div>"
             f"<a class='btn ghost' href='daily_{issue}.xlsx' download>엑셀</a></div>"]
    regions = list(result["regions"])
    parts.append(_region_tabs(regions))

    def rng(v, unit="", dig=0):
        if not v:
            return "-"
        f = (lambda x: num(x)) if dig == 0 else (lambda x: f"{x:.{dig}f}")
        s = f"{f(v['q50'])}{unit} <span class='q'>({f(v['q10'])}~{f(v['q90'])})</span>"
        if v.get("normal") is not None:
            s += f" <span class='q'>· 평년 {f(v['normal'])}{unit}</span>"
        return s

    def tcls(v):
        if not v or v.get("normal") is None:
            return ""
        an = v["q50"] - v["normal"]
        return " warm" if an >= 2 else (" cool" if an <= -2 else "")

    for region in regions:
        alldays = result["regions"][region]["days"]
        days = [x for x in alldays if "trend" not in x]           # 1~14일: 날짜별 값
        tdays = [x for x in alldays if "trend" in x]              # 15~28일: 경향
        parts.append(f"<section class='rsec' data-region='{region}'>")
        # 1) 한눈에: 핵심 문장 + 14일 카드 줄
        parts.append("<ul class='heads'>" + "".join(f"<li class='hl {k}'>{s}</li>" for k, s in daily_headlines(alldays))
                     + "</ul>")
        cards = []
        prev_month = None
        for day in days:
            v = day["vars"]
            mo, dd = day["date"][5:7], day["date"][8:10]
            top = f"{int(mo)}.{int(dd)}" if prev_month != mo else str(int(dd))
            prev_month = mo
            pop = (v.get("precip") or {}).get("pop")
            k = wx_kind(day)
            cards.append(
                f"<div class='dc{' far' if day['lead'] >= 8 else ''}' title='{day['label']} {WX_LABEL[k]}'>"
                f"<div class='dd'>{top}<span>{day['label'][-2]}</span></div>{wx_icon(k)}"
                f"<div class='tt'><b class='lo'>{num(v['tmin']['q50'])}°</b><i>/</i>"
                f"<b class='hi'>{num(v['tmax']['q50'])}°</b></div>"
                f"<div class='pp{' wet' if pop and pop >= 0.4 else ''}'>{'' if pop is None else _DROP + f'{pop*100:.0f}%'}</div></div>")
        parts.append("<div class='strip' role='list' aria-label='14일 요약'>" + "".join(cards) + "</div>"
                     "<p class='hint'><span class='m-only'>옆으로 넘겨 보세요 · </span>흐린 칸(8일 이후)은 참고용</p>")
        # 2) 그래프: 버튼으로 골라 보기
        seg = "".join(f"<button type='button' data-k='{kind}'{' class=on' if i == 0 else ''}>{title}</button>"
                      for i, (kind, title, _) in enumerate(DAILY_CHARTS))
        boxes = "".join(f"<div class='cbox' data-k='{kind}'{'' if i == 0 else ' hidden'}>"
                        f"<canvas id='c-{region}-{kind}' aria-label='{title}'></canvas></div>"
                        for i, (kind, title, _) in enumerate(DAILY_CHARTS))
        notes = "".join(f"<p class='note' data-k='{kind}'{'' if i == 0 else ' hidden'}>{desc}</p>"
                        for i, (kind, _, desc) in enumerate(DAILY_CHARTS))
        chart_html = (f"<h3 class='sec'>날씨 흐름 <span class='q'>· {len(alldays)}일</span></h3>"
                      f"<div class='card chartcard seggroup'><div class='seg' role='tablist'>{seg}</div>{notes}{boxes}</div>")
        trend_html = ""
        if tdays:
            tabs = []
            for var, name in (("temp", "기온"), ("precip", "강수"), ("cloud", "구름"), ("srad", "일사량")):
                cells = []
                for i, x in enumerate(tdays):
                    word, col, s, pct = trend_cell(x["trend"].get(var), var)
                    dd = x["date"]
                    top = f"{int(dd[5:7])}.{int(dd[8:10])}" if i == 0 or dd[8:10] == "01" else str(int(dd[8:10]))
                    tr = x["trend"].get(var) or {}
                    tip = (f"{x['label']} · 낮음 {tr['p'][0]*100:.0f}% / 비슷 {tr['p'][1]*100:.0f}% / 높음 {tr['p'][2]*100:.0f}%"
                           if tr else x["label"])
                    cells.append(f"<div class='tc{' dk' if s >= 0.75 else ''}' style='--c:{col};--s:{0.12 + 0.78 * s:.2f}' "
                                 f"title='{tip}'><span class='td'>{top}<i>{x['label'][-2]}</i></span>"
                                 f"<b>{word}</b><span class='tp'>{pct or '&nbsp;'}</span>"
                                 + ("<span class='tb'>" + "".join(f"<i style='width:{q*100:.0f}%;background:{c}'></i>" for q, c in zip(tr['p'], CAT_COLORS.get(var, CAT_COLORS['temp']))) + "</span>" if tr else "") + "</div>")
                cals = {(x["trend"].get(var) or {}).get("cal") for x in tdays}
                warn = ""
                if var != "temp" and not (cals & {"own", "proxy"}):
                    warn = ("<p class='warn'>보정 전: 장기 모델은 비·구름을 평년보다 많게 예측하는 버릇이 있어 '많음' 쪽으로 "
                            "기울어 보일 수 있습니다. 채점이 쌓이면(약 3주 뒤부터) 자동으로 바로잡습니다.</p>")
                elif "own" not in cals and "proxy" in cals:
                    warn = "<p class='warn soft'>임시 보정: 2주 무렵 채점에서 구한 모델 치우침을 적용했습니다.</p>"
                tabs.append((var, name, f"그날 앞뒤 5일 평균이 평년보다 {TREND_DESC[var]} 가능성 · "
                                        "진한 색 = 확률 높음 · 막대 = 세 경우의 확률 · '–' = 뚜렷한 쪽 없음", warn + "<div class='tcal'>" + "".join(cells) + "</div>"))
            span = f"{tdays[0]['label'].split('(')[0]}~{tdays[-1]['label'].split('(')[0]}"
            trend_html = (f"<h3 class='sec'>3~4주 뒤 경향 <span class='q'>· {span} · 평년보다 어느 쪽일지</span></h3>"
                          + _seg_card(tabs))
        # PC 에서는 그래프(왼쪽 넓게)와 3~4주 경향(오른쪽)을 나란히, 휴대폰은 위아래로
        parts.append(f"<div class='dgrid d st'><div class='gcol'>{chart_html}</div>"
                     + (f"<div class='gcol'>{trend_html}</div>" if trend_html else "") + "</div>")
        parts.append(f'<noscript><img class="chart" alt="{REGION_LABELS.get(region, region)} 일별 예측" '
                     f'src="{img_prefix}daily_{issue}_{region}.png"></noscript>')
        # 3) 날짜별 자세히: 누르면 펼침
        rows = []
        for day in days:
            v = day["vars"]
            p = v.get("precip") or {}
            k = wx_kind(day)
            sky = (v.get("cloud") or {}).get("sky") or {}
            snow = "-" if p.get("p_snow") is None else f"{p['p_snow']*100:.0f}%"
            pn = "" if p.get("pop_normal") is None else f" <span class='q'>· 평년 {p['pop_normal']*100:.0f}%</span>"
            amt = "-" if not p else f"{p['q50']:.1f}mm <span class='q'>(많으면 {p['q90']:.0f}mm)</span>"
            popt = "" if p.get("pop") is None else f"{p['pop'] * 100:.0f}%"
            rows.append(
                f"<details class='drow{' far' if day['lead'] >= 8 else ''}'><summary>"
                f"<span class='c-d'>{day['label']}</span>{wx_icon(k, 26)}"
                f"<span class='c-t'><b class='lo'>{num(v['tmin']['q50'])}°</b> / "
                f"<b class='hi'>{num(v['tmax']['q50'])}°</b></span>"
                f"<span class='c-p'>{popt}</span></summary>"
                "<dl class='dmore'>"
                f"<dt>하늘</dt><dd>{sky_label(v.get('cloud'))} <span class='q'>("
                + " · ".join(f"{kk} {vv*100:.0f}%" for kk, vv in sky.items()) + ")</span></dd>"
                f"<dt>최고기온</dt><dd>{rng(v.get('tmax'), '°C')}</dd>"
                f"<dt>최저기온</dt><dd>{rng(v.get('tmin'), '°C')}</dd>"
                f"<dt>강수확률</dt><dd>{popt or '-'}{pn}</dd>"
                f"<dt>강수량</dt><dd>{amt}</dd><dt>눈 확률</dt><dd>{snow}</dd>"
                f"<dt>운량</dt><dd>{rng(v.get('cloud'), '%')}</dd>"
                f"<dt>일사량</dt><dd>{rng(v.get('srad'), ' MJ/m²', 1)}</dd></dl></details>")
        head = ("<div class='dhead'><span>날짜</span><span></span><span>최저 / 최고</span>"
                "<span>강수확률</span><span></span></div>")
        half = (len(rows) + 1) // 2     # PC 에서는 1주째·2주째를 나란히 두 칸으로
        parts.append("<h3 class='sec'>날짜별 자세히 <span class='q'>· 날짜를 누르면 범위와 평년이 펼쳐집니다</span></h3>"
                     f"<div class='days2'><div class='card days'>{head}{''.join(rows[:half])}</div>"
                     f"<div class='card days'>{head}{''.join(rows[half:])}</div></div></section>")
    parts.append(f"<p class='note'>이번 발표에 쓴 모델: {models}</p>" + methods_block("daily"))
    data = {"regions": {r: {"label": REGION_LABELS.get(r, r), "days": result["regions"][r]["days"]}
                        for r in regions}}
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    parts.append(f'<script id="ddata" type="application/json">{blob}</script>'
                 '<script src="chart.umd.min.js"></script><script src="daily.js"></script>')
    return "".join(parts)


def _order(regions) -> list[str]:
    regions = list(dict.fromkeys(regions))
    return [r for r in REGION_ORDER if r in regions] + [r for r in regions if r not in REGION_ORDER]


def _pct_word(x: float) -> str:
    """평년 대비 개선(0.41) → '평년보다 41% 정확'."""
    return f"평년보다 {abs(x)*100:.0f}% {'정확' if x >= 0 else '부정확'}"


def _tile(value: str, label: str, good: bool | None) -> str:
    cls = "" if good is None else (" good" if good else " bad")
    return f"<div class='tile{cls}'><b>{value}</b><span>{label}</span></div>"


def daily_verification_parts(store):
    """2주 일별 성적: 권역별 (요약 타일들, 본문 html), 그래프 자료."""
    from .daily import DLABEL, LEAD_BINS, MODEL_LABEL, summary
    s = summary(store)
    if s.empty:
        return {}, None
    bins = [b for _, _, b in LEAD_BINS]
    _num = lambda x: None if pd.isna(x) else round(float(x), 3)  # noqa: E731
    vdata = {"bins": bins, "regions": {}}
    out = {}
    for region in _order(s["region"]):
        c = s[(s["region"] == region) & (s["source"] == "combined")]
        rv = vdata["regions"][region] = {"vars": [], "models": {}}
        for var in DLABEL:
            sub = c[c["var"] == var].set_index("bin")
            if sub.empty:
                continue
            rv["vars"].append({"key": var, "name": DLABEL[var][0], "unit": DLABEL[var][1],
                               "bins": {b: {k: _num(sub.at[b, k]) for k in ("mae", "mae_clim", "skill", "cover",
                                                                           "bias", "bss")} | {"n": int(sub.at[b, "n"])}
                                        for b in bins if b in sub.index}})
            m = s[(s["region"] == region) & (s["var"] == var)]
            rv["models"][var] = {src: {r.bin: {"mae": _num(r.mae), "bias": _num(r.bias), "n": int(r.n)}
                                       for r in g.itertuples()} for src, g in m.groupby("source")}
        tiles = []
        ci = c.set_index(["var", "bin"])
        for var, b in (("tmax", bins[0]), ("tmin", bins[0]), ("tmax", bins[-1])):
            if (var, b) in ci.index and not pd.isna(ci.at[(var, b), "skill"]):
                sk = ci.at[(var, b), "skill"]
                tiles.append(_tile(f"{sk*100:+.0f}%", f"{DLABEL[var][0]} · {b}<br>평년값보다 {'정확' if sk > 0 else '부정확'}", sk > 0))
        if ("precip", bins[0]) in ci.index and not pd.isna(ci.at[("precip", bins[0]), "bss"]):
            bs = ci.at[("precip", bins[0]), "bss"]
            tiles.append(_tile(f"{bs*100:+.0f}%", f"강수확률 · {bins[0]}<br>평년값보다 {'정확' if bs > 0 else '부정확'}", bs > 0))
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
        t1 = ("<table class='mt'><tr><th class='l'>변수</th>" + "".join(f"<th>{b}</th>" for b in bins) + "</tr>"
              + "".join(rows) + "</table><p class='note'>평균 오차와 평년 대비 개선(색 숫자) · 적중 = 10~90% 범위에 든 비율(80%가 이상적)</p>")
        pc = c[c["var"] == "precip"].set_index("bin")
        if not pc.empty and pc["brier"].notna().any():
            cells = "".join("<td>-</td>" if b not in pc.index or pd.isna(pc.at[b, "brier"]) else
                            f"<td>{pc.at[b, 'brier']:.3f}" + ("" if pd.isna(pc.at[b, "bss"]) else
                                                              f" <span class='{'pos' if pc.at[b, 'bss'] > 0 else 'neg'}'>"
                                                              f"{pc.at[b, 'bss']:+.2f}</span>") + "</td>" for b in bins)
            t1 += ("<table class='mt'><tr><th class='l'>강수확률 Brier</th>" + "".join(f"<th>{b}</th>" for b in bins)
                   + f"</tr><tr><td class='l'>최종(결합)</td>{cells}</tr></table>")
        # 모델별 오차 표: 변수마다 하나씩, 위 선택 상자(그래프와 같은 변수)에 맞춰 바뀜
        t2s = []
        for i, vv in enumerate(rv["vars"]):
            var, (vname, unit) = vv["key"], DLABEL[vv["key"]][:2]
            m = s[(s["region"] == region) & (s["var"] == var)]
            if m.empty:
                continue
            piv = m.pivot_table(index="source", columns="bin", values="mae")
            order = [x for x in ("combined",) if x in piv.index] + [x for x in piv.index if x != "combined"]
            t2s.append(f"<table class='mt' data-v='{var}'{'' if i == 0 else ' hidden'}><tr><th class='l'>{vname} 오차({unit})</th>"
                       + "".join(f"<th>{b}</th>" for b in bins) + "</tr>" + "".join(
                           f"<tr><td class='l'>{MODEL_LABEL.get(src, src)}</td>" + "".join(
                               "<td>-</td>" if b not in piv.columns or pd.isna(piv.at[src, b]) else f"<td>{piv.at[src, b]:.2f}</td>"
                               for b in bins) + "</tr>" for src in order) + "</table>")
        t2 = f"<div id='v-daily-tabs-{region}'>{''.join(t2s)}</div>" if t2s else ""
        opts = "".join(f"<option value='{v['key']}'>{v['name']}</option>" for v in rv["vars"])
        card = _seg_card([
            ("skill", "평년 대비 개선", "막대가 0보다 높을수록 '평년값으로 찍기'보다 정확 · 진한 색일수록 가까운 날",
             f"<div class='cbox'><canvas id='v-daily-skill-{region}' aria-label='평년 대비 개선'></canvas></div>"
             + _fold("표로 보기", t1)),
            ("models", "모델별 오차", "어느 모델이 잘 맞는지 (막대가 낮을수록 정확)",
             f"<select id='v-daily-var-{region}' class='sel' aria-label='변수'>{opts}</select>"
             f"<div class='cbox'><canvas id='v-daily-models-{region}' aria-label='모델별 평균 오차'></canvas></div>"
             + (_fold("표로 보기", t2) if t2 else "")),
        ])
        out[region] = (tiles, card)
    return out, vdata


def month_verification_parts(store, img_dir: Path):
    """1개월 성적: 권역별 (요약 타일들, 본문 html), 그래프 자료."""
    summ = store.summary()
    if summ.empty:
        return {}, None
    summ = summ[summ["source"] != "blend_raw"]
    _plot_verification(summ, img_dir / "verification.png")
    snow = store.df("SELECT region, lead, p_snow, obs_snow FROM ptype_verification WHERE source='combined'")
    if not snow.empty:
        snow["bs"] = (snow["p_snow"] - snow["obs_snow"]) ** 2
        snow = snow.groupby(["region", "lead"])["bs"].agg(["mean", "size"]).reset_index()
    mdata = {"regions": {}}
    out = {}
    for region in _order(summ["region"]):
        mdata["regions"][region] = {"vars": []}
        tiles, tabs = [], []
        for v in VARS:
            sub = summ[(summ["region"] == region) & (summ["var"] == v)]
            if sub.empty:
                continue
            mdata["regions"][region]["vars"].append({"key": v, "name": VAR_LABEL[v][0], "sources": {
                s: [{"lead": int(r.lead), "rpss": float(r.rpss), "n": int(r.n)} for r in g.sort_values("lead").itertuples()]
                for s, g in sub.groupby("source")}})
            comb = sub[sub["source"] == "combined"]
            if not comb.empty:
                x = float(comb["rpss"].mean())
                tiles.append(_tile(f"{x:+.2f}", f"1개월 {VAR_LABEL[v][0]} · RPSS<br>{'평년 예보보다 나음' if x > 0 else '평년 예보보다 못함'}", x > 0))
                kma = sub[sub["source"] == "kma"]
                if not kma.empty:   # 같은 주차끼리 비교
                    both = comb.merge(kma, on="lead", suffixes=("", "_k"))
                    if not both.empty:
                        d = float((both["rpss"] - both["rpss_k"]).mean())
                        tiles.append(_tile(f"{d:+.2f}", f"1개월 {VAR_LABEL[v][0]} · 기상청 대비<br>"
                                                         f"{'이 사이트가 더 정확' if d > 0 else '기상청이 더 정확'}", d > 0))
            piv = sub.pivot_table(index="source", columns="lead", values="rpss")
            cnt = sub.groupby("source")["n"].max()
            rows = []
            for s_ in ["combined", "kma", "statistical", "ec46", "gefs"]:
                if s_ not in piv.index:
                    continue
                cells = "".join("<td>-</td>" if pd.isna(x) else
                                f"<td class='{'pos' if x > 0 else 'neg'}'>{x:+.2f}</td>" for x in piv.loc[s_])
                rows.append(f"<tr><td class='l'>{SOURCE_LABEL.get(s_, s_)}</td>{cells}<td>{int(cnt.get(s_, 0))}</td></tr>")
            table = (f"<table class='mt'><tr><th class='l'>예측원</th>{''.join(f'<th>{c}주</th>' for c in piv.columns)}"
                     f"<th>채점 수</th></tr>{''.join(rows)}</table>")
            tabs.append((v, VAR_LABEL[v][0], "몇 주 앞 예측인지(가로)에 따른 정확도 · 선이 0보다 위면 평년보다 나음",
                         f"<div class='cbox m'><canvas id='v-{region}-{v}' aria-label='{VAR_LABEL[v][0]} RPSS'></canvas></div>"
                         + _fold("표로 보기", table)))
        sn = snow[snow["region"] == region] if not snow.empty else snow
        if not sn.empty:
            rows = "".join(f"<tr><td class='l'>{r.lead}주</td><td>{r.mean:.3f}</td><td>{r.size}</td></tr>"
                           for r in sn.itertuples())
            tabs.append(("snow", "눈", "눈 올 확률의 Brier 점수 (0이 완벽, 작을수록 정확)",
                         "<table class='mt'><tr><th class='l'>몇 주 앞</th><th>Brier</th><th>채점 수</th></tr>"
                         f"{rows}</table>"))
        out[region] = (tiles, _seg_card(tabs) if tabs else "")
    return out, mdata


def kma_compare_parts(store) -> dict:
    """기상청 1개월전망과 같은 발표일의 이 사이트 전망을 나란히: {권역: html}. 채점 전에도 보여 준다."""
    from .models.combine import to_display
    from .ui import month_cell
    df = store.df("SELECT issue, region, source, var, lead, start, p0, p1, p2 FROM forecasts "
                  "WHERE source IN ('kma', 'combined') AND var IN ('temp', 'precip')")
    if df.empty:
        return {}
    both = sorted(set(df.loc[df["source"] == "kma", "issue"]) & set(df.loc[df["source"] == "combined", "issue"]))
    if not both:
        return {}
    issue = both[-1]
    d = df[df["issue"] == issue]
    out = {}
    has = d.groupby("region")["source"].nunique()
    for region in _order(has[has == 2].index):        # 둘 다 있는 권역만
        r = d[d["region"] == region]
        leads = sorted(r["lead"].unique())
        rows, same, total = [], 0, 0
        for lead in leads:
            st = r.loc[r["lead"] == lead, "start"].iloc[0]
            cells = []
            for v in ("temp", "precip"):
                tops = []
                for src in ("combined", "kma"):
                    x = r[(r["lead"] == lead) & (r["var"] == v) & (r["source"] == src)]
                    if x.empty:
                        cells.append("<td>-</td>")
                        tops.append(None)
                        continue
                    disp = to_display(x[["p0", "p1", "p2"]].to_numpy()[0])
                    word, col, sv = month_cell(disp, v, tuple(VAR_LABEL[v][1:4]))
                    cells.append(f"<td style='--c:{col};--s:{0.18 + 0.72 * sv:.2f}' class='{'dk' if sv >= 0.8 else ''}' "
                                 f"title='낮음·비슷·높음 {disp[0]}/{disp[1]}/{disp[2]}%'><b>{word}</b>"
                                 f"<span>{disp[0]}·{disp[1]}·{disp[2]}</span></td>")
                    tops.append(word)
                if None not in tops:
                    total += 1
                    same += tops[0] == tops[1]
            rows.append(f"<tr><th class='l'>{lead}주<span>{st[5:].replace('-', '.')}~</span></th>{''.join(cells)}</tr>")
        head = ("<tr><th></th><th colspan='2'>기온</th><th colspan='2'>강수량</th></tr>"
                "<tr class='src'><th></th><th>이 사이트</th><th>기상청</th><th>이 사이트</th><th>기상청</th></tr>")
        lead_txt = f"{issue[5:7].lstrip('0')}월 {issue[8:].lstrip('0')}일 발표"
        out[region] = (f"<div class='card grid4 kc'><p class='kchead'><b>기상청과 나란히</b> <span class='q'>· {lead_txt} · "
                       f"가장 큰 쪽이 같은 칸 {same}/{total}</span></p>"
                       f"<table class='mgrid'>{head}{''.join(rows)}</table>"
                       "<p class='note'>숫자는 낮음·비슷·높음(강수: 적음·비슷·많음) 확률 · 기상청 권역 값은 지역별 확률을 "
                       "이 사이트 지점 수 비중으로 평균 · 채점은 각 주가 지나고 약 1주 뒤</p></div>")
    return out


def verification_page(store, img_dir: Path) -> str:
    dparts, ddata = daily_verification_parts(store)
    mparts, mdata = month_verification_parts(store, img_dir)
    kparts = kma_compare_parts(store)
    regions = _order(list(dparts) + list(mparts) + list(kparts))
    head = ("<div class='phead'><div><h1>정확도</h1><p class='meta'>지난 예측을 실제 날씨(ERA5)와 맞춰 본 성적</p></div>"
            "<a class='btn ghost' href='verification.xlsx' download>엑셀</a></div>")
    out = head + _region_tabs(regions)
    if not regions:
        out += ("<div class='card empty'><b>아직 채점된 예측이 없습니다</b><p>일별 예측은 약 1주 뒤부터, "
                "1개월 전망은 첫 전망의 대상 4주가 지난 뒤부터 성적이 쌓입니다.</p></div>")
    for region in regions:
        dt, dcard = dparts.get(region, ([], ""))
        mt, mcard = mparts.get(region, ([], ""))
        out += f"<section class='rsec' data-region='{region}'>"
        if dt or mt:
            out += "<div class='tiles'>" + "".join(dt + mt) + "</div>"
        # PC: 일별·1개월 성적 카드를 같은 줄·같은 높이로 (휴대폰은 위아래)
        out += ("<div class='dgrid eq st'><div class='gcol'><h3 class='sec'>일별 예측 "
                "<span class='q'>· 날마다 실제 날씨와 비교</span></h3>"
                + (dcard or "<div class='card empty'><b>아직 채점 전</b><p>첫 예측 후 약 1주가 지나면 나타납니다.</p></div>")
                + "</div><div class='gcol'><h3 class='sec'>1개월 전망 <span class='q'>· 주별 확률, 4주가 지난 뒤 채점</span></h3>"
                + kparts.get(region, "")
                + (mcard or "<div class='card empty'><b>아직 채점 전</b><p>첫 전망의 대상 4주가 지나고 "
                            "약 1주 뒤부터 나타납니다.</p></div>") + "</div></div>")
        out += "</section>"
    out += methods_block("verify")
    if mdata or ddata:
        blob = json.dumps({"month": mdata, "daily": ddata}, ensure_ascii=False,
                          separators=(",", ":")).replace("</", "<\\/")
        out += (f'<script id="vdata" type="application/json">{blob}</script>'
                '<script src="chart.umd.min.js"></script><script src="verify.js"></script>')
    return out


def verification_excel(store, path: Path, daily_days: int = 120) -> Path:
    """정확도 기록을 엑셀로: 요약(1개월 RPSS, 일별 성적)과 채점 기록 원자료."""
    from openpyxl.styles import Alignment, Font, PatternFill
    from .daily import DLABEL, MODEL_LABEL, summary
    src_name = {**SOURCE_LABEL, **MODEL_LABEL, "combined": "최종(결합)"}
    var_name = {**{k: v[0] for k, v in VAR_LABEL.items()}, **{k: v[0] for k, v in DLABEL.items()}}

    def nice(d: pd.DataFrame, cols: dict) -> pd.DataFrame:
        if d.empty:
            return pd.DataFrame({"안내": ["아직 채점된 기록이 없습니다"]})
        d = d.copy()
        if "region" in d:
            d["region"] = d["region"].map(lambda r: REGION_LABELS.get(r, r))
        if "source" in d:
            d["source"] = d["source"].map(lambda s: src_name.get(s, s))
        if "var" in d:
            d["var"] = d["var"].map(lambda v: var_name.get(v, v))
        return d[[c for c in cols if c in d]].rename(columns=cols)

    m = store.summary()
    if not m.empty:
        m = m[m["source"] != "blend_raw"]
    sheets = {
        "1개월 정확도": nice(m, {"region": "영역", "var": "변수", "source": "예측원", "lead": "몇 주 앞",
                              "rpss": "RPSS", "rps": "RPS", "rps_clim": "평년 RPS", "n": "채점 수"}),
        "1개월 채점 기록": nice(store.df("SELECT * FROM verification WHERE source != 'blend_raw' ORDER BY issue, region, var, lead"),
                             {"issue": "발표일", "region": "영역", "var": "변수", "source": "예측원", "lead": "몇 주 앞",
                              "start": "대상 주 시작", "obs": "실제 값", "obs_cat": "실제 구간(0낮음·1비슷·2높음)",
                              "rps": "RPS", "rps_clim": "평년 RPS", "err": "오차"}),
        "일별 정확도": nice(summary(store), {"region": "영역", "var": "변수", "source": "예측원", "bin": "예보일",
                                           "mae": "평균 오차", "mae_clim": "평년 오차", "skill": "평년 대비 개선",
                                           "bias": "치우침", "cover": "범위 적중률", "brier": "강수확률 Brier",
                                           "bss": "Brier 개선", "n": "채점 수"}),
        f"일별 채점(최근 {daily_days}일)": nice(
            store.df("SELECT * FROM daily_verification WHERE date >= (SELECT date(max(date), ?) FROM daily_verification) "
                     "ORDER BY date, region, var, source, lead",
                     (f"-{daily_days} day",)),
            {"issue": "발표일", "date": "날짜", "region": "영역", "var": "변수", "source": "예측원", "lead": "며칠 앞",
             "obs": "실제 값", "mean_raw": "보정 전 예측", "err": "오차", "abs_err": "절대 오차",
             "clim_abs_err": "평년 절대 오차", "in_band": "10~90% 범위 안", "brier": "강수확률 Brier"}),
    }
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for name, d in sheets.items():
            d.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for c in ws[1]:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="E8EEF8")
                c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                ws.column_dimensions[c.column_letter].width = 12
            ws.row_dimensions[1].height = 32
            ws.freeze_panes = "A2"
    return path


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
    global _BUILT
    _BUILT = f"{datetime.now():%Y-%m-%d %H:%M}"
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
    from .report import to_excel as month_excel
    for r in results:
        month_excel(r, site / f"forecast_{r['issue']}.xlsx")
        rights.stamp_xlsx(site / f"forecast_{r['issue']}.xlsx")
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
    (site / "verification.html").write_text(_page("정확도", verification_page(store, img), "verify"),
                                            encoding="utf-8")
    verification_excel(store, site / "verification.xlsx")
    rights.stamp_xlsx(site / "verification.xlsx")
    # 2주 일별 예측 (최신 1개)
    dd = rep / "daily"
    dailies = sorted(dd.glob("daily_*.json")) if dd.exists() else []
    if dailies:
        for png in dd.glob(f"{dailies[-1].stem}_*.png"):
            shutil.copy2(png, img / png.name)
        latest = json.loads(dailies[-1].read_text(encoding="utf-8"))
        body = daily_body(latest, "img/")
        from .daily import to_excel
        to_excel(latest, site / f"daily_{latest['issue']}.xlsx")
        rights.stamp_xlsx(site / f"daily_{latest['issue']}.xlsx")
    else:
        body = "<h1>일별 예측</h1><div class='card'>아직 일별 예측이 없습니다. 매일 아침 6시 40분에 만들어집니다.</div>"
    ndays = max((len(rd["days"]) for rd in latest["regions"].values()), default=14) if dailies else 14
    page = _page(f"{'4주' if ndays > 14 else '2주'} 일별 예측 · 한국 기상전망", body, "daily")
    for name in ("index.html", "daily.html"):          # 기본 화면 = 2주 일별 (daily.html 은 옛 주소)
        (site / name).write_text(page, encoding="utf-8")
    # 홈 화면 추가용 아이콘·매니페스트
    for name in ICON_FILES:
        shutil.copy2(STATIC / name, site / name)
    (site / "manifest.webmanifest").write_text(json.dumps(MANIFEST, ensure_ascii=False, indent=1),
                                               encoding="utf-8")
    (site / ".nojekyll").write_text("")
    (site / "version.json").write_text(json.dumps({"built": _BUILT}), encoding="utf-8")
    # 저작권·AI 수집 거부: 이용약관, (참고용) robots/ai.txt, 도메인 맨 앞에 올릴 파일(site_root/)
    (site / "terms.html").write_text(_page("이용약관과 저작권", rights.TERMS_HTML, "terms"), encoding="utf-8")
    (site / "robots.txt").write_text(rights.robots_txt(), encoding="utf-8")
    (site / "ai.txt").write_text(rights.ai_txt(), encoding="utf-8")
    rights.root_files(site.parent / "site_root")
    return str(site)
