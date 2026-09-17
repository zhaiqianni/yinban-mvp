import pytest

from app.services.robot_protocol import (
    RobotState,
    encode_command,
    encode_run_command,
    parse_event,
)


def test_commands_are_line_delimited() -> None:
    assert encode_command("ping") == b"PING\n"
    assert encode_command("start", "cardiology") == b"START:CARDIOLOGY\n"
    assert encode_run_command("pharmacy", ["S", "R", "X"]) == (
        b"RUN:PHARMACY:S,R,X\n"
    )


def test_invalid_command_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_command("forward")
    with pytest.raises(ValueError):
        encode_command("start", "bad route")
    with pytest.raises(ValueError):
        encode_run_command("PHARMACY", ["S", "Q", "X"])
    with pytest.raises(ValueError):
        encode_run_command("PHARMACY", ["S", "R"])
    with pytest.raises(ValueError):
        encode_run_command("PHARMACY", ["S", "U", "X"])


def test_robot_events_are_parsed() -> None:
    assert parse_event("READY").state == RobotState.IDLE
    assert parse_event("HOME_READY").location_id == "lobby_start"
    assert parse_event("NEEDS_RESET").needs_reset is True
    moving = parse_event("MOVING:PHARMACY")
    assert moving.state == RobotState.MOVING
    assert moving.route_id == "PHARMACY"
    node = parse_event("NODE:PHARMACY:2")
    assert node.route_id == "PHARMACY"
    assert node.node_index == 2
    turning = parse_event("TURNING:RIGHT")
    assert turning.state == RobotState.TURNING
    assert turning.turn == "RIGHT"
    blocked = parse_event("BLOCKED:18.5")
    assert blocked.state == RobotState.BLOCKED
    assert blocked.distance_cm == 18.5
    arrived = parse_event("ARRIVED:CARDIOLOGY")
    assert arrived.state == RobotState.ARRIVED
    assert arrived.route_id == "CARDIOLOGY"
    assert parse_event("ERROR:SENSOR").error == "SENSOR"


def test_unknown_event_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_event("GOING")
