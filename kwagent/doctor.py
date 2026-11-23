"""실제 자료원 점검: 각 API 를 소량 호출해 형식·멤버 수·결측을 보고한다.

처음 네트워크 환경에서 실행할 때, 그리고 실패 로그가 나왔을 때 가장 먼저 돌린다.
  kwagent doctor
"""
from __future__ import annotations

from datetime import timedelta

import pandas as pd
import requests

from .calendar import today_kst
from .data import indices as ix
from .data import openmeteo as om
from .regions import POINTS


def _line(ok: bool, name: str, msg: str) -> str:
    return f"[{'OK ' if ok else 'ERR'}] {name:<10} {msg}"


def run(cfg) -> list[str]:
    out = []
    cache = cfg.path("cache")
    seoul = [POINTS[0]]
    end = today_kst() - timedelta(days=1)
    try:
        df = om.fetch_archive(seoul, end - timedelta(days=20), end, cfg, cache)
        last = df.dropna(subset=["temp"])["date"].max()
        nan = df[["temp", "cloud", "srad", "precip", "rain"]].isna().mean().round(2).to_dict()
        out.append(_line(not df.empty, "ERA5", f"{len(df)}일, 마지막 자료 {last:%Y-%m-%d}, 결측률 {nan}"))
    except Exception as e:
        out.append(_line(False, "ERA5", str(e)[:300]))
    for name, fn in (("EC46", om.fetch_ec46), ("GEFS", om.fetch_gefs)):
        try:
            df = fn(POINTS[:2], cfg)
            nm = df["member"].nunique()
            span = f"{df['date'].min():%m-%d}~{df['date'].max():%m-%d}"
            nan = df[["temp", "cloud", "srad", "precip", "rain"]].isna().mean().round(2).to_dict()
            out.append(_line(nm >= 10, name, f"멤버 {nm}개, 기간 {span}, 지점 {df['point'].nunique()}, 결측률 {nan}"))
        except Exception as e:
            out.append(_line(False, name, str(e)[:300]))
    src = cfg["sources"]["indices"]
    for key, parser in (("nino34", ix.parse_nino34), ("ao", ix.parse_ao), ("mjo", ix.parse_rmm)):
        url = src[f"{key}_url"]
        try:
            r = requests.get(url, timeout=60, headers=ix.HEADERS)
            r.raise_for_status()
            s = parser(r.text)
            last = s.index.max() if len(s) else None
            if last is None:
                out.append(_line(False, key, "파싱 결과 0행 — 형식 확인 필요"))
                continue
            age = (pd.Timestamp(today_kst()) - last).days
            max_age = ix._PRED_SPEC["rmm1" if key == "mjo" else key][1]
            msg = f"{len(s)}행, 마지막 {last:%Y-%m-%d} ({age}일 전)"
            if age > max_age:
                msg += f" — {max_age}일보다 오래됨: 예측에서 0(평년)으로 처리"
            out.append(_line(len(s) > 100 and age <= max_age, key, msg))
        except Exception as e:
            out.append(_line(False, key, f"{url}: {str(e)[:200]}"))
    return out


def raw_sample(cfg, which: str = "ec46") -> str:
    """API 원본 JSON 의 daily 키 목록 (멤버 이름 규칙 확인용)."""
    o = cfg["sources"]["openmeteo"]
    url, model, days = {"ec46": (o["seasonal_url"], o["ec46_model"], 46),
                        "gefs": (o["ensemble_url"], o["gefs_model"], 35)}[which]
    p = POINTS[0]
    r = requests.get(url, params={"latitude": p.lat, "longitude": p.lon, "models": model,
                                  "daily": ",".join(om.DAILY_VARS), "forecast_days": days,
                                  "timezone": o["timezone"]}, timeout=120)
    js = r.json()
    keys = list(js.get("daily", {}).keys()) if isinstance(js, dict) else "list"
    return f"HTTP {r.status_code}; daily keys({len(keys)}): {keys[:12]} ... ; error={js.get('reason') if isinstance(js, dict) else ''}"
