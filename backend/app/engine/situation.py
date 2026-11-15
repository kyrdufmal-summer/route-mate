"""실시간 상황 판단 — 도우미가 '먼저 말을 거는' 시점과 내용을 정한다.

원칙
1. 결정이 바뀔 때만 말한다. (내 경로·내 약속 시각에 영향이 없으면 조용히 있는다)
2. 픽업·진료처럼 사용자가 정한 약속이 일보다 먼저다.
3. 한 번 한 말은 반복하지 않는다. (상황이 더 나빠지면 그때 다시 말한다)
4. 주행 중에는 짧게, 정차 중에는 선택지를 함께 준다.

실서비스에서는 교통정보(사고·정체), 기상, 학원·병원 알림, 일감 피드를 입력으로 받는다.
MVP 는 data/live_feed.json 의 시연용 시간표와 시연 도구에서 만든 상황을 입력으로 쓴다.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .geo import Point
from .timeutil import at_clock, fmt, minutes_between

PURPOSE_LABEL = {"pickup": "아이 픽업", "hospital": "진료 끝나는 시간", "other": "약속 시간"}


# ---------- 거리 계산 ----------
def _xy(p: Point, lat0: float) -> tuple[float, float]:
    return p.lng * 111_320 * math.cos(math.radians(lat0)), p.lat * 110_540


def dist_to_segment_m(p: Point, a: Point, b: Point) -> float:
    lat0 = (a.lat + b.lat) / 2
    (px, py), (ax, ay), (bx, by) = _xy(p, lat0), _xy(a, lat0), _xy(b, lat0)
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


# ---------- 상황(사건) ----------
def active_incidents(feed: list[dict], manual: list[dict], now: datetime) -> list[dict]:
    out = []
    for inc in feed + manual:
        start = at_clock(now, inc["starts"]) if len(inc["starts"]) == 5 else datetime.fromisoformat(inc["starts"])
        end = at_clock(now, inc["ends"]) if len(inc["ends"]) == 5 else datetime.fromisoformat(inc["ends"])
        if start <= now < end:
            out.append(inc)
    return out


def hits_leg(inc: dict, a: Point, b: Point) -> bool:
    if "lat" not in inc:
        return False
    return dist_to_segment_m(Point(inc["lat"], inc["lng"]), a, b) <= inc.get("radius_m", 200)


def route_delay(incidents: list[dict], legs: list[tuple[Point, Point]]) -> tuple[int, list[dict]]:
    """차로 지나는 구간(legs)에 걸리는 지연(분)과 원인 목록. 비는 운전 구간이 있으면 한 번만 더한다."""
    if not legs:
        return 0, []
    delay, hits = 0, []
    for inc in incidents:
        if inc["type"] == "weather":
            delay += inc.get("delay_min", 0)
            hits.append(inc)
            continue
        if inc["type"] not in ("accident", "congestion", "school_rush"):
            continue
        n = sum(1 for a, b in legs if hits_leg(inc, a, b))
        if n:
            delay += inc.get("delay_min", 0) * n
            hits.append(inc)
    return delay, hits


# ---------- 개입 판단 ----------
@dataclass
class Context:
    now: datetime
    return_by: datetime
    position: Point
    return_point: Point
    purpose: str = "pickup"
    wants_work: bool = True
    resting: bool = False
    parked: bool = True
    assignment: dict | None = None
    gig_site: Point | None = None
    incidents: list[dict] = field(default_factory=list)
    new_gigs: list[dict] = field(default_factory=list)
    waiting_spots: list[dict] = field(default_factory=list)   # 주차 되는 카페·마트 등
    market_hits: list[dict] = field(default_factory=list)     # 찾던 물건 매물
    trip: dict | None = None                                  # 진행 중인 중고거래 다녀오기


def josa(word: str, with_batchim: str, without: str) -> str:
    """한글 받침 유무에 맞는 조사 (예: 카시트+가, 자전거+가, 에어프라이어+가, 책+이)."""
    ch = word.strip()[-1] if word.strip() else ""
    if "가" <= ch <= "힣":
        return with_batchim if (ord(ch) - 0xAC00) % 28 else without
    return without


def josa_ro(word: str) -> str:
    """'로/으로': 받침이 없거나 ㄹ 받침이면 '로'."""
    ch = word.strip()[-1] if word.strip() else ""
    if "가" <= ch <= "힣":
        b = (ord(ch) - 0xAC00) % 28
        return "로" if b in (0, 8) else "으로"
    return "로"


def _iv(id_, priority, kind, say, short=None, actions=None, detail=None):
    return {"id": id_, "priority": priority, "kind": kind, "say": say, "say_short": short or say,
            "actions": actions or [], "detail": detail}


def _when(dt: datetime) -> str:
    return fmt(dt)


def assignment_eta(ctx: Context) -> tuple[datetime, int, list[dict], int]:
    """진행 중인 업무 기준 예상 복귀 시각, 지연(분), 원인, 복귀 구간 운전 시간."""
    a = ctx.assignment
    bd = a["evaluation"]["breakdown"]
    base_finish = at_clock(ctx.now, a["evaluation"]["finish_at"])
    if "drive_back" not in bd:  # 걸어서 하는 일은 교통 영향 없음
        return base_finish, 0, [], bd.get("walk_back", 0)
    legs = [(ctx.gig_site, ctx.return_point)]
    if a["state"] == "accepted":
        legs.insert(0, (ctx.position, ctx.gig_site))
    known = bd.get("traffic_delay", 0)  # 수락할 때 이미 반영한 지연은 빼고 계산
    delay, hits = route_delay(ctx.incidents, legs)
    extra = max(0, delay - known)
    back_delay, _ = route_delay(ctx.incidents, [(ctx.gig_site, ctx.return_point)])
    return base_finish + timedelta(minutes=extra), extra, hits, bd["drive_back"] + back_delay


def assess(ctx: Context) -> list[dict]:
    out: list[dict] = []
    who = PURPOSE_LABEL.get(ctx.purpose, "약속 시간")
    rb = _when(ctx.return_by)
    left = minutes_between(ctx.now, ctx.return_by)
    a = ctx.assignment
    active = a and a["state"] in ("accepted", "in_progress")

    # 1) 업무 중: 내 경로에 생긴 일만 말한다
    if active and ctx.gig_site:
        eta, extra, hits, back_min = assignment_eta(ctx)
        slack = minutes_between(eta, ctx.return_by)
        names = [h["title"] for h in hits if h["type"] != "weather"]
        rain = any(h["type"] == "weather" for h in hits)
        cause = (names[0] if names else "") + (" 때문에" if names else "")
        if rain and names:
            cause = f"{names[0]}에 비까지 와서"
        elif rain:
            cause = "비가 와서"
        level = "late" if slack < 0 else "tight" if slack < 5 else "ok"
        if extra > 0:
            key = f"route-{level}-{extra}"
            if level == "late":
                out.append(_iv(key, 3, "late",
                               f"{cause} 돌아오는 데 {extra}분 더 걸려요. 이대로면 {_when(eta)} 도착이라 {-slack}분 늦어요. "
                               f"{who}이 먼저니까, 업체에 늦는다고 말해 두고 끝나는 대로 바로 출발하세요.",
                               f"{-slack}분 늦을 것 같아요. 끝나는 대로 바로 출발하세요.",
                               [{"label": "업체에 늦는다고 알리기", "action": "notify_partner"},
                                {"label": "일 취소하고 돌아가기", "action": "cancel_gig"}]))
            elif level == "tight":
                room = f"여유가 {slack}분밖에 없어요" if slack > 0 else f"{rb}에 딱 맞춰 도착해요"
                out.append(_iv(key, 2, "tight",
                               f"{cause} {extra}분쯤 더 걸리겠어요. {room}. 끝나면 바로 출발하세요.",
                               f"{extra}분 늦어져요. 끝나면 바로 출발하세요."))
            else:
                out.append(_iv(key, 1, "info",
                               f"{cause} {extra}분쯤 더 걸려요. 그래도 {_when(eta)}이면 돌아와요.",
                               f"{extra}분 늦어져도 {rb} 전에 와요."))
        # 출발 알림: 업체에서 늦어도 이때는 나와야 약속에 맞는다
        if a["state"] == "in_progress":
            latest = ctx.return_by - timedelta(minutes=back_min + 2)
            to_latest = minutes_between(ctx.now, latest)
            if to_latest <= 0:
                out.append(_iv(f"leave-now-{_when(latest)}", 3, "leave",
                               f"지금 출발하셔야 {rb}에 맞춰요. 마무리 못 한 건 업체에 말씀하시고 나오세요.",
                               f"지금 출발하세요. {rb}에 맞춰야 해요."))
            elif to_latest <= 5:
                out.append(_iv(f"leave-soon-{_when(latest)}", 2, "leave",
                               f"늦어도 {_when(latest)}에는 나오셔야 해요. {to_latest}분 남았어요.",
                               f"{_when(latest)}에는 출발하세요."))

    # 2) 비: 운전 중이면 안전, 서 있으면 생활 팁
    for inc in ctx.incidents:
        if inc["type"] != "weather":
            continue
        if active or not ctx.parked:
            out.append(_iv(f"inc-{inc['id']}", 1, "weather",
                           "비가 오기 시작했어요. 길이 미끄러우니 평소보다 천천히 가세요.", "비 와요. 천천히 가세요."))
        elif ctx.purpose == "pickup":
            out.append(_iv(f"inc-{inc['id']}", 1, "weather",
                           "밖에 비가 오기 시작했어요. 아이 데리러 가실 때 우산 챙기세요.", "비 와요. 우산 챙기세요."))

    # 3) 업무가 없을 때: 픽업 장소 주변 상황
    if not active:
        for inc in ctx.incidents:
            near_dest = "lat" in inc and dist_to_segment_m(Point(inc["lat"], inc["lng"]), ctx.return_point, ctx.return_point) <= inc.get("radius_m", 200) + 150
            if inc["type"] == "school_rush" and near_dest and ctx.parked:
                out.append(_iv(f"inc-{inc['id']}", 1, "rush",
                               "이 시간엔 학원 앞에 차가 몰려요. 차는 지금 자리에 두고 걸어가서 데려오시는 게 더 빨라요.",
                               "학원 앞이 막혀요. 걸어가시는 게 빨라요."))
            elif inc["type"] == "school_rush" and near_dest:
                # 차로 학원 앞에 가는 중: 정차 대기 대신 한 바퀴 돌거나, 주차 되는 곳에서 기다리기
                spot = ctx.waiting_spots[0] if ctx.waiting_spots else None
                tail = f" 아니면 {spot['name']}에 차 대고 기다리셔도 돼요. {spot['parking']}예요." if spot else ""
                out.append(_iv(f"inc-{inc['id']}-drive", 2, "rush",
                               f"학원 앞에 차가 몰려 있어요. 서서 기다리면 단속될 수 있으니 한 바퀴 돌고 오시는 게 좋겠어요.{tail}",
                               "학원 앞이 막혀요. 한 바퀴 돌고 오세요.",
                               [{"label": "한 바퀴 도는 길 안내", "action": "loop_route"}] +
                               ([{"label": f"{spot['name']}{josa_ro(spot['name'])} 안내", "action": "go_spot", "spot_id": spot["id"]}] if spot else [])))
            if inc["type"] == "accident" and near_dest and not ctx.parked:
                out.append(_iv(f"inc-{inc['id']}", 2, "safety",
                               f"앞쪽 {inc['title']} 현장이 있어요. 천천히 지나가세요.", "앞에 사고 났어요. 천천히 가세요."))

    # 4) 학원·병원 일정이 바뀌었다는 알림
    for inc in ctx.incidents:
        if inc["type"] == "schedule_change":
            new_rb = ctx.return_by + timedelta(minutes=inc["extend_min"])
            label = "수업이" if ctx.purpose == "pickup" else "진료가" if ctx.purpose == "hospital" else "일정이"
            out.append(_iv(f"inc-{inc['id']}", 2, "schedule",
                           f"{label} {inc['extend_min']}분 늦게 끝난대요. 돌아올 시각을 {_when(new_rb)}까지로 미룰까요?",
                           f"{label} {inc['extend_min']}분 늦게 끝난대요.",
                           [{"label": f"{_when(new_rb)}까지로 미루기", "action": "extend", "minutes": inc["extend_min"]},
                            {"label": "그대로 두기", "action": "dismiss"}]))

    # 5) 새 일감: 일을 보겠다고 했고, 쉬는 중이 아니고, 서 있을 때만
    if ctx.wants_work and not ctx.resting and not active and ctx.parked and left > 15:
        for g in ctx.new_gigs:
            shop = (g.get("partner") or "").replace("샘플 ", "").replace("제휴 ", "") or "근처 가게"
            out.append(_iv(f"gig-{g['gig_id']}", 0, "new_gig",
                           f"근처 {shop}에서 일이 하나 올라왔어요. {g['breakdown']['task']}분짜리고, {g['finish_at']}이면 돌아와요. 보실래요?",
                           "새 일이 하나 올라왔어요.",
                           [{"label": "볼게요", "action": "show_gigs"}, {"label": "괜찮아요", "action": "dismiss"}]))

    # 5-2) 찾던 물건(동네 중고거래): 서 있고, 다녀올 시간이 될 때만. 쉬는 중이어도 알려 준다(일이 아니라 장보기)
    if not active and ctx.parked and not ctx.trip:
        for m in ctx.market_hits:
            won = f"{m['price'] // 10000}만 원" if m["price"] % 10000 == 0 else f"{m['price']:,}원"
            out.append(_iv(f"market-{m['id']}", 1, "market",
                           f"찾으시던 {m['keyword']}{josa(m['keyword'], '이', '가')} 근처에 올라왔어요. "
                           f"{won}이고, {m.get('condition_say') or '상태는 판매글을 확인해 주세요'}. "
                           f"{m['place']}까지 차로 {m['drive_min']}분이라 {m['finish_at']}이면 돌아와요. 판매자에게 구매 메시지 보내 볼까요?",
                           f"찾던 {m['keyword']}{josa(m['keyword'], '이', '가')} 근처에 올라왔어요.",
                           [{"label": "메시지 보내고 길 안내", "action": "market_go", "listing_id": m["id"]},
                            {"label": "괜찮아요", "action": "dismiss"}],
                           detail={"listing": m}))

    # 6) 약속 시각 알림 (업무가 없을 때)
    if not active:
        if 0 < left <= 10:
            out.append(_iv(f"remind-10-{rb}", 2, "remind",
                           f"{who}까지 {left}분 남았어요. 슬슬 정리하고 나가 보세요.", f"{left}분 남았어요."))
        elif left <= 0:
            out.append(_iv(f"remind-0-{rb}", 3, "remind", f"{who} 시간이에요.", f"{who} 시간이에요."))

    # 같은 순간에 여러 말을 겹쳐 하지 않는다: 늦을 위험을 말했으면 '지금 출발'·'비' 안내는 그 말에 이미 담겨 있다
    kinds = {x["kind"] for x in out}
    route_mentions_rain = any(x["kind"] in ("late", "tight", "info") and "비" in x["say"] for x in out)
    for x in out:
        if (x["kind"] == "leave" and "late" in kinds) or (x["kind"] == "weather" and route_mentions_rain):
            x["silent"] = True
    out.sort(key=lambda x: -x["priority"])
    return out
