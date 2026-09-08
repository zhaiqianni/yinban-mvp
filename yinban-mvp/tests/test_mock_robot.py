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
    assert robot.start("PHARMACY")[0] is False
    robot.start("CARDIOLOGY")
    robot.stop()
    assert robot.status().state == RobotState.IDLE


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
