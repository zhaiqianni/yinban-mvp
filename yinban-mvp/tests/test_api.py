from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.mock_robot import MockRobot


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_health_and_dialogue_api() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        response = client.post("/api/dialogue", json={"text": "我要去心内科"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "navigate"
        assert payload["robot_route_id"] == "CARDIOLOGY"
        assert payload["physical_handoff_node_id"] == "elevator3_1f"
        assert payload["physical_available"] is True
        assert [point["floor"] for point in payload["route_points"]] == [1, 1, 3, 3]


def test_dialogue_api_returns_all_requested_destinations() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        response = client.post(
            "/api/dialogue",
            json={"text": "我先去药房，再去检验科"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "navigate"
        assert payload["destinations"] == ["pharmacy", "laboratory"]
        assert payload["destination_names"] == ["药房", "检验科"]
        assert payload["route"] == [
            "门诊大厅（一楼）",
            "3号电梯口（一楼）",
            "药房（一楼）",
            "检验科（一楼）",
        ]
        assert [point["node_id"] for point in payload["route_points"]] == [
            "lobby_1f",
            "elevator3_1f",
            "pharmacy_1f",
            "laboratory_1f",
        ]
        assert "药房，位于" in payload["answer"]
        assert "检验科，位于" in payload["answer"]
        assert payload["robot_route_id"] is None
        assert payload["physical_available"] is False
        assert payload["guide_route_id"] == "SIMULATION"
        assert payload["guide_available"] is True


def test_robot_start_and_status_api() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        response = client.post(
            "/api/robot/start",
            json={"routeId": "CARDIOLOGY"},
        )
        assert response.status_code == 200
        assert response.json()["accepted"] is True
        status = client.get("/api/robot/status").json()
        assert status["mode"] == "simulation"
        assert status["state"] == "MOVING"
        assert status["mission_direction"] == "outbound"
        assert status["location_id"] is None
        assert 0 <= status["progress"] < 0.01


def test_simulation_route_can_start_without_a_physical_route() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        dialogue = client.post(
            "/api/dialogue",
            json={"text": "先去卫生间，再去挂号处，然后去心内科"},
        ).json()
        assert dialogue["route"] == [
            "门诊大厅（一楼）",
            "卫生间（一楼）",
            "门诊大厅（一楼）",
            "3号电梯口（一楼）",
            "挂号处（一楼）",
            "3号电梯入口（一楼）",
            "乘坐3号电梯前往三楼",
            "3号电梯出口（三楼）",
            "心内科（三楼）",
        ]
        response = client.post(
            "/api/robot/start",
            json={"routeId": dialogue["guide_route_id"]},
        )
        assert dialogue["guide_available"] is True
        assert response.json()["accepted"] is True


def test_dialogue_api_returns_cross_floor_round_trip() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        payload = client.post(
            "/api/dialogue",
            json={"text": "我想去心内科然后再去卫生间"},
        ).json()
        assert payload["destination_names"] == ["心内科", "卫生间"]
        assert "乘坐3号电梯前往三楼" in payload["route"]
        assert "乘坐3号电梯返回一楼" in payload["route"]
        assert "路线中将乘坐3号电梯前往三楼" in payload["answer"]
        assert "随后乘坐3号电梯返回一楼" in payload["answer"]
        assert [point["floor"] for point in payload["route_points"]] == [
            1,
            1,
            3,
            3,
            3,
            1,
            1,
            1,
        ]
        assert payload["guide_route_id"] == "SIMULATION"
        assert payload["guide_available"] is True


def test_pharmacy_has_a_physical_route() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        dialogue = client.post(
            "/api/dialogue", json={"text": "我要去药房"}
        ).json()
        assert dialogue["robot_route_id"] == "PHARMACY"
        assert dialogue["physical_available"] is True
        response = client.post(
            "/api/robot/start",
            json={"routeId": "PHARMACY"},
        )
        assert response.json()["accepted"] is True


def test_robot_return_api_requires_matching_arrival() -> None:
    clock = Clock()
    robot = MockRobot(clock)
    app = create_app(Settings(mode="simulation"), robot)
    with TestClient(app) as client:
        assert client.post(
            "/api/robot/return", json={"routeId": "PHARMACY"}
        ).json()["accepted"] is False
        assert client.post(
            "/api/robot/start", json={"routeId": "PHARMACY"}
        ).json()["accepted"] is True
        clock.value = 9.0
        status = client.get("/api/robot/status").json()
        assert status["state"] == "ARRIVED"
        assert status["return_route_id"] == "PHARMACY"
        assert client.post(
            "/api/robot/return", json={"routeId": "PHARMACY"}
        ).json()["accepted"] is True
