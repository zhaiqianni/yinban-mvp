from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from app.services.robot_protocol import VALID_ROUTE_ID, validate_actions


@dataclass(frozen=True)
class PhysicalRoute:
    route_id: str
    destination: str
    destination_name: str
    location_id: str
    outbound_actions: tuple[str, ...]
    return_actions: tuple[str, ...]
    physical_node_ids: tuple[str, ...]


class PhysicalRouteCatalog:
    def __init__(self, config: dict[str, Any]) -> None:
        self.start_location_id = str(config["startLocationId"])
        self.start_node_id = str(config["startNodeId"])
        self._routes: dict[str, PhysicalRoute] = {}
        for route_id, raw in config.get("routes", {}).items():
            normalized_id = route_id.strip().upper()
            if not VALID_ROUTE_ID.fullmatch(normalized_id):
                raise ValueError(f"Invalid physical route id: {route_id}")
            outbound = validate_actions(raw["outboundActions"], allow_uturn=False)
            returning = validate_actions(raw["returnActions"], allow_uturn=True)
            if not returning or returning[0] != "U":
                raise ValueError(f"Return route {normalized_id} must begin with U")
            node_ids = tuple(str(value) for value in raw["physicalNodeIds"])
            if len(node_ids) < 2:
                raise ValueError(f"Physical route {normalized_id} needs two nodes")
            self._routes[normalized_id] = PhysicalRoute(
                route_id=normalized_id,
                destination=str(raw["destination"]),
                destination_name=str(raw["destinationName"]),
                location_id=str(raw["locationId"]),
                outbound_actions=outbound,
                return_actions=returning,
                physical_node_ids=node_ids,
            )
        if not self._routes:
            raise ValueError("At least one physical route is required")

    @property
    def route_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._routes))

    def supports(self, route_id: str) -> bool:
        return route_id.strip().upper() in self._routes

    def get(self, route_id: str) -> PhysicalRoute:
        normalized = route_id.strip().upper()
        try:
            return self._routes[normalized]
        except KeyError as exc:
            raise KeyError(f"Unknown physical route: {route_id}") from exc

    def return_mission_id(self, route_id: str) -> str:
        route = self.get(route_id)
        return f"RETURN_{route.route_id}"

    def base_route_id(self, mission_id: str) -> str:
        normalized = mission_id.strip().upper()
        if normalized.startswith("RETURN_"):
            normalized = normalized[7:]
        return self.get(normalized).route_id

    def actions_for_mission(self, mission_id: str) -> tuple[str, ...]:
        normalized = mission_id.strip().upper()
        route = self.get(self.base_route_id(normalized))
        if normalized.startswith("RETURN_"):
            return route.return_actions
        return route.outbound_actions

    def location_for_arrival(self, mission_id: str) -> str:
        normalized = mission_id.strip().upper()
        if normalized.startswith("RETURN_"):
            self.base_route_id(normalized)
            return self.start_location_id
        return self.get(normalized).location_id

    def route_for_location(self, location_id: str) -> PhysicalRoute | None:
        return next(
            (route for route in self._routes.values() if route.location_id == location_id),
            None,
        )

    def validate_actions_for_mission(
        self,
        mission_id: str,
        actions: Iterable[str],
    ) -> tuple[str, ...]:
        expected = self.actions_for_mission(mission_id)
        normalized = tuple(str(action).strip().upper() for action in actions)
        if normalized != expected:
            raise ValueError(f"Actions do not match mission {mission_id}")
        return normalized
