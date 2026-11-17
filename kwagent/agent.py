"""에이전트 본체: 수집 → 학습 → 예측 → 결합 → 저장 → 검증 → 보고서·해설."""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .calendar import target_weeks, today_kst
from .config import Config
from .data.provider import make_provider
from .features import VARS, Climatology, area_mean, weekly_rolling
from .models.combine import blend, finalize, shrink_alpha, source_weights, to_display
from .models.dynamical import ensemble_week
from .models.statistical import StatisticalModel, build_training, make_features
from .regions import POINTS
from .store import Store, onehot
from .verify import CLIM, rps

log = logging.getLogger(__name__)
DYN_SOURCES = ("ec46", "gefs")


class Agent:
    def __init__(self, cfg: Config, offline: bool = False, asof: date | None = None):
        self.cfg = cfg
        self.offline = offline
        self.asof = asof or (today_kst() - timedelta(days=1))
        self.provider = make_provider(cfg, cfg.path("cache"), offline)
        self.store = Store(cfg.path("store"))
        self._obs: pd.DataFrame | None = None
        self._region: dict[str, dict] = {}
        self._indices: pd.DataFrame | None = None
        self.wet_mm = float(cfg["wet_day_mm"])
        self.snow_thr = float(cfg["snow_fraction_threshold"])

    # ------------------------------------------------------------ 자료
    @property
    def obs_end(self) -> date:
        # 합성 모드에서는 ERA5 공개 지연(약 5일)을 흉내 낸다
        return self.asof - timedelta(days=5) if self.offline else self.asof

    def obs(self) -> pd.DataFrame:
        if self._obs is None:
            start = date(min(self.cfg["train_start_year"], self.cfg["normal_period"][0]) - 1, 12, 1)
            self._obs = self.provider.archive(POINTS, start, self.obs_end)
        return self._obs

    def indices(self) -> pd.DataFrame:
        if self._indices is None:
            df = self.provider.indices()
            self._indices = df[df.index <= pd.Timestamp(self.asof)] if not df.empty else df
        return self._indices

    def region(self, region: str) -> dict:
        if region not in self._region:
            daily = area_mean(self.obs(), region)
            daily = daily[daily["member"] == -1].drop(columns="member")
            weekly = weekly_rolling(daily, self.wet_mm, self.snow_thr)
            clim = Climatology(weekly, daily, tuple(self.cfg["normal_period"]))
            self._region[region] = {"daily": daily, "weekly": weekly, "clim": clim}
        return self._region[region]

    def _model_path(self, region: str):
        return self.cfg.path("models") / f"statistical_{region}.joblib"

    # ------------------------------------------------------------ 학습
    def train(self, end: date | None = None) -> pd.DataFrame:
        end = end or self.obs_end
        reports = []
        for region in self.cfg.regions:
            r = self.region(region)
            log.info("[%s] 학습 자료 구성 중 (%d ~ %s)", region, self.cfg["train_start_year"], end)
            train = build_training(r["daily"], r["weekly"], r["clim"], self.indices(),
                                   self.cfg["train_start_year"], end, self.cfg["n_weeks"],
                                   self.cfg["issue_weekday"])
            model = StatisticalModel()
            rep = model.fit(train)
            rep.insert(0, "region", region)
            model.save(self._model_path(region))
            reports.append(rep)
        out = pd.concat(reports, ignore_index=True)
        out.to_csv(self.cfg.path("reports") / "train_report.csv", index=False)
        return out

    # ------------------------------------------------------------ 예측
    def forecast(self, issue: date) -> dict:
        ens = {}
        for s in DYN_SOURCES:
            df = self.provider.ensemble(s, POINTS, issue)
            ens[s] = df
            log.info("%s 앙상블: %s", s, "없음" if df is None else f"{df['member'].nunique()} 멤버")
        result = {"issue": str(issue), "generated": str(today_kst()), "regions": {},
                  "indices": {k: round(v, 2) for k, v in self._index_snapshot(issue).items()}}
        for region in self.cfg.regions:
            result["regions"][region] = self._forecast_region(region, issue, ens)
        self.store.commit()
        return result

    def _index_snapshot(self, issue: date) -> dict:
        from .data.indices import predictors_at
        return predictors_at(self.indices(), pd.Timestamp(issue))

    def _forecast_region(self, region: str, issue: date, ens: dict) -> dict:
        r = self.region(region)
        clim: Climatology = r["clim"]
        model = StatisticalModel.load(self._model_path(region))
        daily_known = r["daily"][r["daily"]["date"] <= pd.Timestamp(issue)]
        ens_area = {s: area_mean(df, region) for s, df in ens.items() if df is not None}
        weeks = []
        for tw in target_weeks(issue, self.cfg["n_weeks"]):
            feats = make_features(issue, tw.center_doy, daily_known, clim, self.indices())
            wk = {"lead": tw.lead, "start": str(tw.start), "end": str(tw.end), "label": tw.label,
                  "vars": {}, "ptype": {}}
            dyn = {}
            for s, df in ens_area.items():
                biases = {v: self.store.bias(region, s, v, tw.lead, tw.start.month) for v in VARS}
                out = ensemble_week(df, tw, clim, biases, self.wet_mm, self.snow_thr)
                if out:
                    dyn[s] = out
            for v in VARS:
                probs = {"statistical": model.predict(v, tw.lead, feats)}
                self.store.save_forecast(issue, region, "statistical", v, tw.lead, tw.start,
                                         probs["statistical"])
                for s, out in dyn.items():
                    probs[s] = out[v]["prob"]
                    self.store.save_forecast(issue, region, s, v, tw.lead, tw.start, out[v]["prob"],
                                             out[v]["ens_mean_raw"])
                w = source_weights(self.store, region, v, tw.lead, list(probs), self.cfg,
                                   model.cv_rpss.get((v, tw.lead)))
                raw = blend(probs, w)
                self.store.save_forecast(issue, region, "blend_raw", v, tw.lead, tw.start, raw)
                alpha = shrink_alpha(self.store, region, v, tw.lead, self.cfg)
                final = finalize(raw, alpha, self.cfg["combine"]["min_prob"])
                self.store.save_forecast(issue, region, "combined", v, tw.lead, tw.start, final)
                lo, hi = clim.normal_range(v, tw.center_doy)
                ens_mean = np.mean([o[v]["ens_mean"] for o in dyn.values()]) if dyn else None
                wk["vars"][v] = {
                    "prob": [round(float(x), 3) for x in final],
                    "display": to_display(final),
                    "normal_range": [round(lo, 1), round(hi, 1)],
                    "ens_mean_corrected": None if ens_mean is None else round(float(ens_mean), 1),
                    "weights": {k: round(x, 2) for k, x in w.items()},
                    "sources": {k: [round(float(x), 2) for x in p] for k, p in probs.items()},
                    "shrink": alpha,
                }
            # 강수형태: 역학모델 평균을 평년 빈도와 섞는다(통계모델 몫 = 평년)
            sc = clim.snow_climo(tw.center_doy)
            pt = {"p_snow": sc["p_snow"], "rain_days": sc["rain_days"], "snow_days": sc["snow_days"]}
            if dyn:
                wd = 0.6 if tw.lead <= 2 else 0.4
                for k in pt:
                    dm = np.mean([o["ptype"][k] for o in dyn.values()])
                    pt[k] = wd * dm + (1 - wd) * sc[k]
                for s, o in dyn.items():
                    self.store.save_ptype(issue, region, s, tw.lead, tw.start, o["ptype"])
            self.store.save_ptype(issue, region, "combined", tw.lead, tw.start, pt)
            wk["ptype"] = {**{k: round(float(x), 2) for k, x in pt.items()},
                           "climatology": {k: round(x, 2) for k, x in sc.items()}}
            weeks.append(wk)
        return {"weeks": weeks, "dynamical_sources": list(ens_area)}

    # ------------------------------------------------------------ 검증
    def verify(self, until: date | None = None) -> pd.DataFrame:
        cutoff = str(min(until, self.obs_end) if until else self.obs_end)
        pending = self.store.unverified(cutoff)
        n = 0
        for _, f in pending.iterrows():
            r = self.region(f["region"]) if f["region"] in self.cfg.regions else None
            if r is None:
                continue
            ts = pd.Timestamp(f["start"])
            if ts not in r["weekly"].index:
                continue
            obs = r["weekly"].loc[ts]
            if pd.isna(obs[f["var"]]):
                continue
            cdoy = (ts + pd.Timedelta(days=3)).dayofyear
            cat = r["clim"].category(f["var"], cdoy, float(obs[f["var"]]))
            o = onehot(cat)
            p = np.array([f["p0"], f["p1"], f["p2"]])
            self.store.save_verification(dict(
                issue=f["issue"], region=f["region"], source=f["source"], var=f["var"],
                lead=int(f["lead"]), start=f["start"], obs=float(obs[f["var"]]), obs_cat=cat,
                rps=float(rps(p, o)[0]), rps_clim=float(rps(CLIM, o)[0]),
                err=None if pd.isna(f["ens_mean_raw"]) else float(f["ens_mean_raw"] - obs[f["var"]])))
            n += 1
        # 강수형태 검증
        pt = self.store.df("""SELECT p.* FROM ptype p LEFT JOIN ptype_verification v
            USING(issue, region, source, lead) WHERE v.issue IS NULL
            AND date(p.start, '+6 day') <= date(?)""", (cutoff,))
        for _, f in pt.iterrows():
            if f["region"] not in self.cfg.regions:
                continue
            w = self.region(f["region"])["weekly"]
            ts = pd.Timestamp(f["start"])
            if ts not in w.index:
                continue
            ob = w.loc[ts]
            self.store.save_ptype_verification(dict(
                issue=f["issue"], region=f["region"], source=f["source"], lead=int(f["lead"]),
                start=f["start"], p_snow=float(f["p_snow"]), obs_snow=int(ob["snow_days"] >= 1),
                obs_snow_days=float(ob["snow_days"]), obs_rain_days=float(ob["rain_days"])))
        self.store.commit()
        log.info("검증 완료: %d 건", n)
        summ = self.store.summary()
        if not summ.empty:
            summ.to_csv(self.cfg.path("reports") / "verification_summary.csv", index=False)
        return summ

    # ------------------------------------------------------------ 저장
    def save_result(self, result: dict) -> str:
        out = self.cfg.path("reports") / f"forecast_{result['issue']}.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(out)
