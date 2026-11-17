"""확률예측 검증 지표."""
from __future__ import annotations

import numpy as np

CLIM = np.array([1 / 3, 1 / 3, 1 / 3])


def rps(prob: np.ndarray, onehot: np.ndarray) -> np.ndarray:
    """Ranked Probability Score (삼분위, 0=완벽). prob, onehot: (n,3)"""
    prob, onehot = np.atleast_2d(prob), np.atleast_2d(onehot)
    return ((np.cumsum(prob, 1) - np.cumsum(onehot, 1)) ** 2).sum(1) / 2


def rpss(prob: np.ndarray, onehot: np.ndarray, ref: np.ndarray | None = None) -> float:
    """RPSS = 1 - RPS/RPS_ref. 0 = 기후값 수준, 양수 = 기후값보다 나음."""
    ref = CLIM if ref is None else ref
    r = rps(prob, onehot).mean()
    r0 = rps(np.broadcast_to(ref, np.atleast_2d(onehot).shape), onehot).mean()
    return float(1 - r / r0) if r0 > 0 else 0.0


def reliability(prob: np.ndarray, onehot: np.ndarray, cat: int, bins=(0, .2, .3, .4, .5, .6, 1.01)):
    """범주 cat 에 대한 신뢰도표: (예측확률 평균, 관측빈도, 표본수)."""
    p, o = np.asarray(prob)[:, cat], np.asarray(onehot)[:, cat]
    out = []
    for lo, hi in zip(bins[:-1], bins[1:]):
        m = (p >= lo) & (p < hi)
        if m.sum():
            out.append((float(p[m].mean()), float(o[m].mean()), int(m.sum())))
    return out


def brier(p: np.ndarray, o: np.ndarray) -> float:
    return float(np.mean((np.asarray(p) - np.asarray(o)) ** 2))
