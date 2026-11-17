"""통계 예측모델: 다항 로지스틱 회귀로 삼분위 확률을 직접 예측.

예측인자
- 추세: 연도 (온난화로 '높음'이 잦아지는 경향)
- 지속성: 발표 전 14일 영역평균 편차 (기온·운량·강수)
- 기후지수: Niño3.4, AO(7일), MJO RMM1/RMM2
- 계절성: sin/cos(연중일) 및 지수×계절 상호작용 (겨울에 AO 영향이 큰 점 반영)

학습: 1991년~작년, 매주 목요일 발표 × 1~4주 lead. 변수·lead 별로 별도 모델.
검증: 연도 단위 GroupKFold 교차검증으로 RPSS 를 계산해 결합 가중치 초기값으로 쓴다.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from ..calendar import issue_dates_between, target_weeks
from ..data.indices import predictors_at
from ..features import VARS, Climatology
from ..verify import rps, rpss

log = logging.getLogger(__name__)
OBS_LAG_DAYS = 5   # ERA5 공개 지연 — 발표 시점에 실제로 쓸 수 있는 자료만 사용

FEATURES = ["year", "a_temp", "a_cloud", "a_precip", "nino34", "ao", "rmm1", "rmm2",
            "sin", "cos", "nino_cos", "ao_cos", "ao_sin"]


def make_features(issue: date, cdoy: int, obs_daily: pd.DataFrame, clim: Climatology,
                  indices: pd.DataFrame | None) -> dict[str, float]:
    end = pd.Timestamp(issue - timedelta(days=OBS_LAG_DAYS))
    an = clim.daily_anomaly(obs_daily, end)
    ix = predictors_at(indices, pd.Timestamp(issue))
    ang = 2 * np.pi * cdoy / 365.25
    s, c = np.sin(ang), np.cos(ang)
    return {
        "year": (issue.year - 2005) / 10, "a_temp": an["temp"], "a_cloud": an["cloud"],
        "a_precip": an["precip"], **ix, "sin": s, "cos": c,
        "nino_cos": ix["nino34"] * c, "ao_cos": ix["ao"] * c, "ao_sin": ix["ao"] * s,
    }


def build_training(obs_daily, obs_weekly, clim, indices, start_year, end_date, n_weeks=4,
                   weekday=3) -> pd.DataFrame:
    rows = []
    issues = issue_dates_between(date(start_year, 1, 15), end_date, weekday)
    for issue in issues:
        for tw in target_weeks(issue, n_weeks):
            ts = pd.Timestamp(tw.start)
            if ts not in obs_weekly.index or tw.end > end_date:
                continue
            truth = obs_weekly.loc[ts]
            if truth[list(VARS)].isna().any():
                continue
            f = make_features(issue, tw.center_doy, obs_daily, clim, indices)
            row = {"issue": issue, "lead": tw.lead, "cdoy": tw.center_doy, **f}
            for v in VARS:
                row[f"y_{v}"] = clim.category(v, tw.center_doy, float(truth[v]))
            rows.append(row)
    return pd.DataFrame(rows)


class StatisticalModel:
    def __init__(self, C: float = 0.5):
        self.C = C
        self.models: dict[tuple[str, int], object] = {}
        self.cv_rpss: dict[tuple[str, int], float] = {}

    C_GRID = (0.003, 0.01, 0.03, 0.1, 0.5)

    def _new(self, C: float):
        return make_pipeline(StandardScaler(), LogisticRegression(C=C, max_iter=2000))

    def _cv(self, X, y, g, C, n_splits) -> np.ndarray:
        oof = np.full((len(y), 3), 1 / 3)
        gkf = GroupKFold(n_splits=min(n_splits, len(np.unique(g))))
        for tr, te in gkf.split(X, y, g):
            if len(np.unique(y[tr])) < 3:
                continue
            oof[te] = self._new(C).fit(X[tr], y[tr]).predict_proba(X[te])
        return oof

    def fit(self, train: pd.DataFrame, n_splits: int = 5) -> pd.DataFrame:
        """정규화 강도 C 를 연도별 교차검증으로 고른다 (예측인자가 약하면 기후값에 가깝게 수축)."""
        report = []
        groups = pd.to_datetime(train["issue"]).dt.year.values
        for v in VARS:
            for lead in sorted(train["lead"].unique()):
                mask = (train["lead"] == lead).values
                sub = train[mask]
                X, y, g = sub[FEATURES].values, sub[f"y_{v}"].values, groups[mask]
                onehot = np.eye(3)[y]
                best = None
                for C in self.C_GRID:
                    oof = self._cv(X, y, g, C, n_splits)
                    score = rpss(oof, onehot)
                    if best is None or score > best[1]:
                        best = (C, score, oof)
                C, score, oof = best
                self.cv_rpss[(v, int(lead))] = score
                self.models[(v, int(lead))] = self._new(C).fit(X, y)
                report.append({"var": v, "lead": int(lead), "n": len(y), "C": C,
                               "cv_rpss": round(score, 4),
                               "rps": round(float(rps(oof, onehot).mean()), 4)})
                log.info("통계모델 %s lead%d  C=%.3g CV-RPSS=%.3f (n=%d)", v, lead, C, score, len(y))
        return pd.DataFrame(report)

    def predict(self, var: str, lead: int, feats: dict[str, float]) -> np.ndarray:
        m = self.models.get((var, lead))
        if m is None:
            return np.full(3, 1 / 3)
        x = np.array([[feats[f] for f in FEATURES]])
        return m.predict_proba(x)[0]

    def save(self, path):
        joblib.dump({"C": self.C, "models": self.models, "cv_rpss": self.cv_rpss}, path)

    @classmethod
    def load(cls, path) -> "StatisticalModel":
        d = joblib.load(path)
        obj = cls(d["C"])
        obj.models, obj.cv_rpss = d["models"], d["cv_rpss"]
        return obj
