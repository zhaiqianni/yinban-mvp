from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import RLock
from typing import Callable

from app.services.robot_protocol import RobotSnapshot, RobotState


class MockRobot:
    mode = "simulation"

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = RLock()
        self._state = RobotState.IDLE
        self._route_id: str | None = None
        self._started_at: float | None = None
        self._paused_total = 0.0
        self._manual_pause_at: float | None = None
        self._error: str | None = None

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def start(self, route_id: str) -> tuple[bool, str]:
        with self._lock:
            if route_id != "CARDIOLOGY":
                return False, "该实体路线尚未实现"
            self._route_id = route_id
            self._state = RobotState.MOVING
            self._started_at = self._clock()
            self._paused_total = 0.0
            self._manual_pause_at = None
            self._error = None
            return True, "模拟机器人已出发"

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            self._state = RobotState.IDLE
            self._started_at = None
            self._manual_pause_at = None
            return True, "机器人已停止"

    def resume(self) -> tuple[bool, str]:
        with self._lock:
            if self._state not in {RobotState.BLOCKED, RobotState.LINE_LOST}:
                return False, "当前状态无需继续"
            if self._state == RobotState.BLOCKED and self._started_at is not None:
                self._started_at = self._clock() - 4.0
                self._paused_total = 0.0
            self._state = RobotState.MOVING
            return True, "机器人继续运行"

    def reset(self) -> tuple[bool, str]:
        with self._lock:
            self._state = RobotState.IDLE
            self._route_id = None
            self._started_at = None
            self._paused_total = 0.0
            self._manual_pause_at = None
            self._error = None
            return True, "机器人已复位"

    def status(self) -> RobotSnapshot:
        with self._lock:
            self._advance()
            distance = 18.0 if self._state == RobotState.BLOCKED else None
            return RobotSnapshot(
                mode=self.mode,
                connected=True,
                state=self._state,
                route_id=self._route_id,
                distance_cm=distance,
                error=self._error,
                updated_at=datetime.now(UTC),
            )

    def _advance(self) -> None:
        if self._started_at is None or self._state in {
            RobotState.IDLE,
            RobotState.ARRIVED,
            RobotState.ERROR,
            RobotState.LINE_LOST,
        }:
            return
        elapsed = self._clock() - self._started_at - self._paused_total
        if 2.5 <= elapsed < 4.0:
            self._state = RobotState.BLOCKED
        elif elapsed >= 6.5:
            self._state = RobotState.ARRIVED
        else:
            self._state = RobotState.MOVING
