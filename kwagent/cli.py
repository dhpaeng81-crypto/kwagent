"""명령행 진입점.

  kwagent backfill              # ERA5 과거 자료 이어 받기 (무료 한도에 걸리면 받은 데까지 저장)
  kwagent train                 # 1991~ 자료 수집 + 통계모델 학습 (최초 1회, 이후 분기마다)
  kwagent run                   # 매주 목요일: 지난 예측 검증 → 이번 주 예측 → 보고서·해설
  kwagent forecast --issue 2026-11-19
  kwagent verify
  kwagent backtest --start 2024-01-04 --end 2025-12-25   # 과거 재현 (실자료는 통계모델만)
  kwagent status                # 예측원별 검증 성적표
  kwagent doctor                # 실제 자료원(ERA5·EC46·GEFS·지수) 연결과 형식 점검
  kwagent site                  # reports/ + 검증 기록 → site/ 정적 웹사이트 (GitHub Pages)

  --offline : 합성 자료로 전체 흐름 시험 (네트워크 불필요)
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import date, timedelta

import pandas as pd

from .agent import Agent
from .calendar import issue_dates_between, latest_issue_date
from .config import load_config
from . import narrative, report


def _d(s: str) -> date:
    return date.fromisoformat(s)


def publish(agent: Agent, result: dict) -> dict:
    cfg = agent.cfg
    out = cfg.path("reports")
    md = report.to_markdown(result)
    summ = agent.store.summary()
    verif = []
    if not summ.empty:
        verif = summ[summ["source"] == "combined"].to_dict("records")
    result["narrative"] = narrative.write(result, cfg, verif)
    agent.save_result(result)
    md += "\n" + result["narrative"] + "\n"
    if verif:
        md += "\n## 검증 현황 (combined)\n\n" + pd.DataFrame(verif).to_markdown(index=False) + "\n"
    p = out / f"forecast_{result['issue']}.md"
    p.write_text(md, encoding="utf-8")
    pngs = report.plot(result, out)
    return {"markdown": str(p), "png": pngs}


def _backfill(agent: Agent) -> bool:
    """ERA5 과거 자료를 받을 수 있는 만큼 받는다. 다 받았으면 True.

    GitHub Actions 에서는 결과를 GITHUB_OUTPUT 의 complete=true/false 로 남긴다.
    """
    import os
    from .data import openmeteo as om
    from .regions import POINTS
    complete = True
    minutes = float(os.environ.get("KWAGENT_BACKFILL_MINUTES", "0") or 0)
    if minutes > 0:
        import time
        om.DEADLINE = time.time() + minutes * 60
    if not agent.offline:
        try:
            agent.obs()
        except om.QuotaError as e:
            complete = False
            logging.warning("Open-Meteo 무료 한도 도달 — 받은 데까지 저장, 다음 실행에서 이어 받음 (%s)", e)
        start = date(min(agent.cfg["train_start_year"], agent.cfg["normal_period"][0]) - 1, 12, 1)
        prog = om.archive_progress(POINTS, start, agent.cfg.path("era5"))
        done = sum(1 for v in prog.values() if v and v >= f"{agent.obs_end - timedelta(days=15)}")
        print(f"ERA5 과거 자료: {done}/{len(prog)} 지점 완료")
        for k, v in prog.items():
            print(f"  {k:<6} {v or '아직 없음'}")
        complete = complete and done == len(prog)
    gh = os.environ.get("GITHUB_OUTPUT")
    if gh:
        with open(gh, "a") as f:
            f.write(f"complete={'true' if complete else 'false'}\n")
    print("완료" if complete else "미완료 — 다음 실행에서 이어 받습니다")
    return complete


def main(argv=None):
    ap = argparse.ArgumentParser(prog="kwagent")
    ap.add_argument("command", choices=["backfill", "train", "run", "forecast", "verify", "backtest", "status",
                                        "site", "doctor"])
    ap.add_argument("--config", default=None)
    ap.add_argument("--issue", type=_d)
    ap.add_argument("--asof", type=_d, help="기준일(기본: 어제)")
    ap.add_argument("--start", type=_d)
    ap.add_argument("--end", type=_d)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    cfg = load_config(a.config)

    if a.command == "backtest":
        if not (a.start and a.end):
            ap.error("backtest 에는 --start, --end 필요")
        agent = Agent(cfg, offline=a.offline, asof=a.end + timedelta(days=40))
        # 누설 방지: 백테스트 시작 전 자료로만 학습
        print(agent.train(end=a.start - timedelta(days=1)).to_string(index=False))
        for issue in issue_dates_between(a.start, a.end, cfg["issue_weekday"]):
            agent.verify(until=issue - timedelta(days=5))   # 발표 시점에 알 수 있던 검증만 반영
            agent.forecast(issue)
            logging.info("backtest 발표 %s 완료", issue)
        summ = agent.verify()
        print(summ.to_string(index=False))
        return

    agent = Agent(cfg, offline=a.offline, asof=a.asof)
    if a.command == "backfill":
        _backfill(agent)
        return
    if a.command == "train":
        print(agent.train().to_string(index=False))
    elif a.command == "verify":
        print(agent.verify().to_string(index=False))
    elif a.command == "status":
        print(agent.store.summary().to_string(index=False))
    elif a.command == "doctor":
        from . import doctor
        for line in doctor.run(cfg):
            print(line)
        for w in ("ec46", "gefs"):
            try:
                print(w, doctor.raw_sample(cfg, w))
            except Exception as e:
                print(w, "raw 확인 실패:", e)
    elif a.command == "site":
        from . import site
        print(site.build(cfg, agent.store))
    elif a.command in ("forecast", "run"):
        if a.command == "run":
            agent.verify()
        issue = a.issue or latest_issue_date(agent.asof + timedelta(days=1), cfg["issue_weekday"])
        result = agent.forecast(issue)
        print(json.dumps(publish(agent, result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
