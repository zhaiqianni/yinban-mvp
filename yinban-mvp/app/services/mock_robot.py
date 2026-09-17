from __future__ import annotations

import time
from datetime import UTC, datetime
from threading import RLock
from typing import Callable

from app.core.data_loader import load_json
from app.services.physical_routes import PhysicalRouteCatalog
from app.services.robot_protocol import RobotSnapshot, RobotState


class MockRobot:
    mode = "simulation"

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        physical_routes: PhysicalRouteCatalog | None = None,
    ) -> None:
        self._clock = clock
        self._routes = physical_routes or PhysicalRouteCatalog(
            load_json("physical_routes.json")
        )
        self._lock = RLock()
        self._state = RobotState.IDLE
        self._route_id: str | None = None
        self._mission_direction: str | None = None
        self._node_index = 0
        self._location_id: str | None = self._routes.start_location_id
        self._needs_reset = False
        self._return_route_id: str | None = None
        self._started_at: float | None = None
        self._paused_total = 0.0
        self._manual_pause_at: float | None = None
        self._error: str | None = None
        self._travel_duration = 5.0
        self._block_at = 2.5
        self._block_duration = 1.5

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def start(self, route_id: str, step_count: int = 2) -> tuple[bool, str]:
        normalized = route_id.strip().upper()
        with self._lock:
            if normalized == "SIMULATION":
                return self._begin_mission(normalized, step_count, "outbound")
            if not self._routes.supports(normalized):
                return False, "未知的模拟路线"
            if (
                self._state != RobotState.IDLE
                or self._needs_reset
                or self._location_id != self._routes.start_location_id
            ):
                return False, "小车不在已确认的固定起点，请先归位并复位"
            action_count = len(self._routes.get(normalized).outbound_actions)
            return self._begin_mission(normalized, action_count + 1, "outbound")

    def return_to_start(self, route_id: str) -> tuple[bool, str]:
        normalized = route_id.strip().upper()
        with self._lock:
            if not self._routes.supports(normalized):
                return False, "未知的实体返程路线"
            route = self._routes.get(normalized)
            if (
                self._state != RobotState.ARRIVED
                or self._needs_reset
                or self._location_id != route.location_id
                or self._return_route_id != normalized
            ):
                return False, "当前位置与返程路线不匹配，不能启动返程"
            mission_id = self._routes.return_mission_id(normalized)
            action_count = len(route.return_actions)
            return self._begin_mission(mission_id, action_count + 1, "return")

    def _begin_mission(
        self, route_id: str, step_count: int, direction: str
    ) -> tuple[bool, str]:
        self._route_id = route_id
        self._mission_direction = direction
        self._state = RobotState.MOVING
        self._started_at = self._clock()
        self._paused_total = 0.0
        self._manual_pause_at = None
        self._error = None
        self._node_index = 0
        self._location_id = None
        self._needs_reset = False
        self._return_route_id = None
        self._travel_duration = max(5.0, (step_count - 1) * 2.0)
        self._block_at = self._travel_duration / 2.0
        message = "模拟机器人开始返程" if direction == "return" else "模拟机器人已出发"
        return True, message

    def stop(self) -> tuple[bool, str]:
        with self._lock:
            was_running = self._state in {
                RobotState.MOVING,
                RobotState.TURNING,
                RobotState.BLOCKED,
            }
            self._started_at = None
            self._manual_pause_at = None
            if was_running:
                self._state = RobotState.NEEDS_RESET
                self._needs_reset = True
                self._location_id = None
                self._return_route_id = None
                return True, "机器人已停车，位置未知，请人工归位并复位"
            return True, "机器人保持停止"

    def resume(self) -> tuple[bool, str]:
        with self._lock:
            if self._state != RobotState.BLOCKED:
                return False, "仅障碍暂停状态可以继续"
            if self._started_at is not None:
                self._started_at = self._clock() - (
                    self._block_at + self._block_duration
                )
                self._paused_total = 0.0
            self._state = RobotState.MOVING
            return True, "机器人继续运行"

    def reset(self) -> tuple[bool, str]:
        with self._lock:
            self._state = RobotState.IDLE
            self._route_id = None
            self._mission_direction = None
            self._node_index = 0
            self._location_id = self._routes.start_location_id
            self._needs_reset = False
            self._return_route_id = None
            self._started_at = None
            self._paused_total = 0.0
            self._manual_pause_at = None
            self._error = None
            return True, "已确认小车位于固定起点"

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
                progress=self._progress(),
                mission_direction=self._mission_direction,
                node_index=self._node_index,
                location_id=self._location_id,
                needs_reset=self._needs_reset,
                return_route_id=self._return_route_id,
                updated_at=datetime.now(UTC),
            )

    def _progress(self) -> float:
        if self._state == RobotState.ARRIVED:
            return 1.0
        if self._started_at is None:
            return 0.0
        elapsed = max(0.0, self._clock() - self._started_at - self._paused_total)
        if elapsed < self._block_at:
            return elapsed / self._travel_duration
        if elapsed < self._block_at + self._block_duration:
            return self._block_at / self._travel_duration
        return min(1.0, (elapsed - self._block_duration) / self._travel_duration)

    def _advance(self) -> None:
        if self._started_at is None or self._state in {
            RobotState.IDLE,
            RobotState.ARRIVED,
            RobotState.NEEDS_RESET,
            RobotState.ERROR,
            RobotState.LINE_LOST,
        }:
            return
        elapsed = self._clock() - self._started_at - self._paused_total
        if self._block_at <= elapsed < self._block_at + self._block_duration:
            self._state = RobotState.BLOCKED
            return
        if elapsed < self._travel_duration + self._block_duration:
            self._state = RobotState.MOVING
            self._node_index = max(0, int(self._progress() * 2))
            return

        self._started_at = None
        self._node_index = 0
        if self._route_id == "SIMULATION":
            self._state = RobotState.ARRIVED
            self._location_id = self._routes.start_location_id
            return
        if self._mission_direction == "return":
            self._state = RobotState.IDLE
            self._route_id = None
            self._mission_direction = None
            self._location_id = self._routes.start_location_id
            self._return_route_id = None
            return

        self._state = RobotState.ARRIVED
        assert self._route_id is not None
        route = self._routes.get(self._route_id)
        self._location_id = route.location_id
        self._return_route_id = route.route_id
