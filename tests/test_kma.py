"""기상청 1개월전망 PDF 글자 읽기 → 권역 묶기 → 저장 (네트워크 불필요, 2026-11-19 실제 발표 글자 사용)."""
from datetime import date
from pathlib import Path

import pytest

from kwagent import kma

TEXT = (Path(__file__).parent / "data" / "kma_20261119.txt").read_text(encoding="utf-8")


def test_parse_tables():
    p = kma.parse(TEXT)
    assert p["issue"] == date(2026, 11, 19)
    assert p["weeks"][0] == (date(2026, 11, 30), date(2026, 12, 6))
    assert p["weeks"][3] == (date(2026, 12, 21), date(2026, 12, 27))
    t = p["rows"]["temp"]
    assert t["전국(제주도,북한제외)"][0] == (2.2, 4.0, 10, 40, 50)
    assert t["강원도 영서"][2] == (-4.7, -1.9, 20, 50, 30)
    assert p["rows"]["precip"]["전북자치도"][1] == (4.1, 11.0, 10, 40, 50)
    assert len(t) == 13 and len(p["rows"]["precip"]) == 13


def test_regions_weighted():
    r = kma.to_regions(kma.parse(TEXT))
    assert set(r) == {"korea", "central", "honam", "yeongnam"}
    assert r["korea"]["temp"][0] == pytest.approx([0.1, 0.4, 0.5])
    # 중부 2주 기온: 서울경기(3)·영서(2)·영동(1) 은 20/50/30, 충남(2)·충북(2) 은 20/40/40 → 비중 평균
    c = r["central"]["temp"][1]
    assert c == pytest.approx([0.2, (6 * 0.5 + 4 * 0.4) / 10, (6 * 0.3 + 4 * 0.4) / 10])
    for reg in r.values():
        for probs in reg.values():
            for p in probs:
                assert sum(p) == pytest.approx(1)


def test_save(tmp_path):
    from kwagent.store import Store
    s = Store(tmp_path / "s.sqlite")
    n = kma.save(s, kma.parse(TEXT), ["korea", "central", "honam", "yeongnam"])
    assert n == 4 * 2 * 4
    d = s.df("SELECT * FROM forecasts WHERE source='kma' AND region='honam' AND var='precip' AND lead=1")
    assert d.iloc[0]["start"] == "2026-11-30" and d.iloc[0]["p2"] == pytest.approx(0.5)
