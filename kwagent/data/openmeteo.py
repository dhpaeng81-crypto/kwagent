"""Open-Meteo 수집기 (API 키 불필요, 비상업 무료).

- archive  : ERA5/ERA5-Land 재분석 일별 자료 (정답 + 통계모델 학습용, 1940~)
- seasonal : ECMWF EC46(46일) / SEAS5 — 일별 앙상블 멤버
- ensemble : NOAA GEFS 0.5° (35일, 31멤버)

모든 결과는 '긴 형식' DataFrame: date, point, member, temp, cloud, precip, rain
(관측은 member = -1)
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests

from ..regions import Point

DAILY_VARS = {
    "temperature_2m_mean": "temp",
    "cloud_cover_mean": "cloud",
    "precipitation_sum": "precip",
    "rain_sum": "rain",
    "snowfall_sum": "snow_cm",
}
SNOW_CM_PER_MM = 0.7  # Open-Meteo 환산: 강설(cm) = 강수 상당량(mm) × 0.7

_MEMBER_RE = re.compile(r"^(?P<var>.+?)(?:_member(?P<m>\d+))?$")


def _get(url: str, params: dict, retries: int = 3, pause: float = 1.0) -> list[dict]:
    last = None
    for i in range(retries):
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                js = r.json()
                return js if isinstance(js, list) else [js]
            last = f"HTTP {r.status_code}: {r.text[:300]}"
        except requests.RequestException as e:  # pragma: no cover - network
            last = str(e)
        time.sleep(pause * (2 ** i))
    raise RuntimeError(f"Open-Meteo 요청 실패 {url}: {last}")


def _parse_daily(js: dict, point: str) -> pd.DataFrame:
    daily = js.get("daily", {})
    dates = pd.to_datetime(daily.get("time", []))
    frames: dict[int, dict[str, list]] = {}
    for key, values in daily.items():
        if key == "time":
            continue
        m = _MEMBER_RE.match(key)
        var, mem = m.group("var"), m.group("m")
        if var not in DAILY_VARS:
            continue
        member = int(mem) if mem is not None else 0
        frames.setdefault(member, {})[DAILY_VARS[var]] = values
    out = []
    for member, cols in frames.items():
        df = pd.DataFrame(cols, index=dates)
        df["member"] = member
        out.append(df)
    if not out:
        return pd.DataFrame()
    df = pd.concat(out).rename_axis("date").reset_index()
    df["point"] = point
    return _finish(df)


def _finish(df: pd.DataFrame) -> pd.DataFrame:
    for c in ("temp", "cloud", "precip", "rain", "snow_cm"):
        if c not in df:
            df[c] = float("nan")
    # rain 이 없으면 강설로부터 추정
    miss = df["rain"].isna() & df["precip"].notna()
    df.loc[miss, "rain"] = (df.loc[miss, "precip"]
                            - df.loc[miss, "snow_cm"].fillna(0) / SNOW_CM_PER_MM).clip(lower=0)
    return df[["date", "point", "member", "temp", "cloud", "precip", "rain"]]


# ---------------------------------------------------------------- 관측(ERA5)
def fetch_archive(points: list[Point], start: date, end: date, cfg, cache_dir: Path) -> pd.DataFrame:
    """지점별 캐시 CSV를 증분 갱신하며 ERA5 일별 자료를 반환."""
    om = cfg["sources"]["openmeteo"]
    frames = []
    for p in points:
        cache = cache_dir / f"era5_{p.stn}.csv"
        have = pd.read_csv(cache, parse_dates=["date"]) if cache.exists() else pd.DataFrame()
        fetch_from = start
        if not have.empty:
            fetch_from = max(start, (have["date"].max() + pd.Timedelta(days=1)).date() - timedelta(days=10))
        if fetch_from <= end:
            js = _get(om["archive_url"], {
                "latitude": p.lat, "longitude": p.lon,
                "start_date": fetch_from.isoformat(), "end_date": end.isoformat(),
                "daily": ",".join(DAILY_VARS), "timezone": om["timezone"],
            }, pause=om.get("request_pause_s", 1.0))[0]
            new = _parse_daily(js, p.name)
            new["member"] = -1
            have = pd.concat([have, new]).drop_duplicates(["date"], keep="last") if not have.empty else new
            have = have.dropna(subset=["temp"])
            have.to_csv(cache, index=False)
            time.sleep(om.get("request_pause_s", 1.0))
        have["point"] = p.name
        frames.append(have[(have["date"] >= pd.Timestamp(start)) & (have["date"] <= pd.Timestamp(end))])
    return pd.concat(frames, ignore_index=True)


# ---------------------------------------------------------------- 역학모델
def _fetch_members(url: str, model: str, points: list[Point], days: int, cfg) -> pd.DataFrame:
    om = cfg["sources"]["openmeteo"]
    js_list = _get(url, {
        "latitude": ",".join(f"{p.lat}" for p in points),
        "longitude": ",".join(f"{p.lon}" for p in points),
        "models": model, "daily": ",".join(DAILY_VARS),
        "forecast_days": days, "timezone": om["timezone"],
    }, pause=om.get("request_pause_s", 1.0))
    frames = [_parse_daily(js, p.name) for js, p in zip(js_list, points)]
    return pd.concat([f for f in frames if not f.empty], ignore_index=True)


def fetch_ec46(points: list[Point], cfg) -> pd.DataFrame:
    om = cfg["sources"]["openmeteo"]
    return _fetch_members(om["seasonal_url"], om["ec46_model"], points, 46, cfg)


def fetch_gefs(points: list[Point], cfg) -> pd.DataFrame:
    om = cfg["sources"]["openmeteo"]
    return _fetch_members(om["ensemble_url"], om["gefs_model"], points, 35, cfg)
