"""PARKING TRUTH + SAFE PICKUP.

- 공식 요금표 기준으로 예상 체류시간 총비용을 계산한다.
- 잔여면수·발렛·할인 등은 확인 가능한 데이터에 한해 표시하고, 출처/갱신시각/확인필요 상태를 함께 낸다.
- 운영시간·차고 제한·합법 승하차 여부를 필수 필터로 적용한다.
- 주정차 단속 회피 정보나 불법 정차 장소는 데이터 모델 자체에 두지 않는다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .geo import Point, RouteEstimator
from .timeutil import fmt, is_open_through, minutes_between

STALE_HOURS = 24


@dataclass
class Vehicle:
    height_m: float = 1.75
    compact: bool = False


def base_fee(fee: dict[str, int], stay_min: int, extra_free_min: int = 0) -> int:
    """요금표: free_min 이하 무료 → base_min 까지 base_fee → 이후 unit_min 마다 unit_fee, daily_max 상한."""
    billable = stay_min - extra_free_min
    if billable <= fee.get("free_min", 0) or billable <= 0:
        return 0
    cost = fee["base_fee"]
    rest = billable - fee["base_min"]
    if rest > 0:
        cost += math.ceil(rest / fee["unit_min"]) * fee["unit_fee"]
    return min(cost, fee.get("daily_max", cost))


def _field_status(value: Any, updated_at: str | None, now: datetime) -> dict[str, Any]:
    if value is None:
        return {"value": None, "status": "미확인", "label": "확인 불가 — 현장 확인 필요"}
    status = "확인됨"
    if updated_at:
        age_h = (now - datetime.fromisoformat(updated_at)).total_seconds() / 3600
        if age_h > STALE_HOURS:
            status = "갱신 지연"
    return {"value": value, "status": status, "updated_at": updated_at}


@dataclass
class ParkingQuery:
    origin: Point
    destination: Point          # 학원·병원 등 (사용자가 지정한 좌표만 사용, 기관명/아동 정보는 받지 않음)
    now: datetime
    stay_until: datetime
    vehicle: Vehicle = field(default_factory=Vehicle)
    pickup_only: bool = False   # SAFE PICKUP 모드: 합법 승하차 가능 장소만
    has_academy_receipt: bool = False


def evaluate_lots(lots: list[dict], q: ParkingQuery, est: RouteEstimator) -> dict[str, list[dict]]:
    stay_min = max(1, minutes_between(q.now, q.stay_until))
    ok: list[dict] = []
    excluded: list[dict] = []
    for lot in lots:
        here = Point(lot["lat"], lot["lng"])
        reasons: list[str] = []
        drive_km, drive_min = est.drive(q.origin, here)
        arrive = q.now  # 비교 기준은 현재 시각 (진입 소요는 별도 표시)
        if not is_open_through(q.now, lot["open"], lot["close"], arrive, q.stay_until):
            reasons.append(f"운영시간 {lot['open']}~{lot['close']} 이 체류 종료 {fmt(q.stay_until)} 을 덮지 못함")
        if lot["height_limit_m"] < q.vehicle.height_m:
            reasons.append(f"높이 제한 {lot['height_limit_m']}m < 차량 {q.vehicle.height_m}m")
        if q.pickup_only and not lot.get("pickup_zone_legal"):
            reasons.append("합법 승하차 장소로 확인되지 않음")
        if lot.get("realtime_spaces") == 0:
            reasons.append("만차(실시간)")
        if reasons:
            excluded.append({"id": lot["id"], "name": lot["name"], "reasons": reasons})
            continue

        # 할인: 검증된 할인만 금액에 반영, 미검증 할인은 '확인 필요'로 별도 표시
        applied, pending = [], []
        extra_free = 0
        rate = 1.0
        for d in lot.get("discounts", []):
            eligible = (
                (d["condition"] == "vehicle_compact" and q.vehicle.compact)
                or (d["condition"] == "academy_receipt" and q.has_academy_receipt)
            )
            if not eligible:
                continue
            if d.get("verified"):
                applied.append(d["name"])
                rate *= 1 - d.get("rate", 0)
                extra_free += d.get("free_min", 0)
            else:
                pending.append(d["name"])
        full_fee = base_fee(lot["fee"], stay_min)
        est_fee = int(round(base_fee(lot["fee"], stay_min, extra_free) * rate, -1))
        pending_fee = None
        if pending:
            best_free = max(d.get("free_min", 0) for d in lot["discounts"] if d["name"] in pending)
            pending_fee = int(round(base_fee(lot["fee"], stay_min, extra_free + best_free) * rate, -1))

        walk_km, walk_min = est.walk(here, q.destination)
        ok.append({
            "id": lot["id"],
            "name": lot["name"],
            "lat": lot["lat"],
            "lng": lot["lng"],
            "entrance": lot["entrance"],
            "hours": f"{lot['open']}~{lot['close']}",
            "drive_min": drive_min,
            "drive_km": drive_km,
            "walk_to_destination_min": walk_min,
            "walk_to_destination_km": walk_km,
            "stay_min": stay_min,
            "fee_estimate": est_fee,
            "fee_without_discount": full_fee,
            "fee_if_pending_discount_confirmed": pending_fee,
            "discounts_applied": applied,
            "discounts_need_check": pending,
            "realtime_spaces": _field_status(lot.get("realtime_spaces"), lot.get("realtime_spaces_updated_at"), q.now),
            "valet": _field_status(lot.get("valet"), lot.get("updated_at"), q.now),
            "pickup_zone_legal": bool(lot.get("pickup_zone_legal")),
            "source": lot["source"],
            "updated_at": lot["updated_at"],
            "data_freshness": _field_status(True, lot["updated_at"], q.now)["status"],
        })
    # 정렬: 목적지 도보 → 예상요금 → 진입 소요
    ok.sort(key=lambda x: (x["walk_to_destination_min"] + x["drive_min"], x["fee_estimate"]))
    return {"recommended": ok, "excluded": excluded}
