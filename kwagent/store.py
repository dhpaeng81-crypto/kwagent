"""예측·검증 기록 저장소 (SQLite). 정확도 개선 루프의 기억 장치."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

SCHEMA = """
CREATE TABLE IF NOT EXISTS forecasts(
  issue TEXT, region TEXT, source TEXT, var TEXT, lead INT, start TEXT,
  p0 REAL, p1 REAL, p2 REAL, ens_mean_raw REAL,
  PRIMARY KEY(issue, region, source, var, lead));
CREATE TABLE IF NOT EXISTS ptype(
  issue TEXT, region TEXT, source TEXT, lead INT, start TEXT,
  p_snow REAL, rain_days REAL, snow_days REAL,
  PRIMARY KEY(issue, region, source, lead));
CREATE TABLE IF NOT EXISTS verification(
  issue TEXT, region TEXT, source TEXT, var TEXT, lead INT, start TEXT,
  obs REAL, obs_cat INT, rps REAL, rps_clim REAL, err REAL,
  PRIMARY KEY(issue, region, source, var, lead));
CREATE TABLE IF NOT EXISTS ptype_verification(
  issue TEXT, region TEXT, source TEXT, lead INT, start TEXT,
  p_snow REAL, obs_snow INT, obs_snow_days REAL, obs_rain_days REAL,
  PRIMARY KEY(issue, region, source, lead));
CREATE TABLE IF NOT EXISTS daily_forecasts(
  issue TEXT, region TEXT, source TEXT, date TEXT, lead INT, var TEXT,
  mean REAL, mean_raw REAL, q10 REAL, q50 REAL, q90 REAL, pop REAL, p_snow REAL,
  normal REAL, pop_normal REAL, n INT,
  PRIMARY KEY(issue, region, source, date, var));
CREATE TABLE IF NOT EXISTS daily_verification(
  issue TEXT, region TEXT, source TEXT, date TEXT, lead INT, var TEXT,
  obs REAL, mean_raw REAL, err REAL, abs_err REAL, clim_abs_err REAL, in_band INT,
  brier REAL, clim_brier REAL,
  PRIMARY KEY(issue, region, source, date, var));
"""


class Store:
    def __init__(self, path: Path):
        self.con = sqlite3.connect(path)
        self.con.executescript(SCHEMA)

    def _upsert(self, table: str, row: dict):
        cols = ",".join(row)
        q = ",".join("?" * len(row))
        self.con.execute(f"INSERT OR REPLACE INTO {table}({cols}) VALUES({q})", list(row.values()))

    def save_forecast(self, issue, region, source, var, lead, start, prob, ens_mean_raw=None):
        self._upsert("forecasts", dict(issue=str(issue), region=region, source=source, var=var,
                                       lead=int(lead), start=str(start), p0=float(prob[0]),
                                       p1=float(prob[1]), p2=float(prob[2]),
                                       ens_mean_raw=None if ens_mean_raw is None else float(ens_mean_raw)))

    def save_ptype(self, issue, region, source, lead, start, pt: dict):
        self._upsert("ptype", dict(issue=str(issue), region=region, source=source, lead=int(lead),
                                   start=str(start), **{k: float(v) for k, v in pt.items()}))

    def save_verification(self, row: dict):
        self._upsert("verification", row)

    def save_ptype_verification(self, row: dict):
        self._upsert("ptype_verification", row)

    def save_daily(self, row: dict):
        self._upsert("daily_forecasts", row)

    def save_daily_verification(self, row: dict):
        self._upsert("daily_verification", row)

    def commit(self):
        self.con.commit()

    def df(self, sql: str, params=()) -> pd.DataFrame:
        return pd.read_sql_query(sql, self.con, params=params)

    def unverified(self, until: str) -> pd.DataFrame:
        return self.df("""SELECT f.* FROM forecasts f LEFT JOIN verification v
            USING(issue, region, source, var, lead)
            WHERE v.issue IS NULL AND date(f.start, '+6 day') <= date(?)""", (until,))

    def recent_verif(self, region, source, var, lead, n=52) -> pd.DataFrame:
        return self.df("""SELECT v.*, f.p0, f.p1, f.p2, f.ens_mean_raw FROM verification v
            JOIN forecasts f USING(issue, region, source, var, lead)
            WHERE region=? AND source=? AND var=? AND lead=? ORDER BY issue DESC LIMIT ?""",
                       (region, source, var, int(lead), n))

    def bias(self, region, source, var, lead, month: int | None = None, n=52) -> float | None:
        """역학모델 편향: 기온·운량 = 평균(예측−관측), 강수 = 관측합/예측합 비율."""
        d = self.recent_verif(region, source, var, lead, n).dropna(subset=["ens_mean_raw", "obs"])
        if month is not None and len(d) >= 20:   # 자료가 충분하면 같은 계절(±1개월)만
            m = pd.to_datetime(d["start"]).dt.month
            sel = ((m - month) % 12).isin([0, 1, 11])
            if sel.sum() >= 8:
                d = d[sel]
        if len(d) < 4:
            return None
        if var == "precip":
            s = d["ens_mean_raw"].sum()
            return float(d["obs"].sum() / s) if s > 0 else None
        return float((d["ens_mean_raw"] - d["obs"]).mean())

    def summary(self) -> pd.DataFrame:
        d = self.df("SELECT region, source, var, lead, rps, rps_clim FROM verification")
        if d.empty:
            return d
        g = d.groupby(["region", "source", "var", "lead"])
        out = g.agg(n=("rps", "size"), rps=("rps", "mean"), rps_clim=("rps_clim", "mean")).reset_index()
        out["rpss"] = 1 - out["rps"] / out["rps_clim"]
        return out.round(4)


def onehot(cat: int) -> np.ndarray:
    return np.eye(3)[int(cat)]
