import pytest

from app.core.data_loader import load_json
from app.core.route_planner import RoutePlanner


def build_planner() -> RoutePlanner:
    hospital = load_json("hospital.json")
    return RoutePlanner(load_json("routes.json"), hospital["startNode"])


def test_cardiology_has_physical_route() -> None:
    route = build_planner().plan("cardiology")
    assert route.labels == ["门诊大厅", "3号电梯口", "心内科"]
    assert route.robot_route_id == "CARDIOLOGY"
    assert route.physical_available is True


def test_pharmacy_is_display_only() -> None:
    route = build_planner().plan("pharmacy")
    assert route.labels == ["门诊大厅", "药房"]
    assert route.robot_route_id is None
    assert route.physical_available is False


def test_unknown_destination_is_rejected() -> None:
    with pytest.raises(KeyError):
        build_planner().plan("airport")

