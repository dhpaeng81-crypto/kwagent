"""데이터 공급자 인터페이스. 실제(Open-Meteo) / 합성(오프라인 시험용)."""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from ..calendar import today_kst
from ..regions import Point
from . import indices as ix
from . import openmeteo as om

log = logging.getLogger(__name__)


class OpenMeteoProvider:
    name = "openmeteo"

    def __init__(self, cfg, cache_dir):
        self.cfg, self.cache = cfg, cache_dir

    def archive(self, points: list[Point], start: date, end: date) -> pd.DataFrame:
        return om.fetch_archive(points, start, end, self.cfg, self.cfg.path("era5"))

    def indices(self) -> pd.DataFrame:
        return ix.fetch_indices(self.cfg, self.cache)

    def ensemble(self, source: str, points: list[Point], issue: date) -> pd.DataFrame | None:
        # 공개 API 는 '현재' 예측만 준다 → 과거 발표일 재현(백테스트)에는 쓸 수 없음
        if abs((today_kst() - issue).days) > 3:
            return None
        try:
            fn = {"ec46": om.fetch_ec46, "gefs": om.fetch_gefs}[source]
            df = fn(points, self.cfg)
            cache = self.cache / f"{source}_{issue}.csv"
            df.to_csv(cache, index=False)
            return df
        except Exception as e:
            log.warning("%s 수집 실패 — 이 예측원 없이 진행: %s", source, e)
            cache = self.cache / f"{source}_{issue}.csv"
            return pd.read_csv(cache, parse_dates=["date"]) if cache.exists() else None


def make_provider(cfg, cache_dir, offline: bool = False):
    if offline:
        from .synthetic import SyntheticProvider
        return SyntheticProvider(seed=7)
    return OpenMeteoProvider(cfg, cache_dir)


def default_asof() -> date:
    return today_kst() - timedelta(days=1)
