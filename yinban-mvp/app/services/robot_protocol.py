from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class RobotState(StrEnum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    BLOCKED = "BLOCKED"
    LINE_LOST = "LINE_LOST"
    ARRIVED = "ARRIVED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RobotEvent:
    state: RobotState
    route_id: str | None = None
    distance_cm: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class RobotSnapshot:
    mode: str
    connected: bool
    state: RobotState
    route_id: str | None = None
    distance_cm: float | None = None
    error: str | None = None
    progress: float | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


VALID_ROUTE_ID = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")


def encode_command(command: str, value: str | None = None) -> bytes:
    normalized = command.strip().upper()
    if normalized not in {"PING", "START", "STOP", "RESUME", "RESET"}:
        raise ValueError(f"Unsupported command: {command}")
    if normalized == "START":
        route_id = (value or "").strip().upper()
        if not VALID_ROUTE_ID.fullmatch(route_id):
            raise ValueError("START requires a valid route id")
        return f"START:{route_id}\n".encode("ascii")
    if value is not None:
        raise ValueError(f"{normalized} does not accept a value")
    return f"{normalized}\n".encode("ascii")


def parse_event(line: str) -> RobotEvent:
    message = line.strip().upper()
    if message == "READY":
        return RobotEvent(RobotState.IDLE)
    if message == "MOVING":
        return RobotEvent(RobotState.MOVING)
    if message == "LINE_LOST":
        return RobotEvent(RobotState.LINE_LOST, error="LINE_LOST")
    if message.startswith("BLOCKED:"):
        try:
            distance = float(message.split(":", 1)[1])
        except ValueError as exc:
            raise ValueError(f"Invalid distance event: {line}") from exc
        return RobotEvent(RobotState.BLOCKED, distance_cm=distance)
    if message.startswith("ARRIVED:"):
        route_id = message.split(":", 1)[1]
        if not VALID_ROUTE_ID.fullmatch(route_id):
            raise ValueError(f"Invalid route id in event: {line}")
        return RobotEvent(RobotState.ARRIVED, route_id=route_id)
    if message.startswith("ERROR:"):
        error = message.split(":", 1)[1] or "UNKNOWN"
        return RobotEvent(RobotState.ERROR, error=error)
    raise ValueError(f"Unknown robot event: {line}")
