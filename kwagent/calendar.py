"""발표일 → 예측 대상 주(週) 계산.

기상청 1개월전망과 같이, 발표일이 속한 주의 '다음다음 주' 월요일부터 4주를 예측한다.
예) 2026-10-22(목) 발표 → 11/02~11/08, 11/09~11/15, 11/16~11/22, 11/23~11/29
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def today_kst() -> date:
    """서버 시간대(GitHub Actions 는 UTC)와 무관하게 한국 날짜."""
    return datetime.now(KST).date()


@dataclass(frozen=True)
class TargetWeek:
    lead: int          # 1..4
    start: date
    end: date

    @property
    def label(self) -> str:
        return f"{self.lead}주 ({self.start:%m.%d}~{self.end:%m.%d})"

    @property
    def center_doy(self) -> int:
        return (self.start + timedelta(days=3)).timetuple().tm_yday


def target_weeks(issue: date, n_weeks: int = 4) -> list[TargetWeek]:
    monday_this = issue - timedelta(days=issue.weekday())
    first = monday_this + timedelta(days=14)
    return [
        TargetWeek(i + 1, first + timedelta(days=7 * i), first + timedelta(days=7 * i + 6))
        for i in range(n_weeks)
    ]


def latest_issue_date(today: date, weekday: int = 3) -> date:
    """오늘 또는 그 이전의 가장 최근 발표일."""
    return today - timedelta(days=(today.weekday() - weekday) % 7)


def issue_dates_between(start: date, end: date, weekday: int = 3) -> list[date]:
    d = start + timedelta(days=(weekday - start.weekday()) % 7)
    out = []
    while d <= end:
        out.append(d)
        d += timedelta(days=7)
    return out
