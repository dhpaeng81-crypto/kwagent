"""예측 영역과 대표 지점.

지점은 기상청 ASOS 주요 관측소 위치에 맞췄다. 영역 평균 = 지점 값의 단순 평균.
권역은 위도가 아니라 행정구역으로 나눈다(예: 안동은 위도 36.6°지만 경북 → 남부).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    name: str
    stn: int        # 기상청 ASOS 지점번호 (관측 교체 시 사용)
    lat: float
    lon: float
    zone: str       # central | south


POINTS: list[Point] = [
    # 중부권: 서울·인천·경기, 강원, 충북·충남·대전
    Point("서울", 108, 37.571, 126.966, "central"),
    Point("인천", 112, 37.478, 126.625, "central"),
    Point("수원", 119, 37.257, 126.983, "central"),
    Point("춘천", 101, 37.903, 127.736, "central"),
    Point("강릉", 105, 37.751, 128.891, "central"),
    Point("원주", 114, 37.338, 127.947, "central"),
    Point("청주", 131, 36.639, 127.441, "central"),
    Point("대전", 133, 36.372, 127.372, "central"),
    Point("서산", 129, 36.777, 126.494, "central"),
    Point("충주", 127, 36.970, 127.953, "central"),
    # 남부권: 전북·전남·광주, 경북·대구, 경남·부산·울산, 제주
    Point("전주", 146, 35.822, 127.155, "south"),
    Point("광주", 156, 35.173, 126.892, "south"),
    Point("목포", 165, 34.817, 126.381, "south"),
    Point("여수", 168, 34.739, 127.741, "south"),
    Point("대구", 143, 35.878, 128.653, "south"),
    Point("안동", 136, 36.573, 128.707, "south"),
    Point("포항", 138, 36.032, 129.380, "south"),
    Point("부산", 159, 35.105, 129.032, "south"),
    Point("울산", 152, 35.582, 129.335, "south"),
    Point("진주", 192, 35.164, 128.040, "south"),
    Point("제주", 184, 33.514, 126.530, "south"),
]

REGION_LABELS = {"korea": "전국", "central": "중부권", "south": "남부권"}


def points_for(region: str) -> list[Point]:
    if region == "korea":
        return POINTS
    pts = [p for p in POINTS if p.zone == region]
    if not pts:
        raise ValueError(f"unknown region: {region}")
    return pts
