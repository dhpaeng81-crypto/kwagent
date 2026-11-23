"""기후지수 수집: Niño3.4(주간), AO(일별), MJO RMM(일별).

모두 공개 텍스트 파일이다. 형식이 바뀌거나 접속이 안 되면 빈 시계열을 반환하고,
통계모델은 해당 예측인자를 0(기후값)으로 두고 계속 동작한다.
"""
from __future__ import annotations

import io
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import requests

log = logging.getLogger(__name__)
INDEX_COLS = ["nino34", "ao", "rmm1", "rmm2"]
# BoM 은 python-requests 기본 User-Agent 를 403 으로 막는다
HEADERS = {"User-Agent": "kwagent/0.2 (+https://github.com)"}


def _text(url: str, cache: Path) -> str | None:
    try:
        r = requests.get(url, timeout=60, headers=HEADERS)
        r.raise_for_status()
        cache.write_text(r.text, encoding="utf-8")
        return r.text
    except Exception as e:  # pragma: no cover - network
        log.warning("지수 다운로드 실패 %s (%s) — 캐시 사용", url, e)
        return cache.read_text(encoding="utf-8") if cache.exists() else None


def parse_nino34(text: str) -> pd.Series:
    """wksst9120.for: ' 03JAN1990     23.4-0.4     25.1-0.3     26.6 0.0     28.6 0.1'"""
    import re
    num = re.compile(r"-?\d+\.\d")
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 9 or not line[:2].isdigit():
            continue
        try:
            d = pd.to_datetime(line[:9], format="%d%b%Y")
        except ValueError:
            continue
        vals = num.findall(line[9:])
        if len(vals) >= 8:          # (Niño1+2, 3, 3.4, 4) × (SST, SSTA)
            rows.append((d, float(vals[5])))
    s = pd.Series(dict(rows), name="nino34").sort_index()
    # 주간 → 일별 보간
    return s.resample("D").interpolate() if not s.empty else s


def parse_ao(text: str) -> pd.Series:
    df = pd.read_csv(io.StringIO(text), sep=r"\s+", header=None, names=["y", "m", "d", "ao"],
                     on_bad_lines="skip")
    df = df.dropna()
    idx = pd.to_datetime(dict(year=df.y.astype(int), month=df.m.astype(int), day=df.d.astype(int)),
                         errors="coerce")
    return pd.Series(df["ao"].astype(float).values, index=idx, name="ao").dropna().sort_index()


def parse_rmm(text: str) -> pd.DataFrame:
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 7 or not parts[0].isdigit():
            continue
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            r1, r2 = float(parts[3]), float(parts[4])
        except ValueError:
            continue
        if abs(r1) > 900 or abs(r2) > 900:   # 결측 1.E36 등
            continue
        rows.append((pd.Timestamp(y, m, d), r1, r2))
    return pd.DataFrame(rows, columns=["date", "rmm1", "rmm2"]).set_index("date")


def fetch_indices(cfg, cache_dir: Path) -> pd.DataFrame:
    src = cfg["sources"]["indices"]
    parts = []
    t = _text(src["nino34_url"], cache_dir / "nino34.txt")
    if t:
        parts.append(parse_nino34(t).to_frame())
    t = _text(src["ao_url"], cache_dir / "ao.txt")
    if t:
        parts.append(parse_ao(t).to_frame())
    t = _text(src["mjo_url"], cache_dir / "rmm.txt")
    if t:
        parts.append(parse_rmm(t))
    if not parts:
        return pd.DataFrame(columns=INDEX_COLS)
    df = pd.concat(parts, axis=1).sort_index()
    for c in INDEX_COLS:
        if c not in df:
            df[c] = np.nan
    return df[INDEX_COLS]


# 지수별 (평균 낼 최근 일수, 허용하는 자료 최대 나이[일]).
# 마지막 값이 이보다 오래되면 갱신이 끊긴 것으로 보고 0(기후값)을 쓴다.
# 예: BoM RMM 파일은 2024-02 이후 갱신이 멈춰 있다 → 2년 묵은 MJO 를 쓰지 않도록.
# AO(CPC current.ascii)는 월 1회 갱신이라 최대 6주 늦을 수 있어 넉넉히 둔다.
_PRED_SPEC = {"nino34": (7, 21), "ao": (7, 45), "rmm1": (3, 10), "rmm2": (3, 10)}


def predictors_at(indices: pd.DataFrame, issue: pd.Timestamp) -> dict[str, float]:
    """발표일 기준 최근 값: Niño3.4(최근), AO(7일 평균), RMM1/2(최근 3일 평균).

    자료가 너무 오래되면(_PRED_SPEC) 0 으로 둔다. 학습·예측 모두 같은 규칙이라 일관된다.
    """
    out = {c: 0.0 for c in INDEX_COLS}
    if indices is None or indices.empty:
        return out
    issue = pd.Timestamp(issue)
    hist = indices[indices.index < issue]
    if hist.empty:
        return out
    for c, (n, max_age) in _PRED_SPEC.items():
        v = hist[c].dropna()
        if v.empty or (issue - v.index[-1]).days > max_age:
            continue
        out[c] = float(v.tail(n).mean())
    return out


def staleness(indices: pd.DataFrame, today: pd.Timestamp) -> dict[str, int | None]:
    """지수별 마지막 자료가 며칠 전인지 (doctor·로그용)."""
    out: dict[str, int | None] = {}
    for c in INDEX_COLS:
        v = indices[c].dropna() if indices is not None and c in indices else pd.Series(dtype=float)
        out[c] = None if v.empty else int((pd.Timestamp(today) - v.index[-1]).days)
    return out
