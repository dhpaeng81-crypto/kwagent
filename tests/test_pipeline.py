"""합성 자료로 전체 흐름(학습→예측→검증→보고서)을 시험. 네트워크 불필요."""
from datetime import date, timedelta
from pathlib import Path
import shutil

import numpy as np
import pytest
import yaml

from kwagent.agent import Agent
from kwagent.calendar import target_weeks
from kwagent.cli import publish
from kwagent.config import load_config
from kwagent.data.indices import parse_nino34, parse_rmm
from kwagent.models.combine import to_display
from kwagent.verify import rpss

ROOT = Path(__file__).resolve().parents[1]


def test_calendar_matches_kma_example():
    # 기상청 2026-10-22(목) 발표 1개월전망 → 11/02 ~ 11/29
    w = target_weeks(date(2026, 10, 22))
    assert w[0].start == date(2026, 11, 2) and w[-1].end == date(2026, 11, 29)


def test_display_rounding():
    assert sum(to_display(np.array([0.27, 0.36, 0.37]))) == 100
    assert to_display(np.array([0.2, 0.4, 0.4])) == [20, 40, 40]


def test_rpss_perfect_and_climo():
    o = np.eye(3)[[0, 1, 2]]
    assert rpss(o, o) == pytest.approx(1.0)
    assert rpss(np.full((3, 3), 1 / 3), o) == pytest.approx(0.0)


def test_index_parsers():
    n = parse_nino34(" 03JAN1990     23.4-0.4     25.1-0.3     26.6 0.0     28.6 0.1\n"
                     " 10JAN1990     23.4-0.8     25.2-0.3     26.6 0.1     28.6 0.1\n")
    assert n.iloc[-1] == pytest.approx(0.1)
    r = parse_rmm("1974 6 1 1.63447 1.20304 3 2.02948 Final_value\n")
    assert r.iloc[0]["rmm1"] == pytest.approx(1.63447)


@pytest.fixture()
def cfg(tmp_path):
    raw = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    raw["train_start_year"] = 2008
    raw["regions_active"] = ["korea", "central", "honam", "yeongnam"]
    raw["narrative"]["enabled"] = False
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    return load_config(tmp_path / "config.yaml")


def test_end_to_end_offline(cfg):
    start, end = date(2025, 1, 2), date(2025, 2, 27)
    agent = Agent(cfg, offline=True, asof=end + timedelta(days=40))
    rep = agent.train(end=start - timedelta(days=1))
    assert set(rep["region"]) == {"korea", "central", "honam", "yeongnam"}
    issue = start
    while issue <= end:
        agent.verify(until=issue - timedelta(days=5))
        result = agent.forecast(issue)
        issue += timedelta(days=7)
    summ = agent.verify()
    assert {"statistical", "ec46", "gefs", "combined"} <= set(summ["source"])
    for region in ("korea", "central", "honam", "yeongnam"):
        for wk in result["regions"][region]["weeks"]:
            for v in ("temp", "cloud", "precip"):
                assert sum(wk["vars"][v]["prob"]) == pytest.approx(1, abs=2e-3)
                assert sum(wk["vars"][v]["display"]) == 100
            assert 0 <= wk["ptype"]["p_snow"] <= 1
    out = publish(agent, result)
    md = Path(out["markdown"]).read_text(encoding="utf-8")
    assert "중부" in md and "호남" in md and "경상" in md and "강수형태" in md
    assert all(Path(p).exists() for p in out["png"])

    from kwagent import site
    s = Path(site.build(cfg, agent.store))
    for name in ("index.html", "month.html", "archive.html", "verification.html", "img/verification.png",
                 f"f/{result['issue']}.html", "apple-touch-icon.png", "icon-512.png", "manifest.webmanifest"):
        assert (s / name).exists(), name
    month = (s / "month.html").read_text(encoding="utf-8")
    assert "data-r='honam'" in month and "m-yeongnam-temp" in month and "m-korea-temp" in month and "month.js" in month
    assert '../chart.umd.min.js' in (s / "f" / f"{result['issue']}.html").read_text(encoding="utf-8")
    import pandas as pd
    xl = pd.read_excel(s / f"forecast_{result['issue']}.xlsx", sheet_name=None)
    assert {"전국 확률", "전국 강수형태", "중부 확률", "호남 확률", "경상 강수형태", "설명"} <= set(xl) and len(xl["전국 강수형태"]) == 4
    index = (s / "index.html").read_text(encoding="utf-8")
    assert "2주 일별 예측" in index and 'rel="apple-touch-icon"' in index
    # 저작권·AI 수집 거부
    assert 'content="index, follow, noai, noimageai"' in index and 'tdm-reservation' in index and "All rights reserved" in index
    assert 'class="rf"' in index and 'name="kw-built"' in index and (s / "version.json").exists()   # 새로고침 버튼
    assert (s / "terms.html").exists() and "TDM" in (s / "terms.html").read_text(encoding="utf-8")
    robots = (s.parent / "site_root" / "robots.txt").read_text(encoding="utf-8")
    assert "User-agent: GPTBot" in robots and "User-agent: ClaudeBot" in robots and "Allow: /" in robots
    assert (s.parent / "site_root" / ".well-known" / "tdmrep.json").exists()
    assert "저작권" in pd.read_excel(s / f"forecast_{result['issue']}.xlsx", sheet_name=None)
