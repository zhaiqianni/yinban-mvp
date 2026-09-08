from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoutePoint:
    node_id: str
    label: str
    x: float
    y: float


@dataclass(frozen=True)
class PlannedRoute:
    destination: str
    destination_name: str
    node_ids: list[str]
    labels: list[str]
    points: list[RoutePoint]
    robot_route_id: str | None

    @property
    def physical_available(self) -> bool:
        return self.robot_route_id is not None


class RoutePlanner:
    def __init__(self, routes: dict[str, Any], start_node: str = "lobby") -> None:
        self.routes = routes
        self.start_node = start_node
        self.graph: dict[str, list[str]] = {
            node_id: [] for node_id in self.routes["nodes"]
        }
        for left, right in self.routes["edges"]:
            self.graph[left].append(right)
            self.graph[right].append(left)

    def plan(self, destination: str) -> PlannedRoute:
        return self.plan_sequence([destination])

    def plan_sequence(self, destinations: list[str] | tuple[str, ...]) -> PlannedRoute:
        if not destinations:
            raise ValueError("At least one destination is required")

        node_ids: list[str] = [self.start_node]
        current = self.start_node
        for destination in destinations:
            destination_config = self.routes["destinations"].get(destination)
            if destination_config is None:
                raise KeyError(f"Unknown destination: {destination}")
            target = destination_config["node"]
            segment = self._shortest_path(current, target)
            node_ids.extend(segment[1:])
            current = target

        destination = destinations[-1]
        destination_config = self.routes["destinations"].get(destination)
        labels = [self.routes["nodes"][node_id]["label"] for node_id in node_ids]
        points = [
            RoutePoint(
                node_id=node_id,
                label=self.routes["nodes"][node_id]["label"],
                x=self.routes["nodes"][node_id]["x"],
                y=self.routes["nodes"][node_id]["y"],
            )
            for node_id in node_ids
        ]
        return PlannedRoute(
            destination=destination,
            destination_name=self.routes["nodes"][current]["label"],
            node_ids=node_ids,
            labels=labels,
            points=points,
            robot_route_id=(
                destination_config.get("robotRouteId")
                if len(destinations) == 1
                else None
            ),
        )

    def _shortest_path(self, start: str, target: str) -> list[str]:
        queue: deque[list[str]] = deque([[start]])
        visited = {start}
        while queue:
            path = queue.popleft()
            node = path[-1]
            if node == target:
                return path
            for neighbor in self.graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append([*path, neighbor])
        raise ValueError(f"No route from {start} to {target}")
