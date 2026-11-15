"""ROUTE MATE — FLEX WINDOW 백엔드 (FastAPI).

차량 클라이언트(Pleos Connect AAOS 앱, MVP 에서는 웹 시뮬레이터)가 호출하는 외부 서비스.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .engine import intent as intent_mod
from .engine.flex_window import DriverProfile, FlexWindow, evaluate_gig, match
from .engine.geo import HeuristicEstimator, Point
from .engine.parking import ParkingQuery, Vehicle, evaluate_lots
from .engine.radar import radar
from .engine.safety import DrivingLockError, VehicleState, brief_for_driving, require_parked
from .engine.timeutil import fmt, minutes_between
from .store import ConflictError, Store

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
DEMO_NOW = "2026-11-15T17:20:00"

app = FastAPI(title="ROUTE MATE API", version="0.1.0")
store = Store()


# ---------- schemas ----------
class LatLng(BaseModel):
    lat: float
    lng: float

    def p(self) -> Point:
        return Point(self.lat, self.lng)


class VehicleIn(BaseModel):
    height_m: float = 1.75
    compact: bool = False


class VehicleStateIn(BaseModel):
    gear: Literal["P", "R", "N", "D"] = "P"
    speed_kmh: float = 0.0

    def v(self) -> VehicleState:
        return VehicleState(self.gear, self.speed_kmh)


class DriverIn(BaseModel):
    qualifications: list[str] = ["driver_license"]
    insurance: dict[str, str] = {}
    cargo_capacity: Literal["none", "small", "large"] = "small"


class ParkingSearchIn(BaseModel):
    origin: LatLng
    destination: LatLng
    now: datetime | None = None
    stay_until: datetime
    vehicle: VehicleIn = VehicleIn()
    pickup_only: bool = False
    has_academy_receipt: bool = False


class IntentIn(BaseModel):
    utterance: str = Field(max_length=200)
    now: datetime | None = None


class SessionIn(BaseModel):
    position: LatLng
    return_point: LatLng | None = None         # None = 현재 위치로 복귀
    return_by: datetime
    now: datetime | None = None
    min_buffer_min: int = Field(5, ge=0, le=60)
    max_drive_min: int | None = Field(None, ge=0, le=120)
    wants_work: bool = True
    categories: list[str] | None = None
    radar_keywords: list[str] = []
    driver: DriverIn = DriverIn()
    consent_location: bool = True


class AcceptIn(BaseModel):
    gig_id: str
    now: datetime | None = None
    vehicle_state: VehicleStateIn = VehicleStateIn()


class EventIn(BaseModel):
    type: Literal["traffic_delay", "gig_cancelled", "parking_full"]
    delay_min: int = 0
    now: datetime | None = None


# ---------- helpers ----------
def _now(v: datetime | None) -> datetime:
    return v or datetime.now()


def _session_or_404(sid: str):
    try:
        return store.get(sid)
    except KeyError:
        raise HTTPException(404, "이용 기록이 없거나 이미 삭제됐어요.")


def _estimator(s) -> HeuristicEstimator:
    return HeuristicEstimator(traffic_multiplier=s.data.get("traffic_multiplier", 1.0))


def _fw(s, now: datetime) -> FlexWindow:
    d = s.data
    return FlexWindow(
        now=now,
        position=Point(**d["position"]),
        return_point=Point(**(d["return_point"] or d["position"])),
        return_by=datetime.fromisoformat(d["return_by"]),
        min_buffer_min=d["min_buffer_min"],
        max_drive_min=d["max_drive_min"],
        wants_work=d["wants_work"],
        categories=d["categories"],
    )


def _driver(s) -> DriverProfile:
    return DriverProfile(**s.data["driver"])


# ---------- API ----------
@app.get("/api/health")
def health():
    return {"ok": True, "version": app.version, "data": "샘플(가상 시연 데이터)"}


@app.get("/api/demo/scenario")
def demo_scenario():
    """대표 장면: 17:20, 보호자가 자녀의 18:00 학원 종료를 기다리며 도착 (가상 시연)."""
    return {
        "now": DEMO_NOW,
        "vehicle_position": {"lat": 37.49880, "lng": 127.06230},
        "destination": {"lat": 37.49985, "lng": 127.06330, "label": "목적지"},
        "pickup_end": "2026-11-15T18:10:00",
        "vehicle": {"height_m": 1.98, "compact": False},
        "driver": {"qualifications": ["driver_license"],
                   "insurance": {"gig_delivery": "2027-03-31T23:59:00"}, "cargo_capacity": "small"},
        "utterance": "주차 후 17:55까지 이곳에 돌아와야 해요. 시간이 남으면 가까운 일도 볼래요. 5분 이상 여유 두고 약국이랑 반찬가게도 알려줘",
        "notice": "모든 주차장·일감·상점은 가상 샘플 데이터입니다.",
    }


@app.post("/api/parking/search")
def parking_search(body: ParkingSearchIn):
    q = ParkingQuery(origin=body.origin.p(), destination=body.destination.p(), now=_now(body.now),
                     stay_until=body.stay_until, vehicle=Vehicle(**body.vehicle.model_dump()),
                     pickup_only=body.pickup_only, has_academy_receipt=body.has_academy_receipt)
    return evaluate_lots(store.parking_lots, q, HeuristicEstimator())


@app.post("/api/intent")
def parse_intent(body: IntentIn):
    r = intent_mod.parse(body.utterance, _now(body.now))
    return {**r.__dict__, "note": "해석 결과는 제안입니다. 화면에서 확인한 값만 저장됩니다."}


@app.post("/api/sessions", status_code=201)
def create_session(body: SessionIn):
    if not body.consent_location:
        raise HTTPException(400, "위치 정보 이용에 동의해야 여유 시간 계획을 쓸 수 있어요. 동의하지 않아도 주차장 비교는 이용할 수 있어요.")
    now = _now(body.now)
    if body.return_by <= now:
        raise HTTPException(422, "복귀 시각은 지금보다 늦어야 해요.")
    data = body.model_dump(mode="json")
    data["now"] = now.isoformat()
    data["return_by"] = body.return_by.isoformat()
    s = store.create_session(data)
    return {"session_id": s.id, "window": {"now": fmt(now), "return_by": fmt(body.return_by),
                                           "available_min": minutes_between(now, body.return_by)}}


@app.get("/api/sessions/{sid}/recommendations")
def recommendations(sid: str, now: datetime | None = None, gear: str = "P", speed_kmh: float = 0.0):
    s = _session_or_404(sid)
    now = _now(now)
    fw = _fw(s, now)
    est = _estimator(s)
    vs = VehicleState(gear, speed_kmh)
    rad = radar(store.places, s.data["radar_keywords"], fw.position, now, fw.return_by, est)

    if s.recommendations_paused:
        result = {"mode": "paused", "recommended": [], "excluded": [],
                  "message": f"새 일감 추천을 멈췄어요({s.pause_reason}). 안전하게 돌아오는 길을 먼저 안내할게요."}
    elif s.assignment and s.assignment["state"] in ("accepted", "in_progress"):
        result = {"mode": "assigned", "recommended": [], "excluded": [], "message": "진행 중인 업무가 있어요."}
    else:
        hidden = store.taken_gigs(except_session=sid) | set(s.data.get("declined", []))
        result = match(store.gigs, fw, _driver(s), est, taken=hidden)

    if not vs.stationary:
        # 주행 중: 상세 목록 대신 짧은 음성 브리핑만
        n = len(result["recommended"])
        msg = f"조건에 맞는 일감이 {n}건 있어요. 차를 세운 뒤 확인하세요." if n else "지금은 조건에 맞는 일감이 없어요."
        return {"driving": True, "voice_brief": brief_for_driving(msg), "count": n}

    return {"driving": False, **result, "radar": rad, "assignment": s.assignment,
            "remaining_min": minutes_between(now, fw.return_by)}


@app.post("/api/sessions/{sid}/accept")
def accept(sid: str, body: AcceptIn, idempotency_key: str = Header(..., alias="Idempotency-Key")):
    s = _session_or_404(sid)
    try:
        require_parked(body.vehicle_state.v(), "일감을 수락할")
    except DrivingLockError as e:
        raise HTTPException(423, str(e))
    if s.recommendations_paused:
        raise HTTPException(409, f"지금은 추천을 멈춘 상태예요({s.pause_reason}).")
    gig = next((g for g in store.gigs if g["id"] == body.gig_id), None)
    if not gig:
        raise HTTPException(404, "일감을 찾을 수 없어요.")
    now = _now(body.now)
    fw = _fw(s, now)
    # 수락 시점에 조건을 다시 검증 (그 사이 시간이 흘렀거나 보험·마감이 바뀌었을 수 있음)
    ev = evaluate_gig(gig, fw, _driver(s), _estimator(s)).to_dict()
    if not ev["eligible"]:
        raise HTTPException(409, {"message": "지금은 이 일감의 조건을 충족하지 않아요.", "reasons": ev["reasons"]})
    try:
        res = store.accept(sid, gig["id"], idempotency_key, ev)
    except ConflictError as e:
        raise HTTPException(409, str(e))
    bd = ev["breakdown"]
    go = bd.get("drive_to_site", bd.get("walk_to_site", 0))
    res["navigation"] = {
        "provider": "내비게이션 연동 예정(현재는 추정 경로)",
        "waypoints": [
            {"label": "업무지", "lat": gig["lat"], "lng": gig["lng"], "eta": fmt(now + timedelta(minutes=go))},
            {"label": "복귀 지점", **(s.data["return_point"] or s.data["position"]), "eta": ev["finish_at"]},
        ],
        "return_by": fmt(fw.return_by),
    }
    return res


class DeclineIn(BaseModel):
    gig_id: str


@app.post("/api/sessions/{sid}/decline")
def decline(sid: str, body: DeclineIn):
    """거절한 일감은 이 세션에서 다시 추천하지 않는다. 거절은 불이익 없이 기록만 남긴다."""
    s = _session_or_404(sid)
    with store.lock:
        declined = s.data.setdefault("declined", [])
        if body.gig_id not in declined:
            declined.append(body.gig_id)
    store.log(sid, "gig_declined", gig_id=body.gig_id)
    return {"declined": declined}


@app.post("/api/sessions/{sid}/assignment/{action}")
def assignment_action(sid: str, action: Literal["start", "complete", "cancel"]):
    _session_or_404(sid)
    state = {"start": "in_progress", "complete": "completed", "cancel": "cancelled"}[action]
    try:
        return store.transition(sid, state, reason="user")
    except ConflictError as e:
        raise HTTPException(409, str(e))


@app.post("/api/sessions/{sid}/events")
def vehicle_event(sid: str, body: EventIn):
    """교통 악화·업무 취소·주차 만차 감지 → 추가 추천 중지, 안전한 복귀/고객 안내 우선."""
    s = _session_or_404(sid)
    now = _now(body.now)
    fw = _fw(s, now)
    guidance: list[str] = []
    with store.lock:
        s.recommendations_paused = True
        if body.type == "traffic_delay":
            s.data["traffic_multiplier"] = 1.0 + max(body.delay_min, 0) / 10
            s.pause_reason = f"교통 정체로 {body.delay_min}분 지연"
        elif body.type == "gig_cancelled":
            s.pause_reason = "업무 취소"
        else:
            s.pause_reason = "복귀할 주차장 만차"
    a = s.assignment
    active = a and a["state"] in ("accepted", "in_progress")
    if body.type == "gig_cancelled" and active:
        store.transition(sid, "cancelled", reason="partner_cancelled")
        guidance.append("업무가 취소됐어요. 복귀 지점으로 안내할게요.")
    elif body.type == "traffic_delay" and active:
        bd = a["evaluation"]["breakdown"]
        m = s.data["traffic_multiplier"]
        go = bd.get("drive_to_site", bd.get("walk_to_site", 0))
        back = bd.get("drive_back", bd.get("walk_back", 0))
        # 보수적으로 남은 구간 전체를 다시 합산 (도보 구간은 교통 영향 없음)
        scale = m if "drive_back" in bd else 1.0
        remaining = bd["task"] + math.ceil(back * scale)
        if a["state"] == "accepted":
            remaining += math.ceil(go * scale)
        eta = now + timedelta(minutes=remaining)
        if eta > fw.return_by:
            guidance.append(f"약속한 {fmt(fw.return_by)}보다 늦은 {fmt(eta)}쯤 돌아오게 돼요. 업체에 지연을 알리고 바로 돌아가세요.")
        else:
            guidance.append(f"지연을 반영해도 {fmt(eta)}쯤 돌아올 수 있어요. 업무를 마치면 바로 복귀하세요.")
    elif body.type == "parking_full":
        q = ParkingQuery(origin=fw.return_point, destination=fw.return_point, now=now,
                         stay_until=fw.return_by + timedelta(minutes=15), pickup_only=True)
        rp = fw.return_point
        others = [lot for lot in store.parking_lots if (lot["lat"], lot["lng"]) != (rp.lat, rp.lng)]  # 꽉 찬 곳 제외
        alts = evaluate_lots(others, q, HeuristicEstimator())["recommended"][:2]
        guidance.append("복귀할 주차장이 꽉 찼어요. 합법적으로 타고 내릴 수 있는 다른 곳을 안내할게요.")
        return {"paused": True, "reason": s.pause_reason, "guidance": guidance, "alternatives": alts}
    else:
        guidance.append("새 일감 추천을 멈췄어요. 안전하게 돌아오는 길을 먼저 안내할게요.")
    store.log(sid, "vehicle_event", type=body.type, delay_min=body.delay_min)
    return {"paused": True, "reason": s.pause_reason, "guidance": guidance, "assignment": s.assignment}


@app.post("/api/sessions/{sid}/resume")
def resume(sid: str):
    s = _session_or_404(sid)
    s.recommendations_paused, s.pause_reason = False, None
    s.data["traffic_multiplier"] = 1.0
    store.log(sid, "recommendations_resumed")
    return {"paused": False}


@app.delete("/api/sessions/{sid}", status_code=204)
def delete_session(sid: str):
    _session_or_404(sid)
    store.delete_session(sid)


@app.get("/api/audit")
def audit(limit: int = 50):
    return store.audit[-limit:]


# ---------- vehicle UI simulator ----------
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")
