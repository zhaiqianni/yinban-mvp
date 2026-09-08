import pytest

from app.services.robot_protocol import RobotState, encode_command, parse_event


def test_commands_are_line_delimited() -> None:
    assert encode_command("ping") == b"PING\n"
    assert encode_command("start", "cardiology") == b"START:CARDIOLOGY\n"


def test_invalid_command_is_rejected() -> None:
    with pytest.raises(ValueError):
        encode_command("forward")
    with pytest.raises(ValueError):
        encode_command("start", "bad route")


def test_robot_events_are_parsed() -> None:
    assert parse_event("READY").state == RobotState.IDLE
    assert parse_event("MOVING").state == RobotState.MOVING
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

