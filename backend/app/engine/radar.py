"""ROUTE RADAR — 사용자가 미리 고른 키워드만 경로 주변 생활정보와 연결한다.
광고/제휴 콘텐츠(sponsored)는 일반 추천과 별도 목록으로 분리해 반환한다."""
from __future__ import annotations

from datetime import datetime, timedelta

from .geo import Point, RouteEstimator
from .timeutil import is_open_through


def radar(places: list[dict], keywords: list[str], position: Point, now: datetime, return_by: datetime,
          est: RouteEstimator, max_walk_min: int = 10) -> dict:
    wanted = set(keywords)
    organic, sponsored = [], []
    for p in places:
        hit = wanted.intersection(p["keywords"])
        if not hit:
            continue
        _, walk = est.walk(position, Point(p["lat"], p["lng"]))
        if walk > max_walk_min:
            continue
        round_trip = walk * 2
        if now + timedelta(minutes=round_trip) > return_by:
            continue
        if not is_open_through(now, p["open"], p["close"], now, now + timedelta(minutes=round_trip)):
            continue
        item = {
            "id": p["id"], "name": p["name"], "keywords": sorted(hit), "walk_min": walk,
            "round_trip_min": round_trip, "hours": f"{p['open']}~{p['close']}",
            "source": p["source"], "updated_at": p["updated_at"], "lat": p["lat"], "lng": p["lng"],
        }
        (sponsored if p.get("sponsored") else organic).append(item)
    organic.sort(key=lambda x: x["walk_min"])
    sponsored.sort(key=lambda x: x["walk_min"])
    return {"organic": organic, "sponsored": sponsored,
            "sponsored_notice": "광고·제휴 콘텐츠는 일반 추천과 구분하여 표시합니다."}
