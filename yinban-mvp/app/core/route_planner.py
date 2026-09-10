from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RoutePoint:
    node_id: str
    label: str
    floor: int
    kind: str
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
    physical_handoff_node_id: str | None

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
        points = [
            RoutePoint(
                node_id=node_id,
                label=self.routes["nodes"][node_id]["label"],
                floor=self.routes["nodes"][node_id]["floor"],
                kind=self.routes["nodes"][node_id].get("kind", "place"),
                x=self.routes["nodes"][node_id]["x"],
                y=self.routes["nodes"][node_id]["y"],
            )
            for node_id in node_ids
        ]
        labels = self._build_step_labels(points)
        robot_route_id = (
            destination_config.get("robotRouteId")
            if len(destinations) == 1
            else None
        )
        return PlannedRoute(
            destination=destination,
            destination_name=self.routes["nodes"][current]["label"],
            node_ids=node_ids,
            labels=labels,
            points=points,
            robot_route_id=robot_route_id,
            physical_handoff_node_id=(
                destination_config.get("physicalHandoffNodeId")
                if robot_route_id
                else None
            ),
        )

    def _build_step_labels(self, points: list[RoutePoint]) -> list[str]:
        labels: list[str] = []
        for index, point in enumerate(points):
            labels.append(self._point_step_label(points, index))
            if index == len(points) - 1:
                continue
            next_point = points[index + 1]
            if point.floor != next_point.floor:
                verb = "前往" if next_point.floor > point.floor else "返回"
                labels.append(
                    f"乘坐3号电梯{verb}{self._floor_name(next_point.floor)}"
                )
        return labels

    def _point_step_label(self, points: list[RoutePoint], index: int) -> str:
        point = points[index]
        floor_name = self._floor_name(point.floor)
        if point.kind != "elevator":
            return f"{point.label}（{floor_name}）"

        previous_floor = points[index - 1].floor if index > 0 else point.floor
        next_floor = (
            points[index + 1].floor
            if index < len(points) - 1
            else point.floor
        )
        if next_floor != point.floor:
            role = "入口"
        elif previous_floor != point.floor:
            role = "出口"
        else:
            role = "口"
        return f"{point.label}{role}（{floor_name}）"

    @staticmethod
    def _floor_name(floor: int) -> str:
        names = {1: "一楼", 2: "二楼", 3: "三楼"}
        return names.get(floor, f"{floor}楼")

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
