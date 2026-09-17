import pytest

from app.core.data_loader import load_json
from app.core.route_planner import RoutePlanner


def build_planner() -> RoutePlanner:
    hospital = load_json("hospital.json")
    return RoutePlanner(load_json("routes.json"), hospital["startNode"])


def test_cardiology_has_physical_route() -> None:
    route = build_planner().plan("cardiology")
    assert route.labels == [
        "门诊大厅（一楼）",
        "3号电梯入口（一楼）",
        "乘坐3号电梯前往三楼",
        "3号电梯出口（三楼）",
        "心内科（三楼）",
    ]
    assert [point.floor for point in route.points] == [1, 1, 3, 3]
    assert route.robot_route_id == "CARDIOLOGY"
    assert route.physical_handoff_node_id == "elevator3_1f"
    assert route.physical_available is True


def test_pharmacy_has_physical_route() -> None:
    route = build_planner().plan("pharmacy")
    assert route.labels == ["门诊大厅（一楼）", "3号电梯口（一楼）", "药房（一楼）"]
    assert [(point.x, point.y) for point in route.points] == [
        (95, 165),
        (300, 165),
        (300, 270),
    ]
    assert route.robot_route_id == "PHARMACY"
    assert route.physical_available is True


def test_toilet_has_physical_route() -> None:
    route = build_planner().plan("toilet")
    assert route.robot_route_id == "TOILET"
    assert route.physical_available is True


def test_multiple_destinations_are_planned_in_order() -> None:
    route = build_planner().plan_sequence(["pharmacy", "laboratory"])
    assert route.labels == [
        "门诊大厅（一楼）",
        "3号电梯口（一楼）",
        "药房（一楼）",
        "检验科（一楼）",
    ]
    assert route.destination == "laboratory"
    assert route.robot_route_id is None
    assert route.physical_available is False


def test_complex_route_follows_drawn_corridors_and_keeps_every_stop() -> None:
    route = build_planner().plan_sequence(
        ["toilet", "registration", "cardiology"]
    )
    assert route.labels == [
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


def test_cross_floor_round_trip_includes_both_elevator_directions() -> None:
    route = build_planner().plan_sequence(["cardiology", "toilet"])
    assert route.labels == [
        "门诊大厅（一楼）",
        "3号电梯入口（一楼）",
        "乘坐3号电梯前往三楼",
        "3号电梯出口（三楼）",
        "心内科（三楼）",
        "3号电梯入口（三楼）",
        "乘坐3号电梯返回一楼",
        "3号电梯出口（一楼）",
        "门诊大厅（一楼）",
        "卫生间（一楼）",
    ]
    assert [point.floor for point in route.points] == [1, 1, 3, 3, 3, 1, 1, 1]


def test_unknown_destination_is_rejected() -> None:
    with pytest.raises(KeyError):
        build_planner().plan("airport")
