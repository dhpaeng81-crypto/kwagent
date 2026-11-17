"""예측원 결합 + 기후값 쪽 수축(보정) + 표시용 반올림."""
from __future__ import annotations

import numpy as np

from ..store import Store
from ..verify import CLIM, rps

ALPHAS = np.round(np.arange(0.0, 0.95, 0.05), 2)


def source_weights(store: Store, region: str, var: str, lead: int, sources: list[str], cfg,
                   stat_cv_rpss: float | None) -> dict[str, float]:
    cc = cfg["combine"]
    w = {}
    for s in sources:
        hist = store.recent_verif(region, s, var, lead)
        if len(hist) >= cc["min_verified"]:
            skill = 1 - hist["rps"].mean() / hist["rps_clim"].mean()
            w[s] = max(float(skill), 0.01)
        else:
            prior = float(cc["prior_weights"].get(s, 0.1))
            if s == "statistical" and stat_cv_rpss is not None:
                # 교차검증에서 기술이 없으면 비중을 줄인다
                prior *= float(np.clip(stat_cv_rpss / 0.05, 0.1, 1.5))
            elif s != "statistical":
                prior *= cc["unverified_dyn_factor"]
            w[s] = prior
    tot = sum(w.values())
    return {k: v / tot for k, v in w.items()} if tot > 0 else w


def shrink_alpha(store: Store, region: str, var: str, lead: int, cfg) -> float:
    """결합 확률을 기후값 쪽으로 당기는 비율. 검증 20건 이상이면 RPS 최소화로 추정."""
    default = float(cfg["combine"]["shrink_to_climatology"][min(lead, 4) - 1])
    hist = store.recent_verif(region, "blend_raw", var, lead, n=104)
    if len(hist) < 20:
        return default
    p = hist[["p0", "p1", "p2"]].to_numpy()
    o = np.eye(3)[hist["obs_cat"].astype(int)]
    scores = [rps((1 - a) * p + a * CLIM, o).mean() for a in ALPHAS]
    return float(ALPHAS[int(np.argmin(scores))])


def blend(probs: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    num = sum(weights[s] * np.asarray(p) for s, p in probs.items() if s in weights)
    den = sum(weights[s] for s in probs if s in weights)
    return num / den if den else CLIM.copy()


def finalize(p: np.ndarray, alpha: float, min_prob: float) -> np.ndarray:
    q = (1 - alpha) * np.asarray(p) + alpha * CLIM
    q = np.maximum(q, min_prob)
    return q / q.sum()


def to_display(p: np.ndarray, step: int = 10) -> list[int]:
    """기상청 형식처럼 10% 단위, 합계 100."""
    raw = np.asarray(p) * 100 / step
    base = np.floor(raw).astype(int)
    rem = int(100 / step - base.sum())
    for i in np.argsort(-(raw - base))[:rem]:
        base[i] += 1
    return (base * step).tolist()
