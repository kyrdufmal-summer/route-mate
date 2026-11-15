"""운전 중 상호작용 제한 (Driver Distraction 가드).

실차에서는 Pleos Vehicle SDK 의 승인된 차량 상태 신호(기어·속도 등)를 입력으로 받는다.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VehicleState:
    gear: str = "P"          # P/R/N/D
    speed_kmh: float = 0.0

    @property
    def stationary(self) -> bool:
        return self.gear == "P" or self.speed_kmh < 1.0

    @property
    def parked(self) -> bool:
        return self.gear == "P"


class DrivingLockError(Exception):
    pass


def require_parked(state: VehicleState, action: str) -> None:
    if not state.parked:
        raise DrivingLockError(f"주행 중에는 {action} 수 없어요. 차를 세우고(P단) 다시 시도해 주세요.")


def brief_for_driving(text: str, limit: int = 40) -> str:
    """주행 중에는 짧은 음성 안내 한 문장만 허용."""
    return text if len(text) <= limit else text[: limit - 1] + "…"
