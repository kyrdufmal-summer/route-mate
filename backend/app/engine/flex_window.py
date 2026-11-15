"""FLEX WINDOW + ROUTE-FIT MATCH 핵심 알고리즘.

(A) 법적 적합성·업무 자격·보험·주차 가능성을 필수 필터로 확인
(B) 현위치→업무지→복귀지의 운전·도보·업무·안전여유를 합산
(C) 복귀 마감 초과 시 제외
(D) 통과 후보를 우회시간·예상 순수익·신뢰도로 정렬

안전·계약 판단은 전부 이 규칙 기반 코드에서 처리한다. (LLM 은 의도 해석·설명 문구에만 사용)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .geo import Point, RouteEstimator
from .timeutil import fmt, minutes_between

COST_PER_KM = 180          # 원/km — 연료·감가 단순 추정 (사용자 설정으로 변경 가능)
SYSTEM_MIN_BUFFER = 5      # 사용자가 더 낮게 설정해도 강제되는 최소 복귀 여유(분)


@dataclass
class DriverProfile:
    qualifications: list[str] = field(default_factory=lambda: ["driver_license"])
    insurance: dict[str, str] = field(default_factory=dict)   # 보험종류 -> 만료일 ISO
    cargo_capacity: str = "small"                             # none < small < large


CARGO_RANK = {"none": 0, "small": 1, "large": 2}


@dataclass
class FlexWindow:
    now: datetime
    position: Point             # 현재 차량(주차) 위치
    return_point: Point         # 복귀 기준점
    return_by: datetime         # 복귀 마감
    min_buffer_min: int = 5     # 사용자가 설정한 최소 복귀 여유
    max_drive_min: int | None = None  # 총 운전(우회) 허용 상한
    wants_work: bool = True
    categories: list[str] | None = None  # 희망 업무 유형 (None = 전체)


@dataclass
class GigEvaluation:
    gig_id: str
    title: str
    eligible: bool
    reasons: list[str]
    breakdown: dict[str, int] | None = None
    finish_at: str | None = None
    slack_min: int | None = None
    net_profit: int | None = None
    net_per_hour: int | None = None
    trust: float | None = None
    score: float | None = None
    partner: str | None = None
    pay: int | None = None
    costs: dict[str, int] | None = None
    lat: float | None = None
    lng: float | None = None

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def hard_filters(gig: dict, fw: FlexWindow, driver: DriverProfile) -> list[str]:
    """(A) 하나라도 걸리면 추천하지 않는다. 사용자에게 사유를 투명하게 보여준다."""
    reasons: list[str] = []
    if not gig.get("partner_verified"):
        reasons.append("제휴·검증되지 않은 공급자")
    if not gig.get("legal_reviewed"):
        reasons.append("법적 적합성 검토 미완료")
    if datetime.fromisoformat(gig["expires_at"]) <= fw.now:
        reasons.append("일감 마감 시각 경과")
    missing = [q for q in gig.get("required_qualifications", []) if q not in driver.qualifications]
    if missing:
        reasons.append(f"필요 자격 미보유: {', '.join(missing)}")
    ins = gig.get("requires_insurance")
    if ins:
        until = driver.insurance.get(ins)
        if not until:
            reasons.append(f"필수 보험 미가입: {ins}")
        elif datetime.fromisoformat(until) < fw.return_by:
            reasons.append(f"보험({ins}) 만료가 업무 종료 전")
    if CARGO_RANK.get(gig.get("cargo", "none"), 0) > CARGO_RANK.get(driver.cargo_capacity, 0):
        reasons.append("차량 적재 조건 불충족")
    if not gig.get("on_foot") and not gig.get("parking_at_site", {}).get("available"):
        reasons.append("업무지 합법 정차/주차 공간 미확인")
    if fw.categories and gig.get("category") not in fw.categories:
        reasons.append("희망 업무 유형 아님")
    return reasons


def time_budget(gig: dict, fw: FlexWindow, est: RouteEstimator) -> tuple[dict[str, int], float]:
    """(B) 이동·업무·복귀·안전여유 합산. 반환: (분 단위 내역, 총 주행 km)"""
    site = Point(gig["lat"], gig["lng"])
    if gig.get("on_foot"):
        _, go = est.walk(fw.position, site)
        _, back = est.walk(site, fw.return_point)
        km = 0.0
        travel_label = ("walk_to_site", "walk_back")
    else:
        km1, go = est.drive(fw.position, site)
        km2, back = est.drive(site, fw.return_point)
        km = km1 + km2
        travel_label = ("drive_to_site", "drive_back")
    # 교통 불확실성: 이동시간의 25% 를 사용자 최소 여유에 더한다 (예: 5 + ceil(12*0.25)=8)
    buffer = max(SYSTEM_MIN_BUFFER, fw.min_buffer_min) + math.ceil((go + back) * 0.25)
    breakdown = {
        travel_label[0]: go,
        "task": gig["task_min"],
        travel_label[1]: back,
        "safety_buffer": buffer,
    }
    breakdown["total"] = sum(breakdown.values())
    return breakdown, km


def evaluate_gig(gig: dict, fw: FlexWindow, driver: DriverProfile, est: RouteEstimator) -> GigEvaluation:
    base = dict(gig_id=gig["id"], title=gig["title"], partner=gig.get("partner"), pay=gig["pay"],
                lat=gig["lat"], lng=gig["lng"], trust=gig.get("trust"))
    reasons = hard_filters(gig, fw, driver)
    if reasons:
        return GigEvaluation(eligible=False, reasons=reasons, **base)

    breakdown, km = time_budget(gig, fw, est)
    finish = fw.now + timedelta(minutes=breakdown["total"])
    slack = minutes_between(finish, fw.return_by)
    # (C) 복귀 마감 초과 → 제외
    if finish > fw.return_by:
        return GigEvaluation(eligible=False, breakdown=breakdown, finish_at=fmt(finish), slack_min=slack,
                             reasons=[f"복귀 마감 {fmt(fw.return_by)} 초과 (예상 {fmt(finish)})"], **base)
    if datetime.fromisoformat(gig["expires_at"]) < fw.now + timedelta(minutes=breakdown["total"] - breakdown["safety_buffer"]):
        return GigEvaluation(eligible=False, breakdown=breakdown, reasons=["일감 마감 전 완료 불가"], **base)
    drive_total = breakdown.get("drive_to_site", 0) + breakdown.get("drive_back", 0)
    if fw.max_drive_min is not None and drive_total > fw.max_drive_min:
        return GigEvaluation(eligible=False, breakdown=breakdown,
                             reasons=[f"우회 운전 {drive_total}분 > 허용 {fw.max_drive_min}분"], **base)

    costs = {
        "vehicle": int(round(km * COST_PER_KM, -1)),
        "parking": int(gig.get("parking_at_site", {}).get("fee", 0)) if not gig.get("on_foot") else 0,
    }
    net = gig["pay"] - sum(costs.values())
    work_min = breakdown["total"] - breakdown["safety_buffer"]
    net_per_hour = int(net / work_min * 60) if work_min > 0 else 0
    # (D) 우회(짧을수록) · 순수익 · 신뢰도 가중 점수
    score = round(
        0.45 * min(net_per_hour / 40000, 1.0)
        + 0.30 * (1 - min(drive_total / 30, 1.0))
        + 0.25 * gig.get("trust", 0.5),
        4,
    )
    return GigEvaluation(eligible=True, reasons=[], breakdown=breakdown, finish_at=fmt(finish), slack_min=slack,
                         net_profit=net, net_per_hour=net_per_hour, costs=costs, score=score, **base)


def match(gigs: list[dict], fw: FlexWindow, driver: DriverProfile, est: RouteEstimator,
          taken: set[str] | None = None) -> dict:
    if not fw.wants_work:
        return {"mode": "rest", "recommended": [], "excluded": [],
                "message": "일감 추천을 끄셨어요. 주차·휴식·생활편의 안내만 제공합니다."}
    taken = taken or set()
    recs, excl = [], []
    for g in gigs:
        if g["id"] in taken:
            continue
        ev = evaluate_gig(g, fw, driver, est)
        (recs if ev.eligible else excl).append(ev.to_dict())
    recs.sort(key=lambda e: e["score"], reverse=True)
    message = (f"조건에 맞는 일감 {len(recs)}건" if recs
               else "지금은 조건에 맞는 일감이 없어요. 잠시 쉬시거나 근처 생활정보를 확인해 보세요.")
    return {"mode": "work", "recommended": recs, "excluded": excl, "message": message,
            "window": {"now": fmt(fw.now), "return_by": fmt(fw.return_by),
                       "available_min": minutes_between(fw.now, fw.return_by)}}
