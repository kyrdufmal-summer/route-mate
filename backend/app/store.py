"""정차 세션·일감 수락 상태 저장소.

MVP 는 프로세스 메모리 + 락으로 원자성을 보장한다. 기획서의 운영 구성은 PostgreSQL 이며,
같은 규칙을 `SELECT ... FOR UPDATE` + idempotency_key UNIQUE 제약으로 옮기면 된다.
"""
from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path(__file__).parent / "data"

# 일감 수락 상태 머신
TRANSITIONS = {
    "offered": {"accepted", "declined", "expired"},
    "accepted": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
}
STATE_KO = {"offered": "제안", "accepted": "수락", "in_progress": "진행 중", "completed": "완료",
            "cancelled": "취소", "declined": "거절", "expired": "만료"}


def load(name: str, key: str) -> list[dict]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))[key]


def coarse(lat: float, lng: float) -> tuple[float, float]:
    """감사 로그용 위치 최소화 (약 100m 격자)."""
    return round(lat, 3), round(lng, 3)


@dataclass
class Session:
    id: str
    created_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
    recommendations_paused: bool = False
    pause_reason: str | None = None
    assignment: dict[str, Any] | None = None


class ConflictError(Exception):
    pass


class Store:
    def __init__(self) -> None:
        self.lock = threading.RLock()
        self.sessions: dict[str, Session] = {}
        self.gig_owner: dict[str, str] = {}             # gig_id -> session_id (원자적 배정)
        self.idempotency: dict[str, dict] = {}          # key -> 최초 응답
        self.audit: list[dict] = []
        self.closed_gigs: set[str] = set()
        self.parking_lots = load("parking_lots.json", "lots")
        self.gigs = load("gigs.json", "gigs")
        self.places = load("places.json", "places")

    # --- audit ---
    def log(self, session_id: str | None, event: str, **detail: Any) -> None:
        self.audit.append({"at": datetime.now().isoformat(timespec="seconds"), "session": session_id,
                           "event": event, **detail})

    # --- sessions ---
    def create_session(self, data: dict) -> Session:
        with self.lock:
            s = Session(id=uuid.uuid4().hex[:12], created_at=datetime.now(), data=data)
            self.sessions[s.id] = s
            pos = data.get("position") or {}
            self.log(s.id, "session_created", position=coarse(pos.get("lat", 0), pos.get("lng", 0)))
            return s

    def get(self, sid: str) -> Session:
        s = self.sessions.get(sid)
        if not s:
            raise KeyError(sid)
        return s

    def delete_session(self, sid: str) -> None:
        """동의 철회·삭제: 세션 데이터와 배정을 지우고, 감사 로그에는 위치를 남기지 않는다."""
        with self.lock:
            s = self.sessions.pop(sid, None)
            if s and s.assignment:
                self.gig_owner.pop(s.assignment["gig_id"], None)
            for e in self.audit:
                if e.get("session") == sid:
                    e.pop("position", None)
            self.idempotency = {k: v for k, v in self.idempotency.items() if not k.startswith(sid + ":")}
            self.log(sid, "session_deleted")

    def taken_gigs(self, except_session: str | None = None) -> set[str]:
        return {g for g, owner in self.gig_owner.items() if owner != except_session} | self.closed_gigs

    # --- gig lifecycle ---
    def accept(self, sid: str, gig_id: str, idem_key: str, evaluation: dict) -> dict:
        key = f"{sid}:{idem_key}"
        with self.lock:
            if key in self.idempotency:                      # 같은 요청 재전송 → 같은 결과
                return {**self.idempotency[key], "idempotent_replay": True}
            s = self.get(sid)
            if s.assignment and s.assignment["state"] in ("accepted", "in_progress"):
                raise ConflictError("이미 진행 중인 업무가 있어요.")
            owner = self.gig_owner.get(gig_id)
            if owner and owner != sid:
                raise ConflictError("다른 사용자가 먼저 수락한 일감이에요.")
            self.gig_owner[gig_id] = sid
            s.assignment = {"gig_id": gig_id, "state": "accepted", "evaluation": evaluation,
                            "accepted_at": datetime.now().isoformat(timespec="seconds")}
            result = {"session_id": sid, "assignment": s.assignment}
            self.idempotency[key] = result
            self.log(sid, "gig_accepted", gig_id=gig_id, idempotency_key=idem_key)
            return result

    def transition(self, sid: str, new_state: str, reason: str | None = None) -> dict:
        with self.lock:
            s = self.get(sid)
            if not s.assignment:
                raise ConflictError("진행 중인 업무가 없어요.")
            cur = s.assignment["state"]
            if new_state not in TRANSITIONS.get(cur, set()):
                raise ConflictError(f"'{STATE_KO.get(cur, cur)}' 상태에서는 '{STATE_KO.get(new_state, new_state)}' 처리를 할 수 없어요.")
            s.assignment["state"] = new_state
            if new_state == "completed":
                self.closed_gigs.add(s.assignment["gig_id"])   # 완료된 일감은 재추천하지 않음
            if new_state in ("completed", "cancelled"):
                self.gig_owner.pop(s.assignment["gig_id"], None)
            self.log(sid, f"gig_{new_state}", gig_id=s.assignment["gig_id"], reason=reason)
            return s.assignment
