from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class RobotState(StrEnum):
    IDLE = "IDLE"
    MOVING = "MOVING"
    TURNING = "TURNING"
    BLOCKED = "BLOCKED"
    LINE_LOST = "LINE_LOST"
    ARRIVED = "ARRIVED"
    NEEDS_RESET = "NEEDS_RESET"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RobotEvent:
    state: RobotState
    route_id: str | None = None
    distance_cm: float | None = None
    error: str | None = None
    node_index: int | None = None
    turn: str | None = None
    location_id: str | None = None
    needs_reset: bool = False


@dataclass(frozen=True)
class RobotSnapshot:
    mode: str
    connected: bool
    state: RobotState
    route_id: str | None = None
    distance_cm: float | None = None
    error: str | None = None
    progress: float | None = None
    mission_direction: str | None = None
    node_index: int = 0
    location_id: str | None = None
    needs_reset: bool = False
    return_route_id: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


VALID_ROUTE_ID = re.compile(r"^[A-Z][A-Z0-9_]{0,39}$")
VALID_ACTIONS = frozenset({"S", "L", "R", "U", "X"})
MAX_ROUTE_ACTIONS = 8


def validate_actions(
    actions: list[str] | tuple[str, ...],
    *,
    allow_uturn: bool = True,
) -> tuple[str, ...]:
    normalized = tuple(str(action).strip().upper() for action in actions)
    if not normalized or len(normalized) > MAX_ROUTE_ACTIONS:
        raise ValueError("A route requires between 1 and 8 actions")
    if any(action not in VALID_ACTIONS for action in normalized):
        raise ValueError("Route contains an unsupported action")
    if normalized[-1] != "X" or "X" in normalized[:-1]:
        raise ValueError("A route must end with exactly one X action")
    if "U" in normalized:
        if not allow_uturn or normalized[0] != "U" or normalized.count("U") != 1:
            raise ValueError("U is only allowed once as the first action")
    return normalized


def encode_run_command(route_id: str, actions: list[str] | tuple[str, ...]) -> bytes:
    normalized_route = route_id.strip().upper()
    if not VALID_ROUTE_ID.fullmatch(normalized_route):
        raise ValueError("RUN requires a valid route id")
    normalized_actions = validate_actions(actions)
    action_text = ",".join(normalized_actions)
    return f"RUN:{normalized_route}:{action_text}\n".encode("ascii")


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
    if message == "HOME_READY":
        return RobotEvent(RobotState.IDLE, location_id="lobby_start")
    if message == "NEEDS_RESET":
        return RobotEvent(RobotState.NEEDS_RESET, needs_reset=True)
    if message == "MOVING":
        return RobotEvent(RobotState.MOVING)
    if message.startswith("MOVING:"):
        route_id = message.split(":", 1)[1]
        if not VALID_ROUTE_ID.fullmatch(route_id):
            raise ValueError(f"Invalid route id in event: {line}")
        return RobotEvent(RobotState.MOVING, route_id=route_id)
    if message.startswith("NODE:"):
        parts = message.split(":")
        if len(parts) != 3 or not VALID_ROUTE_ID.fullmatch(parts[1]):
            raise ValueError(f"Invalid node event: {line}")
        try:
            node_index = int(parts[2])
        except ValueError as exc:
            raise ValueError(f"Invalid node event: {line}") from exc
        if node_index < 1 or node_index > MAX_ROUTE_ACTIONS:
            raise ValueError(f"Invalid node event: {line}")
        return RobotEvent(
            RobotState.MOVING,
            route_id=parts[1],
            node_index=node_index,
        )
    if message.startswith("TURNING:"):
        turn = message.split(":", 1)[1]
        if turn not in {"LEFT", "RIGHT", "UTURN", "STRAIGHT"}:
            raise ValueError(f"Invalid turn event: {line}")
        return RobotEvent(RobotState.TURNING, turn=turn)
    if message == "LINE_LOST":
        return RobotEvent(
            RobotState.LINE_LOST,
            error="LINE_LOST",
            needs_reset=True,
        )
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
        return RobotEvent(RobotState.ERROR, error=error, needs_reset=True)
    raise ValueError(f"Unknown robot event: {line}")
