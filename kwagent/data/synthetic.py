"""합성 자료 공급자 — 네트워크 없이 전체 파이프라인을 시험하기 위한 것.

한국과 비슷한 계절순환·추세·지속성·AO/ENSO 영향을 가진 '가짜 날씨'를 만들고,
역학모델 앙상블은 '미래 정답 + lead 에 따라 커지는 오차 + 고정 편향'으로 흉내 낸다.
실제 예측 성능과는 무관하다.
"""
from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd

from ..regions import POINTS, Point


class SyntheticProvider:
    name = "synthetic"

    def __init__(self, seed: int = 7, start="1985-01-01", end="2027-12-31"):
        rng = np.random.default_rng(seed)
        idx = pd.date_range(start, end, freq="D")
        n = len(idx)
        doy = idx.dayofyear.values
        ang = 2 * np.pi * (doy - 15) / 365.25
        # 기후지수
        ao = np.zeros(n)
        for i in range(1, n):
            ao[i] = 0.93 * ao[i - 1] + rng.normal(0, 0.37)
        years = (idx.year + doy / 365.25).values
        nino = 1.1 * np.sin(2 * np.pi * years / 4.3) + 0.4 * np.sin(2 * np.pi * years / 2.7)
        phase = np.cumsum(rng.normal(2 * np.pi / 45, 0.02, n))
        amp = 1 + 0.5 * np.sin(2 * np.pi * years / 0.7)
        self.idx_df = pd.DataFrame({"nino34": nino, "ao": ao, "rmm1": amp * np.cos(phase),
                                    "rmm2": amp * np.sin(phase)}, index=idx)
        winter = np.clip(np.cos(ang), 0, None)
        # 공통 대규모 편차(지속성 있는 AR1) + 지점 잡음
        anom = np.zeros(n)
        for i in range(1, n):
            anom[i] = 0.85 * anom[i - 1] + rng.normal(0, 1.1)
        trend = 0.03 * (idx.year.values - 2005)
        base_t = 12.5 - 13.5 * np.cos(ang) + trend + anom + 1.8 * winter * ao - 0.4 * winter * nino
        wet_season = 0.5 + 0.45 * np.clip(-np.cos(ang), 0, None) ** 2
        frames = []
        for p in POINTS:
            off = (37.5 - p.lat) * 1.2
            t = base_t + off + rng.normal(0, 1.2, n)
            cloud = np.clip(48 + 20 * wet_season + 6 * anom / 2 + rng.normal(0, 18, n), 0, 100)
            # 일사량(MJ/m²/일): 여름 ~22, 겨울 ~8, 구름이 많을수록 적음
            srad = np.clip((15 - 7 * np.cos(ang)) * (1.25 - 0.6 * cloud / 100) + rng.normal(0, 1.5, n), 0.3, None)
            pwet = np.clip(0.18 + 0.25 * wet_season + 0.004 * (cloud - 50), 0.02, 0.9)
            wet = rng.random(n) < pwet
            pr = np.where(wet, rng.gamma(0.8, 6 + 18 * wet_season), 0.0)
            rain = np.where(t > 1.0, pr, np.where(t > -1.0, pr * 0.5, 0.0))
            frames.append(pd.DataFrame({"date": idx, "point": p.name, "member": -1, "temp": t,
                                        "cloud": cloud, "srad": srad, "precip": pr, "rain": rain}))
        self.truth = pd.concat(frames, ignore_index=True)
        self.rng = rng

    def archive(self, points: list[Point], start: date, end: date) -> pd.DataFrame:
        names = {p.name for p in points}
        t = self.truth
        return t[t["point"].isin(names) & (t["date"] >= pd.Timestamp(start))
                 & (t["date"] <= pd.Timestamp(end))].copy()

    def indices(self) -> pd.DataFrame:
        return self.idx_df.copy()

    def ensemble(self, source: str, points: list[Point], issue: date) -> pd.DataFrame:
        days, members, bias_t, skill = {"ec46": (46, 51, 0.8, 1.0), "gefs": (35, 31, -0.6, 0.8)}[source]
        rng = np.random.default_rng(zlib.crc32(f"{source}{issue}".encode()))
        start = pd.Timestamp(issue)
        dates = pd.date_range(start, periods=days, freq="D")
        truth = self.archive(points, dates[0].date(), dates[-1].date())
        out = []
        lead = (truth["date"] - start).dt.days.values
        sigma = 0.5 + 2.6 * (1 - np.exp(-lead / (9 * skill)))
        common = rng.normal(0, 1, (members, len(dates)))
        for m in range(members):
            e = common[m][lead] * sigma + rng.normal(0, 0.8, len(truth))
            df = truth.copy()
            df["member"] = m
            df["temp"] = df["temp"] + e + bias_t
            df["cloud"] = np.clip(df["cloud"] + 8 * e / 2 + 5, 0, 100)
            df["srad"] = np.clip(df["srad"] - 0.6 * e - 0.8, 0.1, None)
            scale = np.exp(0.25 * e) * 0.8
            df["precip"] = df["precip"] * scale
            df["rain"] = np.where(df["temp"] > 0.5, df["precip"], 0.0)
            out.append(df)
        return pd.concat(out, ignore_index=True)
