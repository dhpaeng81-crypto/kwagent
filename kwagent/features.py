"""영역평균, 주간 집계, 평년 삼분위 기준."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .regions import points_for

VARS = ("temp", "cloud", "srad", "precip")   # srad = 일사량(MJ/m²/일, 주평균)
CATS = ("below", "normal", "above")


def area_mean(df: pd.DataFrame, region: str) -> pd.DataFrame:
    """지점별 일자료 → 영역평균 일자료 (member 별)."""
    names = {p.name for p in points_for(region)}
    sub = df[df["point"].isin(names)]
    return (sub.groupby(["member", "date"])[[*VARS, "rain"]]
            .mean().reset_index())


def classify_day(precip: pd.Series, rain: pd.Series, wet_mm: float, snow_thr: float):
    wet = precip >= wet_mm
    snow_frac = 1 - (rain / precip.where(precip > 0)).clip(0, 1)
    snow = wet & (snow_frac >= snow_thr)
    return wet & ~snow, snow


def weekly_rolling(daily: pd.DataFrame, wet_mm: float, snow_thr: float) -> pd.DataFrame:
    """한 멤버의 일자료(date 정렬) → 각 날짜를 '시작일'로 하는 7일 집계."""
    d = daily.set_index("date").sort_index().asfreq("D")
    rain_day, snow_day = classify_day(d["precip"], d["rain"], wet_mm, snow_thr)
    roll = pd.DataFrame({
        "temp": d["temp"].rolling(7).mean(),
        "cloud": d["cloud"].rolling(7).mean(),
        "srad": d["srad"].rolling(7).mean(),
        "precip": d["precip"].rolling(7).sum(),
        "rain_days": rain_day.astype(float).rolling(7).sum(),
        "snow_days": snow_day.astype(float).rolling(7).sum(),
    })
    roll.index = roll.index - pd.Timedelta(days=6)   # 끝일 → 시작일
    return roll.dropna(how="all")


def week_values(daily: pd.DataFrame, start, wet_mm: float, snow_thr: float) -> pd.DataFrame:
    """앙상블 일자료(여러 member) → 지정 주의 member별 값."""
    start = pd.Timestamp(start)
    end = start + pd.Timedelta(days=6)
    sub = daily[(daily["date"] >= start) & (daily["date"] <= end)]
    rows = []
    for m, g in sub.groupby("member"):
        if g["date"].nunique() < 7:
            continue
        rain_day, snow_day = classify_day(g["precip"], g["rain"], wet_mm, snow_thr)
        rows.append({"member": m, "temp": g["temp"].mean(), "cloud": g["cloud"].mean(),
                     "srad": g["srad"].mean(),
                     "precip": g["precip"].sum(), "rain_days": rain_day.sum(),
                     "snow_days": snow_day.sum()})
    return pd.DataFrame(rows)


class Climatology:
    """평년(1991~2020) 주간값 분포. 목표 주 중심일 ±window 일의 모든 7일 구간을 표본으로 쓴다."""

    def __init__(self, obs_weekly: pd.DataFrame, obs_daily: pd.DataFrame,
                 period=(1991, 2020), window: int = 10):
        w = obs_weekly[(obs_weekly.index.year >= period[0]) & (obs_weekly.index.year <= period[1])]
        self.weekly = w.copy()
        self.weekly["cdoy"] = (w.index + pd.Timedelta(days=3)).dayofyear
        self.window = window
        # 일별 평년(지속성 편차용): 31일 이동평균 평활
        dd = obs_daily.set_index("date")
        dd = dd[(dd.index.year >= period[0]) & (dd.index.year <= period[1])]
        doy = dd.groupby(dd.index.dayofyear)[list(VARS)].mean()
        doy = doy.reindex(range(1, 367)).interpolate(limit_direction="both")
        ext = pd.concat([doy.tail(15), doy, doy.head(15)])
        self.daily_normal = ext.rolling(31, center=True).mean().iloc[15:-15]
        self._cache: dict[int, pd.DataFrame] = {}

    def sample(self, cdoy: int) -> pd.DataFrame:
        if cdoy not in self._cache:
            diff = np.abs(((self.weekly["cdoy"] - cdoy + 183) % 366) - 183)
            self._cache[cdoy] = self.weekly[diff <= self.window]
        return self._cache[cdoy]

    def terciles(self, var: str, cdoy: int) -> tuple[float, float]:
        s = self.sample(cdoy)[var].dropna()
        return float(s.quantile(1 / 3)), float(s.quantile(2 / 3))

    def normal_range(self, var: str, cdoy: int) -> tuple[float, float]:
        return self.terciles(var, cdoy)

    def snow_climo(self, cdoy: int) -> dict[str, float]:
        s = self.sample(cdoy)
        return {"p_snow": float((s["snow_days"] >= 1).mean()),
                "rain_days": float(s["rain_days"].mean()),
                "snow_days": float(s["snow_days"].mean())}

    def category(self, var: str, cdoy: int, value: float) -> int:
        lo, hi = self.terciles(var, cdoy)
        return int(0 if value < lo else (2 if value > hi else 1))

    def daily_anomaly(self, daily: pd.DataFrame, end: pd.Timestamp, days: int = 14) -> dict[str, float]:
        d = daily.set_index("date").sort_index()
        d = d[(d.index <= end) & (d.index > end - pd.Timedelta(days=days))]
        if d.empty:
            return {v: 0.0 for v in VARS}
        norm = self.daily_normal.reindex(d.index.dayofyear).values
        anom = d[list(VARS)].values - norm
        return dict(zip(VARS, np.nanmean(anom, axis=0).astype(float)))
