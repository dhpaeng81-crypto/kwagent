"""ERA5 나눠 받기: 1년 조각, 한도 초과 시 받은 데까지 저장 후 다음에 이어 받기."""
from datetime import date

import pandas as pd
import pytest

from kwagent.data import openmeteo as om
from kwagent.regions import POINTS


def _fake_daily(params):
    d = pd.date_range(params["start_date"], params["end_date"], freq="D")
    n = len(d)
    return {"daily": {"time": [x.strftime("%Y-%m-%d") for x in d],
                      "temperature_2m_mean": [10.0] * n, "cloud_cover_mean": [50.0] * n,
                      "precipitation_sum": [1.0] * n, "rain_sum": [1.0] * n,
                      "snowfall_sum": [0.0] * n}}


def test_chunked_resume(tmp_path, monkeypatch):
    monkeypatch.setattr(om.time, "sleep", lambda s: None)
    cfg = {"sources": {"openmeteo": {"archive_url": "x", "timezone": "Asia/Seoul"}}}
    calls = []

    def fake_get(url, params, **kw):
        calls.append((params["start_date"], params["end_date"]))
        if len(calls) == 3:
            raise om.QuotaError("Hourly API request limit exceeded")
        return [_fake_daily(params)]

    monkeypatch.setattr(om, "_get", fake_get)
    pts = POINTS[:1]
    start, end = date(2020, 12, 1), date(2023, 3, 10)
    with pytest.raises(om.QuotaError):
        om.fetch_archive(pts, start, end, cfg, tmp_path)
    assert calls[0] == ("2020-12-01", "2020-12-31")
    assert calls[1] == ("2021-01-01", "2021-12-31")
    saved = pd.read_csv(om.archive_file(tmp_path, pts[0]), parse_dates=["date"])
    assert saved["date"].max() == pd.Timestamp("2021-12-31")      # 받은 데까지 저장됨
    assert om.archive_progress(pts, start, tmp_path)[pts[0].name] == "2021-12-31"

    calls.clear()
    monkeypatch.setattr(om, "_get", lambda url, params, **kw: (calls.append(params["start_date"]),
                                                              [_fake_daily(params)])[1])
    df = om.fetch_archive(pts, start, end, cfg, tmp_path)
    assert calls[0] == "2021-12-22"                                  # 이어 받기(10일 겹침)
    assert df["date"].min() == pd.Timestamp(start) and df["date"].max() == pd.Timestamp(end)
    assert df["date"].is_unique
