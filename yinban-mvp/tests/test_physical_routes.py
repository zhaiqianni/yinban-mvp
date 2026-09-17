import pytest

from app.core.data_loader import load_json
from app.core.route_planner import RoutePlanner
from app.services.physical_routes import PhysicalRouteCatalog


def build_catalog() -> PhysicalRouteCatalog:
    return PhysicalRouteCatalog(load_json("physical_routes.json"))


def test_catalog_exposes_three_supported_physical_routes() -> None:
    catalog = build_catalog()

    assert catalog.route_ids == ("CARDIOLOGY", "PHARMACY", "TOILET")
    assert catalog.start_location_id == "lobby_start"
    assert catalog.get("CARDIOLOGY").outbound_actions == ("S", "X")
    assert catalog.get("TOILET").return_actions == ("U", "L", "X")
    assert catalog.get("PHARMACY").return_actions == ("U", "L", "S", "X")


def test_catalog_maps_return_missions_and_locations() -> None:
    catalog = build_catalog()

    assert catalog.return_mission_id("PHARMACY") == "RETURN_PHARMACY"
    assert catalog.base_route_id("RETURN_PHARMACY") == "PHARMACY"
    assert catalog.location_for_arrival("PHARMACY") == "pharmacy_1f"
    assert catalog.location_for_arrival("RETURN_PHARMACY") == "lobby_start"


def test_physical_routes_follow_the_same_nodes_as_the_web_map() -> None:
    catalog = build_catalog()
    route_data = load_json("routes.json")
    planner = RoutePlanner(route_data, "lobby_1f")

    for route_id in catalog.route_ids:
        physical = catalog.get(route_id)
        planned = planner.plan(physical.destination)
        node_ids = planned.node_ids
        if planned.physical_handoff_node_id:
            handoff_index = node_ids.index(planned.physical_handoff_node_id)
            node_ids = node_ids[: handoff_index + 1]
        assert tuple(node_ids) == physical.physical_node_ids
        assert planned.robot_route_id == route_id


@pytest.mark.parametrize(
    "actions",
    [(), ("Q", "X"), ("S",), ("S", "X", "R"), ("S", "U", "X")],
)
def test_catalog_rejects_invalid_action_queues(actions) -> None:
    config = {
        "startLocationId": "lobby_start",
        "startNodeId": "lobby_1f",
        "routes": {
            "TOILET": {
                "destination": "toilet",
                "destinationName": "卫生间",
                "locationId": "toilet_1f",
                "outboundActions": list(actions),
                "returnActions": ["U", "L", "X"],
                "physicalNodeIds": ["lobby_1f", "toilet_1f"]
            }
        }
    }

    with pytest.raises(ValueError):
        PhysicalRouteCatalog(config)
