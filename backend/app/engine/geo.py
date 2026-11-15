"""거리·이동시간 추정.

실차 환경에서는 Pleos NaviHelper SDK(경로·ETA)와 FusedLocation SDK(현재 위치)가
이 모듈을 대체한다. MVP에서는 직선거리에 도로 우회 계수를 곱한 보수적 추정치를 쓴다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class Point:
    lat: float
    lng: float


class RouteEstimator(Protocol):
    def drive(self, a: Point, b: Point) -> tuple[float, int]:
        """(도로 거리 km, 소요 분)"""

    def walk(self, a: Point, b: Point) -> tuple[float, int]:
        """(보행 거리 km, 소요 분)"""


@dataclass
class HeuristicEstimator:
    """NaviHelper 미연결 시 사용하는 보수적 추정기."""

    road_factor: float = 1.4          # 직선 대비 도로 우회 계수
    urban_kmh: float = 15.0           # 학원가 혼잡 시간대 평균 속도
    walk_factor: float = 1.25
    walk_kmh: float = 4.0
    min_drive_min: int = 3            # 출차·진입 고정 소요
    traffic_multiplier: float = 1.0   # 교통 악화 이벤트 시 상향

    def drive(self, a: Point, b: Point) -> tuple[float, int]:
        km = haversine_km(a.lat, a.lng, b.lat, b.lng) * self.road_factor
        minutes = km / self.urban_kmh * 60 * self.traffic_multiplier
        return round(km, 2), max(self.min_drive_min, math.ceil(minutes))

    def walk(self, a: Point, b: Point) -> tuple[float, int]:
        km = haversine_km(a.lat, a.lng, b.lat, b.lng) * self.walk_factor
        return round(km, 2), max(1, math.ceil(km / self.walk_kmh * 60))
