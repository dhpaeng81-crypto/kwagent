"""기상청 1개월전망 수집 → 이 사이트와 같은 기준으로 채점하기 위한 벤치마크 (2026-11-24 사용자 요청).

- 매주 목요일 11시(KST) 기상청이 PDF 로 발표한다. 지난 발표분은 사이트에서 사라지므로 발표 당일 받아 둔다.
  주소: https://www.weather.go.kr/w/repositary/xml/fct/mon/fct_mon1_108_YYYYMMDD.pdf  (108 = 전국, 권역 표 포함)
- PDF 의 '주·지역별 평균기온/강수량 확률 전망(%)' 표에서 지역·주별 낮음/비슷/높음 확률을 읽는다.
- 기상청 지역을 이 사이트 권역으로 묶을 때는 우리 지점 수만큼 비중을 둔다(중부 = 서울·인천·경기 3, 강원영서 2,
  강원영동 1, 대전·세종·충남 2, 충북 2 / 호남 = 전북 4, 전남·광주 3 / 경상 = 대구·경북 4, 부산·울산·경남 4).
- 결과는 forecasts 표에 source='kma' 로 저장 → 기존 채점(Agent.verify)이 같은 정답(ERA5)으로 자동 채점한다.
  (기상청 평년은 관측소 기준이라 ERA5 정답과 약간 어긋날 수 있음 — 화면 설명에 밝힘)
- 기상청 자료는 공공누리 출처표시 조건으로 이용한다. 원문 PDF 는 저장하지 않고, 읽은 글자(txt)만 data/kma/ 에 남긴다.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

URL = "https://www.weather.go.kr/w/repositary/xml/fct/mon/fct_mon1_108_{d}.pdf"
UA = "Mozilla/5.0 (X11; Linux x86_64) kwagent-benchmark"

# 기상청 지역 이름(일부 글자) → (이 사이트 권역, 비중). 전국은 따로.
REGION_MAP = [
    (("서울", "경기"), "central", 3), (("영서",), "central", 2), (("영동",), "central", 1),
    (("충청남", "충남", "대전"), "central", 2), (("충청북", "충북"), "central", 2),
    (("전북", "전라북"), "honam", 4), (("전남", "광주", "전라남"), "honam", 3),
    (("경상북", "경북", "대구"), "yeongnam", 4), (("경상남", "경남", "부산", "울산"), "yeongnam", 4),
]
SECTIONS = {"temp": "평균기온 확률 전망", "precip": "강수량 확률 전망"}
_CELL = re.compile(r"(-?\d+(?:\.\d+)?)\s*~\s*(-?\d+(?:\.\d+)?)\s+(\d+)\s+(\d+)\s+(\d+)")
_WEEK = re.compile(r"(\d)주\s*\((\d{1,2})\.(\d{1,2})\.?\s*~\s*(\d{1,2})\.(\d{1,2})\.?\)")
_ISSUE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일\s*\d{1,2}시\s*발표")


_SKIP = ("함경", "평안", "황해", "제주")     # 북한·제주: 권역에 넣지 않음 ('함경남북도'에 '경남'이 들어 있어 주의)


def classify(name: str) -> str | None:
    if "전국" in name:
        return "korea"
    if any(k in name for k in _SKIP):
        return None
    for keys, region, _ in REGION_MAP:
        if any(k in name for k in keys):
            return region
    return None


def _weight(name: str) -> float:
    for keys, _, w in REGION_MAP:
        if any(k in name for k in keys):
            return float(w)
    return 1.0


def parse(text: str) -> dict:
    """pdftotext -layout 결과 → {'issue', 'weeks':[(start,end)...], 'rows': {var: {지역이름: [(lo,hi,p0,p1,p2)]*4}}}"""
    m = _ISSUE.search(text)
    if not m:
        raise ValueError("발표일을 찾지 못함 (PDF 형식이 바뀌었을 수 있음)")
    issue = date(int(m[1]), int(m[2]), int(m[3]))
    weeks = []
    for wm in _WEEK.finditer(text):
        k = int(wm[1])
        if len(weeks) >= k:
            continue
        sm, sd, em, ed = map(int, wm.groups()[1:])
        sy = issue.year + (1 if sm < issue.month else 0)
        ey = sy + (1 if em < sm else 0)
        weeks.append((date(sy, sm, sd), date(ey, em, ed)))
    if len(weeks) != 4:
        raise ValueError(f"주 기간을 4개 찾지 못함: {weeks}")
    rows: dict[str, dict] = {}
    lines = text.splitlines()
    for var, title in SECTIONS.items():
        start = next((i for i, ln in enumerate(lines) if title in ln), None)
        if start is None:
            raise ValueError(f"'{title}' 표를 찾지 못함")
        got = {}
        others = [x for v2, x in SECTIONS.items() if v2 != var]
        for ln in lines[start + 1:start + 60]:
            if any(o in ln for o in others) or (got and ("\f" in ln or "■" in ln)):
                break                                    # 다음 표·장이 시작되면 끝
            cells = _CELL.findall(ln)
            if len(cells) == 4:
                name = ln[:ln.index(_CELL.search(ln).group(0))].strip()
                if name in got:
                    break
                got[name] = [(float(a), float(b), int(p), int(q), int(r)) for a, b, p, q, r in cells]
        if not got:
            raise ValueError(f"'{title}' 표가 비어 있음")
        rows[var] = got
    return {"issue": issue, "weeks": weeks, "rows": rows}


def to_regions(parsed: dict) -> dict:
    """기상청 지역 → 이 사이트 권역(비중 평균). {region: {var: [[p0,p1,p2] 주별 4개]}} (확률 0~1)"""
    out: dict[str, dict] = {}
    for var, table in parsed["rows"].items():
        acc: dict[str, list] = {}
        for name, cells in table.items():
            region = classify(name)
            if region is None:
                continue
            w = 1.0 if region == "korea" else _weight(name)
            acc.setdefault(region, []).append((w, cells))
        for region, items in acc.items():
            wsum = sum(w for w, _ in items)
            probs = []
            for k in range(4):
                p = [sum(w * c[k][2 + j] for w, c in items) / wsum / 100 for j in range(3)]
                s = sum(p)
                probs.append([x / s for x in p])
            out.setdefault(region, {})[var] = probs
    return out


def save(store, parsed: dict, regions: list[str]) -> int:
    n = 0
    for region, vs in to_regions(parsed).items():
        if region not in regions:
            continue
        for var, probs in vs.items():
            for lead, (p, (start, _)) in enumerate(zip(probs, parsed["weeks"]), start=1):
                store.save_forecast(parsed["issue"], region, "kma", var, lead, start, p)
                n += 1
    store.commit()
    return n


def pdf_to_text(pdf: Path) -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext 가 없습니다 (poppler-utils 설치 필요)")
    out = pdf.with_suffix(".txt")
    subprocess.run([exe, "-layout", str(pdf), str(out)], check=True)
    return out.read_text(encoding="utf-8")


def fetch(d: date, timeout: int = 60) -> str | None:
    """그 날짜 발표 PDF 를 받아 글자로. 없으면(발표 전·지난 발표분) None."""
    import requests
    r = requests.get(URL.format(d=d.strftime("%Y%m%d")), headers={"User-Agent": UA}, timeout=timeout)
    if r.status_code != 200 or not r.content.startswith(b"%PDF"):
        return None
    with tempfile.TemporaryDirectory() as td:
        pdf = Path(td) / "kma.pdf"
        pdf.write_bytes(r.content)
        return pdf_to_text(pdf)


def collect(agent, around: date | None = None) -> dict | None:
    """최근 목요일(±1일) 발표분을 찾아 저장. 이미 저장돼 있으면 건너뜀."""
    from .calendar import today_kst
    today = around or today_kst()
    thu = today - timedelta(days=(today.weekday() - 3) % 7)
    out_dir = agent.cfg.root / "data" / "kma"
    out_dir.mkdir(parents=True, exist_ok=True)
    for d in (thu, thu - timedelta(days=1), thu + timedelta(days=1)):
        if d > today:
            continue
        txt_path = out_dir / f"fct_mon1_108_{d:%Y%m%d}.txt"
        if txt_path.exists():
            log.info("기상청 %s 발표분은 이미 있음", d)
            text = txt_path.read_text(encoding="utf-8")
        else:
            text = fetch(d)
            if text is None:
                continue
            txt_path.write_text(text, encoding="utf-8")
        parsed = parse(text)
        n = save(agent.store, parsed, agent.cfg.regions)
        log.info("기상청 1개월전망 %s: %d건 저장", parsed["issue"], n)
        return {"issue": str(parsed["issue"]), "saved": n, "file": str(txt_path)}
    log.warning("기상청 1개월전망 PDF 를 찾지 못함 (%s 전후)", thu)
    return None
