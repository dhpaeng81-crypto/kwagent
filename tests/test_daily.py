"""2주 일별 예측: 합성 자료로 예측 → 채점 → 편향 보정 → 보고서·웹사이트. 네트워크 불필요."""
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml

from kwagent import daily
from kwagent.agent import Agent
from kwagent.config import load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def cfg(tmp_path):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["regions_active"] = ["korea", "central", "honam"]
    raw["narrative"]["enabled"] = False
    raw["daily"]["bias_min_n"] = 4
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return load_config(tmp_path / "config.yaml")


def test_wquantile():
    x = np.arange(101, dtype=float)
    assert daily.wquantile(x, np.ones(101), [0.1, 0.5, 0.9]) == pytest.approx([10, 50, 90], abs=0.6)


def test_daily_end_to_end(cfg):
    first = date(2025, 1, 6)
    agent = Agent(cfg, offline=True, asof=first + timedelta(days=60))
    obs = daily._obs(agent)
    issues = [first + timedelta(days=i) for i in range(12)]
    for issue in issues:
        daily.verify(agent, until=issue - timedelta(days=5), obs=obs)
        result = daily.forecast(agent, issue, obs=obs)
    days = result["regions"]["korea"]["days"]
    assert len(days) == 14 and days[0]["date"] == str(issues[-1] + timedelta(days=1))
    assert set(days[0]["models"]) == {"ecmwf_ens", "ecmwf_aifs", "gefs", "icon_eps"}
    assert set(days[10]["models"]) == {"ecmwf_ens", "ecmwf_aifs", "gefs"}       # ICON 은 7일까지
    for d in days:
        for var in daily.DVARS:
            v = d["vars"][var]
            assert v["q10"] <= v["q50"] <= v["q90"]
            assert v["normal"] is not None
        assert 0 <= d["vars"]["precip"]["pop"] <= 1
        assert 0 <= d["vars"]["precip"]["p_snow"] <= 1
        assert sum(d["vars"]["cloud"]["sky"].values()) == pytest.approx(1, abs=0.02)
        assert d["vars"]["tmin"]["q50"] < d["vars"]["tmax"]["q50"]

    # 채점이 쌓이면 모델 편향을 알아내 보정한다 (합성 GEFS 는 −0.9°C 편향)
    assert daily.verify(agent, obs=obs) > 0
    b = daily._bias(agent.store, "korea", "gefs", "temp", 2, 60, 4)
    assert b == pytest.approx(-0.9, abs=0.6)
    s = daily.summary(agent.store)
    comb = s[(s["source"] == "combined") & (s["var"] == "temp") & (s["region"] == "korea")]
    assert set(comb["bin"]) == {"1~3일", "4~7일", "8~14일"}
    near = comb.set_index("bin").loc["1~3일"]
    assert near["skill"] > 0.3                                             # 1~3일은 평년보다 훨씬 나음

    out = daily.publish(agent, result)
    assert all(Path(p).exists() for p in out["png"])
    from kwagent import site
    s = Path(site.build(cfg, agent.store))
    html = (s / "daily.html").read_text(encoding="utf-8")
    assert "2주 일별 예측" in html and "class='strip'" in html and "<details class='drow" in html and "data-r='honam'" in html
    assert (s / "img" / f"daily_{result['issue']}_korea.png").exists()
    assert "c-korea-temp" in html and "daily.js" in html and (s / "chart.umd.min.js").exists()
    import pandas as pd
    xl = pd.read_excel(s / f"daily_{result['issue']}.xlsx", sheet_name=None)
    assert {"전국", "중부", "호남", "설명"} <= set(xl) and len(xl["전국"]) == 14 and "최고기온(°C)" in xl["전국"]
    vh = (s / "verification.html").read_text(encoding="utf-8")
    assert "2주 일별 예측" in vh and "v-daily-skill-honam" in vh and "verify.js" in vh
    vx = pd.read_excel(s / "verification.xlsx", sheet_name=None)
    assert "2주 일별 정확도" in vx and len(vx["2주 일별 정확도"]) > 10
