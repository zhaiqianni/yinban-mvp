from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.mock_robot import MockRobot


def test_health_and_dialogue_api() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"
        response = client.post("/api/dialogue", json={"text": "我要去心内科"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["intent"] == "navigate"
        assert payload["robot_route_id"] == "CARDIOLOGY"
        assert payload["physical_available"] is True


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
        assert payload["route"] == ["门诊大厅", "药房", "检验科"]
        assert "药房位于" in payload["answer"]
        assert "检验科位于" in payload["answer"]
        assert payload["robot_route_id"] is None
        assert payload["physical_available"] is False


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


def test_display_only_route_cannot_start_robot() -> None:
    app = create_app(Settings(mode="simulation"), MockRobot())
    with TestClient(app) as client:
        response = client.post(
            "/api/robot/start",
            json={"routeId": "PHARMACY"},
        )
        assert response.json()["accepted"] is False
