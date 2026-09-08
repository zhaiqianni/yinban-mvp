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
    assert route.labels == ["门诊大厅", "3号电梯口", "药房"]
    assert [(point.x, point.y) for point in route.points] == [
        (92, 165),
        (285, 165),
        (285, 270),
    ]
    assert route.robot_route_id is None
    assert route.physical_available is False


def test_multiple_destinations_are_planned_in_order() -> None:
    route = build_planner().plan_sequence(["pharmacy", "laboratory"])
    assert route.labels == ["门诊大厅", "3号电梯口", "药房", "检验科"]
    assert route.destination == "laboratory"
    assert route.robot_route_id is None
    assert route.physical_available is False


def test_complex_route_follows_drawn_corridors_and_keeps_every_stop() -> None:
    route = build_planner().plan_sequence(
        ["toilet", "registration", "cardiology"]
    )
    assert route.labels == [
        "门诊大厅",
        "卫生间",
        "门诊大厅",
        "3号电梯口",
        "挂号处",
        "3号电梯口",
        "心内科",
    ]


def test_unknown_destination_is_rejected() -> None:
    with pytest.raises(KeyError):
        build_planner().plan("airport")
