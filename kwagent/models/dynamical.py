"""역학모델(EC46, GEFS) 앙상블 → 편향보정 → 삼분위 확률.

편향보정: 같은 예측원·변수·lead 의 과거 검증 기록에서 '앙상블평균 − 관측' 평균을 빼준다.
  기온·운량 = 더하기 보정, 강수량 = 곱하기 보정(비율, 0.3~3배로 제한).
확률: 보정된 멤버 값이 평년 삼분위 구간에 떨어지는 비율 (+1/3 멤버 평활로 0% 방지).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..calendar import TargetWeek
from ..features import VARS, Climatology, week_values


def apply_bias(values: np.ndarray, var: str, bias: float | None) -> np.ndarray:
    if bias is None or not np.isfinite(bias):
        return values
    if var == "precip":
        return values * float(np.clip(bias, 0.3, 3.0))
    return values - bias


def ensemble_week(ens_daily: pd.DataFrame, tw: TargetWeek, clim: Climatology,
                  biases: dict[str, float | None], wet_mm: float, snow_thr: float) -> dict | None:
    wk = week_values(ens_daily, tw.start, wet_mm, snow_thr)
    if len(wk) < 5:          # 멤버가 너무 적거나 예측 기간 밖
        return None
    out: dict = {"n_members": int(len(wk))}
    for v in VARS:
        vals = apply_bias(wk[v].to_numpy(float), v, biases.get(v))
        lo, hi = clim.terciles(v, tw.center_doy)
        counts = np.array([(vals < lo).sum(), ((vals >= lo) & (vals <= hi)).sum(), (vals > hi).sum()],
                          dtype=float)
        k = 1.0
        out[v] = {"prob": (counts + k / 3) / (counts.sum() + k),
                  "ens_mean_raw": float(wk[v].mean()), "ens_mean": float(vals.mean())}
    out["ptype"] = {"p_snow": float((wk["snow_days"] >= 1).mean()),
                    "rain_days": float(wk["rain_days"].mean()),
                    "snow_days": float(wk["snow_days"].mean())}
    return out
