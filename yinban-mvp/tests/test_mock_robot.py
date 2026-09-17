from app.services.mock_robot import MockRobot
from app.services.robot_protocol import RobotState


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_mock_robot_runs_complete_scenario() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    accepted, _ = robot.start("CARDIOLOGY")
    assert accepted is True
    assert robot.status().state == RobotState.MOVING

    clock.value = 3.0
    assert robot.status().state == RobotState.BLOCKED

    clock.value = 4.5
    assert robot.status().state == RobotState.MOVING

    clock.value = 7.0
    assert robot.status().state == RobotState.ARRIVED


def test_mock_robot_rejects_unknown_route_and_stops() -> None:
    robot = MockRobot()
    assert robot.start("REGISTRATION")[0] is False
    robot.start("CARDIOLOGY")
    robot.stop()
    assert robot.status().state == RobotState.NEEDS_RESET
    assert robot.status().needs_reset is True


def test_mock_robot_accepts_generic_screen_simulation() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    accepted, _ = robot.start("SIMULATION")
    assert accepted is True
    assert robot.status().progress == 0
    clock.value = 1.25
    assert robot.status().progress == 0.25
    clock.value = 6.5
    assert robot.status().progress == 1


def test_complex_simulation_duration_scales_with_route_length() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    robot.start("SIMULATION", step_count=7)
    clock.value = 3.0
    assert robot.status().state == RobotState.MOVING
    assert robot.status().progress == 0.25
    clock.value = 6.5
    assert robot.status().state == RobotState.BLOCKED
    clock.value = 13.5
    assert robot.status().state == RobotState.ARRIVED


def test_mock_robot_can_resume_from_blocked_state() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    robot.start("CARDIOLOGY")
    clock.value = 3.0
    assert robot.status().state == RobotState.BLOCKED
    accepted, _ = robot.resume()
    assert accepted is True
    assert robot.status().state == RobotState.MOVING


def test_mock_robot_supports_all_physical_routes_and_return() -> None:
    clock = Clock()
    robot = MockRobot(clock)

    accepted, _ = robot.start("PHARMACY")
    assert accepted is True
    clock.value = 9.0
    arrived = robot.status()
    assert arrived.state == RobotState.ARRIVED
    assert arrived.location_id == "pharmacy_1f"
    assert arrived.return_route_id == "PHARMACY"

    accepted, _ = robot.return_to_start("PHARMACY")
    assert accepted is True
    returning = robot.status()
    assert returning.route_id == "RETURN_PHARMACY"
    assert returning.mission_direction == "return"
    clock.value = 20.0
    home = robot.status()
    assert home.state == RobotState.IDLE
    assert home.location_id == "lobby_start"
    assert home.return_route_id is None


def test_mock_robot_rejects_route_when_not_at_confirmed_start() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    robot.start("TOILET")
    clock.value = 7.0
    assert robot.status().state == RobotState.ARRIVED

    assert robot.start("PHARMACY")[0] is False
    assert robot.return_to_start("PHARMACY")[0] is False
    assert robot.return_to_start("TOILET")[0] is True
