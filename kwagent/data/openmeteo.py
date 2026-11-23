"""Open-Meteo 수집기 (API 키 불필요, 비상업 무료).

- archive  : ERA5/ERA5-Land 재분석 일별 자료 (정답 + 통계모델 학습용, 1940~)
- seasonal : ECMWF EC46(46일) / SEAS5 — 일별 앙상블 멤버
- ensemble : NOAA GEFS 0.5° (35일, 31멤버)

모든 결과는 '긴 형식' DataFrame: date, point, member, temp, cloud, precip, rain
(관측은 member = -1)
"""
from __future__ import annotations

import re
import json
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


class QuotaError(RuntimeError):
    """Open-Meteo 시간·일 한도 초과(또는 이번 실행 시간 상한). 받은 데까지 저장하고 다음 실행에서 이어 받는다."""


# 과거 자료 받기의 이번 실행 마감 시각(time.time() 기준, None 이면 무제한) — kwagent backfill 이 설정
DEADLINE: float | None = None


def _get(url: str, params: dict, retries: int = 6, pause: float = 2.0,
         minutely_waits: int = 5) -> list[dict]:
    """GET + 재시도. 429 분당 한도는 1분 기다려 재시도, 시간·일 한도는 QuotaError.

    Open-Meteo 무료판은 긴 기간 요청을 '여러 번 호출'로 센다(지점당 2주 = 1회).
    """
    last = None
    i = 0
    while i < retries:
        try:
            r = requests.get(url, params=params, timeout=120)
            if r.status_code == 200:
                js = r.json()
                return js if isinstance(js, list) else [js]
            last = f"HTTP {r.status_code}: {r.text[:300]}"
            if r.status_code == 429:
                if "Minutely" in r.text and minutely_waits > 0:
                    minutely_waits -= 1
                    time.sleep(61)
                    continue
                if "Hourly" in r.text or "Daily" in r.text or "Monthly" in r.text:
                    raise QuotaError(last)
        except requests.RequestException as e:  # pragma: no cover - network
            last = str(e)
        time.sleep(pause * (2 ** i))
        i += 1
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
def archive_file(cache_dir: Path, p: Point) -> Path:
    return cache_dir / f"era5_{p.stn}.csv.gz"


def fetch_archive(points: list[Point], start: date, end: date, cfg, cache_dir: Path,
                  marker_dir: Path | None = None) -> pd.DataFrame:
    """지점별 파일(data/era5, 저장소에 커밋)을 증분 갱신하며 ERA5 일별 자료를 반환.

    요청은 1년 단위로 나누고, 조각마다 파일에 저장한다. 한도(QuotaError)에 걸리면
    그때까지 받은 것은 남고 예외가 올라간다 → 다음 실행이 이어서 받는다.
    marker_dir 가 주어지면 같은 end 로 이미 갱신한 지점은 다시 받지 않는다
    (backfill → train → run 이 각각 같은 최근 10일을 다시 받던 낭비 방지).
    """
    om = cfg["sources"]["openmeteo"]
    chunk_pause = float(om.get("archive_chunk_pause_s", 4.0))
    marker = Path(marker_dir) / "era5_refreshed.json" if marker_dir is not None else None
    done = {}
    if marker is not None and marker.exists():
        try:
            done = json.loads(marker.read_text())
        except ValueError:
            done = {}
    frames = []
    for p in points:
        cache = archive_file(cache_dir, p)
        have = pd.read_csv(cache, parse_dates=["date"]) if cache.exists() else pd.DataFrame()
        fetch_from = start
        if not have.empty:
            fetch_from = max(start, (have["date"].max() + pd.Timedelta(days=1)).date() - timedelta(days=10))
            if done.get(p.name) == end.isoformat() and have["date"].min() <= pd.Timestamp(start):
                fetch_from = end + timedelta(days=1)          # 오늘 이미 갱신함
        while fetch_from <= end:
            if DEADLINE is not None and time.time() > DEADLINE:
                raise QuotaError("이번 실행의 자료 받기 시간 상한 도달")
            chunk_end = min(end, date(fetch_from.year, 12, 31))
            js = _get(om["archive_url"], {
                "latitude": p.lat, "longitude": p.lon,
                "start_date": fetch_from.isoformat(), "end_date": chunk_end.isoformat(),
                "daily": ",".join(DAILY_VARS), "timezone": om["timezone"],
            }, pause=om.get("request_pause_s", 1.0))[0]
            new = _parse_daily(js, p.name)
            new["member"] = -1
            have = pd.concat([have, new]).drop_duplicates(["date"], keep="last") if not have.empty else new
            have = have.dropna(subset=["temp"]).sort_values("date")
            have.to_csv(cache, index=False)
            fetch_from = chunk_end + timedelta(days=1)
            # 남은 조각이 있으면 분당 한도(600회)에 안 걸리게 쉬어 간다 (1년 조각 ≈ 26회)
            time.sleep(chunk_pause if fetch_from <= end else om.get("request_pause_s", 1.0))
        if marker is not None and not have.empty:
            done[p.name] = end.isoformat()
            marker.write_text(json.dumps(done, ensure_ascii=False))
        have["point"] = p.name
        frames.append(have[(have["date"] >= pd.Timestamp(start)) & (have["date"] <= pd.Timestamp(end))])
    return pd.concat(frames, ignore_index=True)


def archive_progress(points: list[Point], start: date, cache_dir: Path) -> dict[str, str | None]:
    """지점별로 받아 둔 마지막 날짜 (없으면 None)."""
    out = {}
    for p in points:
        f = archive_file(cache_dir, p)
        if not f.exists():
            out[p.name] = None
            continue
        d = pd.read_csv(f, usecols=["date"], parse_dates=["date"])["date"]
        out[p.name] = None if d.empty or d.min() > pd.Timestamp(start) + pd.Timedelta(days=7) \
            else f"{d.max():%Y-%m-%d}"
    return out


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
