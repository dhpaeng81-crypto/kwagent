"""단기 2주 일별 예측: 기온(평균·최고·최저)·운량·일사량·강수(비/눈).

흐름: 여러 앙상블(ECMWF IFS·AIFS, GEFS, ICON) → 영역평균 → 모델별 편향보정(운영 채점 기록)
      → 모델 가중 혼합 → 날짜별 10/50/90% 범위, 강수확률, 눈 확률, 하늘상태 확률 → 평년과 비교.
매일 실행하면서 지난 예측을 ERA5 로 채점하고(daily_verification), 그 기록으로 다음 예측의 편향을 고친다.

1단계(현재): 위 흐름. 2단계(예정): Open-Meteo 과거 예측(Historical Forecast)으로 첫날부터 보정,
퍼짐 보정(EMOS), 채점 성적에 따른 모델 가중치 자동 조절.
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .calendar import today_kst
from .features import classify_day
from .regions import POINTS, REGION_LABELS, points_for

log = logging.getLogger(__name__)

DVARS = ("temp", "tmax", "tmin", "cloud", "srad", "precip")
DLABEL = {"temp": ("평균기온", "°C"), "tmax": ("최고기온", "°C"), "tmin": ("최저기온", "°C"),
          "cloud": ("운량", "%"), "srad": ("일사량", "MJ/m²"), "precip": ("강수량", "mm")}
MODEL_LABEL = {"ecmwf_ens": "ECMWF 앙상블", "ecmwf_aifs": "ECMWF AI 앙상블", "gefs": "NOAA GEFS",
               "icon_eps": "DWD ICON 앙상블", "combined": "최종(결합)"}
# 하늘상태: 기상청 기준(운량 0~5할 맑음, 6~8할 구름많음, 9~10할 흐림)을 % 로
SKY = (("맑음", 0, 55), ("구름많음", 55, 85), ("흐림", 85, 101))
WEEKDAY = "월화수목금토일"


# ---------------------------------------------------------------- 도구
def region_daily(df: pd.DataFrame, region: str, wet_mm: float = 1.0, snow_thr: float = 0.5) -> pd.DataFrame:
    """지점 → 영역평균. wet/snowd = 비(눈) 온 지점의 비율 → 강수확률·눈 확률은 '평균적인 지점' 기준."""
    names = {p.name for p in points_for(region)}
    sub = df[df["point"].isin(names)].copy()
    cols = [c for c in (*DVARS, "rain") if c in sub]
    if "precip" in sub:
        valid = sub["precip"].notna()
        sub["wet"] = (sub["precip"] >= wet_mm).astype(float).where(valid)
        if "rain" in sub:
            _, sd = classify_day(sub["precip"], sub["rain"].fillna(sub["precip"]), wet_mm, snow_thr)
            sub["snowd"] = sd.astype(float).where(valid)
            cols.append("snowd")
        cols.append("wet")
    return sub.groupby(["member", "date"])[cols].mean().reset_index()


def wquantile(x: np.ndarray, w: np.ndarray, qs) -> np.ndarray:
    o = np.argsort(x)
    x, w = x[o], w[o]
    c = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(qs, c, x)


def day_label(d: date) -> str:
    return f"{d.month}.{d.day}({WEEKDAY[d.weekday()]})"


def daily_normals(obs_region: pd.DataFrame, period, wet_mm: float) -> pd.DataFrame:
    """1991~2020 일별 평년(연중일, 31일 이동평균). precip 은 평년 강수확률 pop 도."""
    d = obs_region[obs_region["member"] == -1].set_index("date")
    d = d[(d.index.year >= period[0]) & (d.index.year <= period[1])]
    cols = [c for c in DVARS if c in d and d[c].notna().any()]
    if d.empty or not cols:
        return pd.DataFrame()
    g = d[cols].copy()
    if "wet" in d:
        g["pop"] = d["wet"]
    doy = g.groupby(g.index.dayofyear).mean().reindex(range(1, 367)).interpolate(limit_direction="both")
    ext = pd.concat([doy.tail(15), doy, doy.head(15)])
    return ext.rolling(31, center=True).mean().iloc[15:-15]


def _bias(store, region, source, var, lead, window: int, min_n: int) -> float | None:
    d = store.df("""SELECT mean_raw, obs FROM daily_verification
        WHERE region=? AND source=? AND var=? AND lead BETWEEN ? AND ? AND mean_raw IS NOT NULL
        ORDER BY date DESC LIMIT ?""", (region, source, var, lead - 1, lead + 1, window))
    if len(d) < min_n:
        return None
    if var == "precip":
        s = d["mean_raw"].sum()
        return float(np.clip(d["obs"].sum() / s, 0.5, 2.0)) if s > 1.0 else None
    return float((d["mean_raw"] - d["obs"]).mean())


def _correct(x: np.ndarray, var: str, b: float | None) -> np.ndarray:
    if b is None:
        return x
    if var == "precip":
        return x * b
    y = x - b
    if var == "cloud":
        return np.clip(y, 0, 100)
    if var == "srad":
        return np.clip(y, 0, None)
    return y


# ---------------------------------------------------------------- 예측
def _summarise(vals: np.ndarray, w: np.ndarray, var: str, wet: np.ndarray | None = None) -> dict:
    q10, q50, q90 = wquantile(vals, w, (0.1, 0.5, 0.9))
    out = {"mean": float(np.average(vals, weights=w)), "q10": float(q10), "q50": float(q50),
           "q90": float(q90)}
    if var == "precip" and wet is not None:
        out["pop"] = float(np.average(wet, weights=w))
    if var == "cloud":
        out["sky"] = {name: float(np.average((vals >= lo) & (vals < hi), weights=w)) for name, lo, hi in SKY}
    return out


def forecast(agent, issue: date | None = None, obs: pd.DataFrame | None = None) -> dict:
    cfg, store = agent.cfg, agent.store
    dc = cfg["daily"]
    issue = issue or today_kst()
    ndays = int(dc["days"])
    wet_mm, snow_thr = agent.wet_mm, agent.snow_thr
    ens = {}
    for name, spec in dc["models"].items():
        try:
            df = agent.provider.short_ensemble(name, spec, POINTS, issue)
        except Exception as e:  # pragma: no cover - network
            log.warning("%s(단기) 실패: %s", name, e)
            df = None
        if df is not None and not df.empty:
            ens[name] = df
        log.info("단기 %s: %s", name, "없음" if df is None or df.empty else f"{df['member'].nunique()} 멤버")
    obs = _obs(agent) if obs is None else obs
    result = {"issue": str(issue), "generated": str(today_kst()), "kind": "daily",
              "models": {k: int(v["member"].nunique()) for k, v in ens.items()}, "regions": {}}
    for region in cfg.regions:
        normals = daily_normals(region_daily(obs, region, wet_mm, snow_thr), tuple(cfg["normal_period"]), wet_mm) \
            if obs is not None and not obs.empty else pd.DataFrame()
        areas = {k: region_daily(v, region, wet_mm, snow_thr) for k, v in ens.items()}
        days = []
        for lead in range(1, ndays + 1):
            d = issue + timedelta(days=lead)
            ts = pd.Timestamp(d)
            nrm = normals.loc[ts.dayofyear] if not normals.empty else None
            day = {"date": str(d), "lead": lead, "label": day_label(d), "vars": {}, "models": []}
            per_model = {}
            for name, a in areas.items():
                sub = a[a["date"] == ts]
                if len(sub) >= 3:
                    per_model[name] = sub
            if not per_model:
                continue
            day["models"] = list(per_model)
            wsum = sum(float(dc["models"][k]["weight"]) for k in per_model)
            for var in DVARS:
                pooled_v, pooled_w, pooled_wet, raw_means = [], [], [], []
                for name, sub in per_model.items():
                    if var not in sub or sub[var].isna().all():
                        continue
                    ok = sub[var].notna().to_numpy()
                    if ok.sum() < 3:
                        continue
                    raw = sub[var].to_numpy(float)[ok]
                    wet = sub["wet"].to_numpy(float)[ok] if var == "precip" and "wet" in sub else None
                    b = _bias(store, region, name, var, lead, int(dc["bias_window"]), int(dc["bias_min_n"]))
                    vals = _correct(raw, var, b)
                    s = _summarise(vals, np.ones(len(vals)), var, wet)
                    store.save_daily(dict(issue=str(issue), region=region, source=name, date=str(d), lead=lead,
                                          var=var, mean=s["mean"], mean_raw=float(raw.mean()), q10=s["q10"],
                                          q50=s["q50"], q90=s["q90"], pop=s.get("pop"), p_snow=None,
                                          normal=None, pop_normal=None, n=len(vals)))
                    wm = float(dc["models"][name]["weight"]) / wsum
                    if wet is not None:
                        pooled_wet.append(wet)
                    pooled_v.append(vals)
                    pooled_w.append(np.full(len(vals), wm / len(vals)))
                    raw_means.append((wm, float(raw.mean())))
                if not pooled_v:
                    continue
                vals, w = np.concatenate(pooled_v), np.concatenate(pooled_w)
                wet = np.concatenate(pooled_wet) if len(pooled_wet) == len(pooled_v) and pooled_wet else None
                s = _summarise(vals, w, var, wet)
                mean_raw = sum(a * m for a, m in raw_means) / sum(a for a, _ in raw_means)
                normal = float(nrm[var]) if nrm is not None and var in nrm and pd.notna(nrm[var]) else None
                pop_normal = float(nrm["pop"]) if var == "precip" and nrm is not None and "pop" in nrm else None
                p_snow = None
                if var == "precip":
                    snow = []
                    for name, sub in per_model.items():
                        if "snowd" in sub and sub["snowd"].notna().any():
                            wm = float(dc["models"][name]["weight"]) / wsum
                            snow.append((wm, float(sub["snowd"].mean())))
                    if snow:
                        p_snow = sum(a * p for a, p in snow) / sum(a for a, _ in snow)
                        s["p_snow"] = p_snow
                store.save_daily(dict(issue=str(issue), region=region, source="combined", date=str(d), lead=lead,
                                      var=var, mean=s["mean"], mean_raw=mean_raw, q10=s["q10"], q50=s["q50"],
                                      q90=s["q90"], pop=s.get("pop"), p_snow=p_snow, normal=normal,
                                      pop_normal=pop_normal, n=len(vals)))
                s = {k: (round(v, 2) if isinstance(v, float) else
                         {kk: round(vv, 2) for kk, vv in v.items()} if isinstance(v, dict) else v)
                     for k, v in s.items()}
                s["normal"] = None if normal is None else round(normal, 1)
                if pop_normal is not None:
                    s["pop_normal"] = round(pop_normal, 2)
                day["vars"][var] = s
            days.append(day)
        result["regions"][region] = {"days": days}
    store.commit()
    return result


def _obs(agent) -> pd.DataFrame | None:
    """ERA5(정답·평년). 무료 한도에 걸리면 받아 둔 파일만 읽어서 계속 진행."""
    try:
        return agent.obs()
    except Exception as e:
        from .data import openmeteo as om
        log.warning("ERA5 갱신 실패 — 받아 둔 자료로 진행: %s", e)
        try:
            df = om.read_archive(POINTS, agent.cfg.path("era5"))
            return df[df["date"] <= pd.Timestamp(agent.obs_end)] if not df.empty else None
        except Exception:
            return None


# ---------------------------------------------------------------- 채점
def verify(agent, until: date | None = None, obs: pd.DataFrame | None = None) -> int:
    store = agent.store
    cutoff = min(until, agent.obs_end) if until else agent.obs_end
    pend = store.df("""SELECT f.* FROM daily_forecasts f LEFT JOIN daily_verification v
        USING(issue, region, source, date, var) WHERE v.issue IS NULL AND date(f.date) <= date(?)""",
                    (str(cutoff),))
    if pend.empty:
        return 0
    obs = _obs(agent) if obs is None else obs
    if obs is None or obs.empty:
        return 0
    n = 0
    truth = {}
    for _, f in pend.iterrows():
        if f["region"] not in truth:
            t = region_daily(obs, f["region"], agent.wet_mm, agent.snow_thr)
            truth[f["region"]] = t[t["member"] == -1].set_index("date")
        t = truth[f["region"]]
        ts = pd.Timestamp(f["date"])
        if ts not in t.index or f["var"] not in t or pd.isna(t.at[ts, f["var"]]):
            continue
        o = float(t.at[ts, f["var"]])
        row = dict(issue=f["issue"], region=f["region"], source=f["source"], date=f["date"], lead=int(f["lead"]),
                   var=f["var"], obs=o, mean_raw=f["mean_raw"], err=float(f["mean"] - o),
                   abs_err=float(abs(f["q50"] - o)),
                   clim_abs_err=None if pd.isna(f["normal"]) else float(abs(f["normal"] - o)),
                   in_band=int(f["q10"] <= o <= f["q90"]), brier=None, clim_brier=None)
        if f["var"] == "precip" and pd.notna(f["pop"]) and "wet" in t and pd.notna(t.at[ts, "wet"]):
            hit = float(t.at[ts, "wet"])          # 비 온 지점 비율 (0~1)
            row["brier"] = float((f["pop"] - hit) ** 2)
            if pd.notna(f["pop_normal"]):
                row["clim_brier"] = float((f["pop_normal"] - hit) ** 2)
        store.save_daily_verification(row)
        n += 1
    store.commit()
    log.info("일별 채점: %d 건", n)
    return n


LEAD_BINS = ((1, 3, "1~3일"), (4, 7, "4~7일"), (8, 14, "8~14일"))


def summary(store) -> pd.DataFrame:
    d = store.df("SELECT * FROM daily_verification")
    if d.empty:
        return d
    d["bin"] = None
    for lo, hi, name in LEAD_BINS:
        d.loc[d["lead"].between(lo, hi), "bin"] = name
    g = d.groupby(["region", "source", "var", "bin"])
    out = g.agg(n=("obs", "size"), mae=("abs_err", "mean"), mae_clim=("clim_abs_err", "mean"),
                bias=("err", "mean"), cover=("in_band", "mean"), brier=("brier", "mean"),
                brier_clim=("clim_brier", "mean")).reset_index()
    out["skill"] = 1 - out["mae"] / out["mae_clim"]
    out["bss"] = 1 - out["brier"] / out["brier_clim"]
    return out.round(3)


# ---------------------------------------------------------------- 보고서
def to_markdown(result: dict) -> str:
    L = [f"# 2주 일별 예측 (발표 {result['issue']})", "",
         "사용한 모델: " + (", ".join(f"{MODEL_LABEL.get(k, k)} {v}멤버" for k, v in result["models"].items())
                         or "없음"), ""]
    for region, rd in result["regions"].items():
        L += [f"## {REGION_LABELS.get(region, region)}", "",
              "| 날짜 | 최저/최고(°C) | 하늘 | 강수확률 | 강수량(mm) | 눈 | 일사량(MJ/m²) |",
              "|---|---|---|---|---|---|---|"]
        for day in rd["days"]:
            L.append("| " + " | ".join(day_cells(day)) + " |")
        L.append("")
    return "\n".join(L)


def sky_label(c: dict | None) -> str:
    if not c or "sky" not in c:
        return "-"
    return max(c["sky"], key=c["sky"].get)


def num(x: float, nd: int = 0) -> str:
    s = f"{x:.{nd}f}"
    return s[1:] if s.startswith("-") and float(s) == 0 else s


def day_cells(day: dict) -> list[str]:
    v = day["vars"]

    def f(var, key="q50", nd=0):
        return num(v[var][key], nd) if var in v and v[var].get(key) is not None else "-"
    p = v.get("precip", {})
    amount = "-" if not p else (f"{p['q50']:.0f}" if p["q90"] < 1 else f"{p['q50']:.0f}~{p['q90']:.0f}")
    snow = "-" if p.get("p_snow") is None else f"{p['p_snow']*100:.0f}%"
    return [day["label"], f"{f('tmin')} / {f('tmax')}", sky_label(v.get("cloud")),
            "-" if "pop" not in p else f"{p['pop']*100:.0f}%", amount, snow, f("srad", nd=1)]


def plot(result: dict, out_dir) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from .report import _korean_font
    _korean_font()
    paths = []
    for region, rd in result["regions"].items():
        days = rd["days"]
        if not days:
            continue
        x = np.arange(len(days))
        lab = [d["label"].split("(")[0] for d in days]

        def ser(var, key):
            vals = [d["vars"].get(var, {}).get(key) for d in days]
            return np.array([np.nan if v is None else v for v in vals], dtype=float)
        fig, axes = plt.subplots(2, 2, figsize=(12, 6.4), sharex=True)
        ax = axes[0, 0]
        for var, c in (("tmax", "#c9473b"), ("tmin", "#3d6fc4")):
            ax.fill_between(x, ser(var, "q10"), ser(var, "q90"), color=c, alpha=0.18, linewidth=0)
            ax.plot(x, ser(var, "q50"), color=c, lw=2, label=DLABEL[var][0])
            ax.plot(x, ser(var, "normal"), color=c, lw=1, ls="--", alpha=0.7)
        ax.set_title("기온 (°C) — 띠: 10~90% 범위, 점선: 평년")
        ax.legend(fontsize=8, frameon=False)
        ax = axes[0, 1]
        ax.bar(x, ser("precip", "q50"), color="#3f9a6b", width=0.6, label="강수량(중앙)")
        ax.errorbar(x, ser("precip", "q50"), yerr=[np.zeros(len(x)), ser("precip", "q90") - ser("precip", "q50")],
                    fmt="none", ecolor="#2e6e4c", capsize=2, lw=1)
        ax.set_title("강수량 (mm) · 강수확률 (%)")
        ax2 = ax.twinx()
        ax2.plot(x, ser("precip", "pop") * 100, color="#1f4fa8", marker="o", ms=3, lw=1.4)
        ax2.set_ylim(0, 100)
        ax2.spines[["top"]].set_visible(False)
        for ax, var, c in ((axes[1, 0], "cloud", "#56657a"), (axes[1, 1], "srad", "#e08a1e")):
            ax.fill_between(x, ser(var, "q10"), ser(var, "q90"), color=c, alpha=0.2, linewidth=0)
            ax.plot(x, ser(var, "q50"), color=c, lw=2)
            ax.plot(x, ser(var, "normal"), color=c, lw=1, ls="--", alpha=0.7)
            ax.set_title(f"{DLABEL[var][0]} ({DLABEL[var][1]})")
        axes[1, 0].set_ylim(0, 100)
        for ax in axes.flat:
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_xticks(x, lab, fontsize=8, rotation=0)
        fig.suptitle(f"{REGION_LABELS.get(region, region)} 2주 일별 예측 · 발표 {result['issue']}", y=1.0)
        fig.tight_layout()
        p = out_dir / f"daily_{result['issue']}_{region}.png"
        fig.savefig(p, dpi=120, bbox_inches="tight")
        plt.close(fig)
        paths.append(str(p))
    return paths


def publish(agent, result: dict) -> dict:
    out = agent.cfg.path("reports") / "daily"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"daily_{result['issue']}.json").write_text(json.dumps(result, ensure_ascii=False, indent=1),
                                                       encoding="utf-8")
    (out / f"daily_{result['issue']}.md").write_text(to_markdown(result), encoding="utf-8")
    pngs = plot(result, out)
    # 오래된 일별 보고서 정리 (기록은 store 에 모두 남음)
    keep = int(agent.cfg["daily"].get("keep_reports_days", 30))
    old = date.fromisoformat(result["issue"]) - timedelta(days=keep)
    for f in out.glob("daily_*"):
        try:
            if date.fromisoformat(f.name[6:16]) < old:
                f.unlink()
        except ValueError:
            pass
    s = summary(agent.store)
    if not s.empty:
        s.to_csv(agent.cfg.path("reports") / "daily_verification_summary.csv", index=False)
    return {"json": str(out / f"daily_{result['issue']}.json"), "png": pngs}


def run(agent, issue: date | None = None) -> dict:
    obs = _obs(agent)
    verify(agent, obs=obs)
    result = forecast(agent, issue, obs=obs)
    return publish(agent, result)
