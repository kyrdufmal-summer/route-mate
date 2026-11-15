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
from .engine import situation as sit
from .engine.flex_window import DriverProfile, FlexWindow, evaluate_gig, is_posted, match
from .engine.geo import HeuristicEstimator, Point
from .engine.parking import ParkingQuery, Vehicle, evaluate_lots
from .engine.radar import radar
from .engine.safety import DrivingLockError, VehicleState, brief_for_driving, require_parked
from .engine.timeutil import at_clock, fmt, minutes_between
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
    purpose: Literal["pickup", "hospital", "other"] = "pickup"


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


def _incidents(now: datetime) -> list[dict]:
    return sit.active_incidents(store.live_feed, store.manual_incidents, now)


def _delay_for(fw: FlexWindow, now: datetime):
    """실시간 상황(사고·정체·비)이 이 일감의 운전 구간에 주는 지연(분)."""
    incs = _incidents(now)

    def f(gig: dict) -> int:
        if gig.get("on_foot"):
            return 0
        site = Point(gig["lat"], gig["lng"])
        return sit.route_delay(incs, [(fw.position, site), (site, fw.return_point)])[0]
    return f


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
    data["announced"], data["dismissed"] = [], []
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
                  "message": f"{s.pause_reason}. 지금은 새 일을 띄우지 않을게요."}
    elif s.assignment and s.assignment["state"] in ("accepted", "in_progress"):
        result = {"mode": "assigned", "recommended": [], "excluded": [], "message": "하고 있는 일이 있어요."}
    else:
        hidden = store.taken_gigs(except_session=sid) | set(s.data.get("declined", []))
        result = match(store.gigs, fw, _driver(s), est, taken=hidden, delay_for=_delay_for(fw, now))

    if not vs.stationary:
        # 주행 중: 상세 목록 대신 짧은 음성 브리핑만
        n = len(result["recommended"])
        msg = f"시간 맞는 일이 {n}개 있어요. 차 세우고 보세요." if n else "지금은 시간 맞는 일이 없어요."
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
    ev = evaluate_gig(gig, fw, _driver(s), _estimator(s), _delay_for(fw, now)(gig)).to_dict()
    if not ev["eligible"]:
        raise HTTPException(409, {"message": "지금은 이 일을 하기 어려워요.", "reasons": ev["reasons"]})
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
            s.pause_reason = f"길이 막혀서 {body.delay_min}분쯤 늦어지고 있어요"
        elif body.type == "gig_cancelled":
            s.pause_reason = "업체에서 일을 취소했어요"
        else:
            s.pause_reason = "돌아갈 주차장이 꽉 찼어요"
    a = s.assignment
    active = a and a["state"] in ("accepted", "in_progress")
    if body.type == "gig_cancelled" and active:
        store.transition(sid, "cancelled", reason="partner_cancelled")
        guidance.append("업체에서 일을 취소했어요. 그냥 돌아오시면 돼요.")
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
            guidance.append(f"길이 막혀서 {fmt(eta)}쯤 도착해요. {fmt(fw.return_by)}보다 늦으니까, 업체에 늦는다고 알리고 바로 출발하세요.")
        else:
            guidance.append(f"길이 좀 막히지만 {fmt(eta)}이면 돌아와요. 끝나면 바로 출발하세요.")
    elif body.type == "parking_full":
        q = ParkingQuery(origin=fw.return_point, destination=fw.return_point, now=now,
                         stay_until=fw.return_by + timedelta(minutes=15), pickup_only=True)
        rp = fw.return_point
        others = [lot for lot in store.parking_lots if (lot["lat"], lot["lng"]) != (rp.lat, rp.lng)]  # 꽉 찬 곳 제외
        alts = evaluate_lots(others, q, HeuristicEstimator())["recommended"][:2]
        guidance.append("돌아갈 주차장이 꽉 찼대요. 근처에 바로 세울 수 있는 곳을 찾아 뒀어요.")
        return {"paused": True, "reason": s.pause_reason, "guidance": guidance, "alternatives": alts}
    else:
        guidance.append("새 일은 잠깐 멈출게요. 돌아오는 것부터 챙기세요.")
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


# ---------- 실시간 상황 · 먼저 말 걸기 ----------
def _live_view(incs: list[dict], fw: FlexWindow, assignment: dict | None) -> list[dict]:
    """화면 상단 '지금 상황' 표시용. 내 경로·내 약속에 영향이 있는지 함께 표시."""
    legs = []
    if assignment and assignment["state"] in ("accepted", "in_progress"):
        ev = assignment["evaluation"]
        site = Point(ev["lat"], ev["lng"])
        legs = [(fw.position, site), (site, fw.return_point)]
    out = []
    for inc in incs:
        if inc["type"] == "schedule_change":
            continue
        mine = inc["type"] == "weather" or any(sit.hits_leg(inc, a, b) for a, b in legs) or (
            "lat" in inc and sit.dist_to_segment_m(Point(inc["lat"], inc["lng"]), fw.return_point, fw.return_point)
            <= inc.get("radius_m", 200) + 150)
        out.append({"id": inc["id"], "type": inc["type"], "title": inc["title"], "delay_min": inc.get("delay_min", 0),
                    "mine": bool(mine), "source": inc.get("source", ""), "lat": inc.get("lat"), "lng": inc.get("lng")})
    return out


@app.get("/api/sessions/{sid}/situation")
def situation(sid: str, now: datetime | None = None, gear: str = "P", resting: bool = False):
    """지금 상황을 보고, 사용자에게 먼저 말해야 할 것(개입)이 있는지 판단한다. 한 번 한 말은 다시 하지 않는다."""
    s = _session_or_404(sid)
    now = _now(now)
    fw = _fw(s, now)
    incs = [i for i in _incidents(now) if i["id"] not in s.data.get("dismissed", [])]
    a = s.assignment
    site = Point(a["evaluation"]["lat"], a["evaluation"]["lng"]) if a else None

    # 세션 시작 뒤 새로 올라온 일감 중, 지금 조건에 맞는 것
    started = datetime.fromisoformat(s.data["now"])
    hidden = store.taken_gigs(except_session=sid) | set(s.data.get("declined", []))
    fresh = [g for g in store.gigs if g.get("posted_at") and is_posted(g, now)
             and datetime.fromisoformat(g["posted_at"]) > started and g["id"] not in hidden]
    new_gigs = [r for r in match(fresh, fw, _driver(s), _estimator(s), delay_for=_delay_for(fw, now))["recommended"]] if fresh else []

    ctx = sit.Context(now=now, return_by=fw.return_by, position=fw.position, return_point=fw.return_point,
                      purpose=s.data.get("purpose", "pickup"), wants_work=fw.wants_work, resting=resting,
                      parked=VehicleState(gear).parked, assignment=a, gig_site=site, incidents=incs, new_gigs=new_gigs)
    announced = s.data.setdefault("announced", [])
    fresh_ivs = [iv for iv in sit.assess(ctx) if iv["id"] not in announced]
    for iv in fresh_ivs:
        announced.append(iv["id"])
        store.log(sid, "assistant_spoke", kind=iv["kind"], id=iv["id"])
    spoken = [iv for iv in fresh_ivs if not iv.get("silent")]
    return {"now": fmt(now), "return_by": fmt(fw.return_by), "live": _live_view(incs, fw, a), "interventions": spoken}


class InterventionAction(BaseModel):
    action: Literal["extend", "dismiss", "notify_partner", "cancel_gig", "show_gigs"]
    minutes: int = 0
    intervention_id: str = ""


@app.post("/api/sessions/{sid}/situation/action")
def situation_action(sid: str, body: InterventionAction):
    s = _session_or_404(sid)
    msg = ""
    if body.action == "extend":
        new_rb = datetime.fromisoformat(s.data["return_by"]) + timedelta(minutes=body.minutes)
        s.data["return_by"] = new_rb.isoformat()
        msg = f"네, 돌아올 시각을 {fmt(new_rb)}까지로 바꿨어요."
    elif body.action == "notify_partner":
        msg = "업체에 '조금 늦을 것 같아요'라고 보냈어요. (시연에서는 실제로 보내지 않아요)"
    elif body.action == "cancel_gig":
        if s.assignment and s.assignment["state"] in ("accepted", "in_progress"):
            store.transition(sid, "cancelled", reason="late_risk")
        msg = "일은 취소했어요. 천천히, 안전하게 돌아오세요."
    elif body.action == "dismiss":
        msg = "네, 알겠어요."
    store.log(sid, "intervention_action", action=body.action, id=body.intervention_id)
    return {"message": msg, "return_by": fmt(datetime.fromisoformat(s.data["return_by"])), "assignment": s.assignment}


class IncidentIn(BaseModel):
    type: Literal["accident", "weather", "school_rush", "schedule_change"]
    now: datetime | None = None
    minutes: int = 15


@app.post("/api/demo/incidents", status_code=201)
def add_incident(body: IncidentIn, sid: str | None = None):
    """시연 도구: 지금 이 순간 상황을 하나 만든다. 사고는 진행 중인 일의 경로 위(없으면 목적지 근처)에 만든다."""
    now = _now(body.now)
    n = len(store.manual_incidents) + 1
    inc: dict = {"id": f"M-{n}", "type": body.type, "starts": now.isoformat(),
                 "ends": (now + timedelta(minutes=60)).isoformat(), "source": "시연 도구"}
    sc = demo_scenario()
    lat, lng = sc["destination"]["lat"], sc["destination"]["lng"]
    s = store.sessions.get(sid) if sid else None
    if s and s.assignment:
        ev = s.assignment["evaluation"]
        rp = s.data["return_point"] or s.data["position"]
        lat, lng = (ev["lat"] + rp["lat"]) / 2, (ev["lng"] + rp["lng"]) / 2
    if body.type == "accident":
        inc.update(title="돌아오는 길 교통사고", lat=lat, lng=lng, radius_m=250, delay_min=8)
    elif body.type == "weather":
        inc.update(title="비", delay_min=3)
    elif body.type == "school_rush":
        inc.update(title="학원 앞 정체", lat=sc["destination"]["lat"], lng=sc["destination"]["lng"], radius_m=250, delay_min=5)
    else:
        inc.update(title="끝나는 시간 변경", extend_min=body.minutes, source="학원·병원 알림(연동 가정)")
    store.manual_incidents.append(inc)
    return inc


@app.delete("/api/demo/incidents", status_code=204)
def clear_incidents():
    """시연 도구: 직접 만든 상황을 모두 지운다 (처음부터 다시 할 때)."""
    store.manual_incidents.clear()


@app.get("/api/enforcement")
def enforcement(lat: float, lng: float, now: datetime | None = None, radius_m: int = 400):
    """목적지 주변 불법 주정차 단속 구간과 과태료, 오늘 예상 단속액(시연용 추정).
    단속 시간대·카메라 위치처럼 단속을 피하는 데 쓰일 정보는 내보내지 않는다. 합법 주차를 권하는 데에만 쓴다."""
    now = _now(now)
    here = Point(lat, lng)
    out = []
    for z in store.enforcement:
        d = sit.dist_to_segment_m(Point(z["lat"], z["lng"]), here, here)
        if d > radius_m + z["radius_m"]:
            continue
        open_t, close_t = at_clock(now, z["open"]), at_clock(now, z["close"])
        span = max(1, minutes_between(open_t, close_t))
        elapsed = min(max(minutes_between(open_t, now), 0), span)
        day_total = z["daily_cases_estimate"] * z["fine_car"]
        out.append({
            "id": z["id"], "name": z["name"], "kind": z["kind"], "fine_car": z["fine_car"], "fine_note": z["fine_note"],
            "today_estimate_total": day_total,
            "today_estimate_so_far": int(day_total * elapsed / span),
            "per_minute": round(day_total / span, 1),
            "source": z["source"], "is_estimate": True,
        })
    out.sort(key=lambda z: -z["fine_car"])
    return {"zones": out, "notice": "시연용 추정치예요. 과태료는 승용차 기준이에요."}


# ---------- vehicle UI simulator ----------
if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")
