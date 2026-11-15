"""음성 요청 의도 해석.

기획서 원칙: LLM 은 의도 이해·설명에만 사용하고 안전·계약 판단은 규칙 기반으로 처리한다.
MVP 는 외부 키 없이 동작하도록 규칙 기반 파서를 기본 구현으로 두고,
같은 인터페이스(parse)로 LLM 파서를 끼울 수 있게 했다. 어떤 파서든 결과는 '제안'일 뿐이며
FLEX WINDOW 는 사용자가 화면에서 확인한 값으로만 저장된다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ParsedIntent:
    return_by: str | None = None          # "HH:MM"
    return_to_here: bool = False
    wants_work: bool | None = None
    min_buffer_min: int | None = None
    max_drive_min: int | None = None
    keywords: list[str] = field(default_factory=list)
    confidence: float = 0.0
    needs_confirmation: bool = True


KEYWORDS = ["아이 동반 식당", "반찬가게", "약국", "주차 편한 상점", "카페", "휴식"]

TIME_RE = re.compile(r"(오전|오후)?\s*(\d{1,2})\s*(?:[:시]\s*(\d{1,2})?\s*분?|시)")


def parse(utterance: str, now: datetime | None = None) -> ParsedIntent:
    text = utterance.replace(" ", "")
    out = ParsedIntent()
    hits = 0

    m = TIME_RE.search(utterance)
    if m:
        ampm, h, mm = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if ampm == "오후" and h < 12:
            h += 12
        elif ampm is None and now is not None and h < 12 and now.hour >= 12:
            h += 12  # "5시 55분" 을 오후 시간대에 말하면 17:55 로 해석
        if 0 <= h < 24 and 0 <= mm < 60:
            out.return_by = f"{h:02d}:{mm:02d}"
            hits += 1

    if any(k in text for k in ["여기돌아", "이곳에돌아", "여기로돌아", "원래장소", "이자리"]):
        out.return_to_here = True
        hits += 1

    if any(k in text for k in ["일도볼", "일감", "일할", "일하고", "가까운일", "부업"]):
        out.wants_work = True
        hits += 1
    if any(k in text for k in ["쉬고싶", "쉴래", "일은안", "일안할", "휴식만"]):
        out.wants_work = False
        hits += 1

    b = re.search(r"(\d+)\s*분\s*(?:이상)?\s*여유", utterance)
    if b:
        out.min_buffer_min = int(b.group(1))
        hits += 1
    d = re.search(r"최대\s*(\d+)\s*분\s*우회", utterance)
    if d:
        out.max_drive_min = int(d.group(1))
        hits += 1

    out.keywords = [k for k in KEYWORDS if k.replace(" ", "") in text]
    hits += bool(out.keywords)
    out.confidence = min(1.0, hits / 3)
    return out
