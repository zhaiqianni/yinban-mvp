from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class DialogueRequest(BaseModel):
    text: str = Field(min_length=1, max_length=200)


class RoutePointResponse(BaseModel):
    node_id: str
    label: str
    x: float
    y: float


class DialogueResponse(BaseModel):
    intent: str
    destination: str | None = None
    destinations: list[str] = Field(default_factory=list)
    destination_names: list[str] = Field(default_factory=list)
    answer: str
    route: list[str] = Field(default_factory=list)
    route_points: list[RoutePointResponse] = Field(default_factory=list)
    robot_route_id: str | None = None
    physical_available: bool = False
    guide_route_id: str | None = None
    guide_available: bool = False


class RouteResponse(BaseModel):
    destination: str
    destination_name: str
    node_ids: list[str]
    labels: list[str]
    points: list[RoutePointResponse]
    robot_route_id: str | None
    physical_available: bool


class RobotStartRequest(BaseModel):
    route_id: str = Field(alias="routeId", min_length=1, max_length=40)
    step_count: int = Field(default=2, alias="stepCount", ge=2, le=20)

    model_config = {"populate_by_name": True}


class CommandResponse(BaseModel):
    accepted: bool
    mode: str
    message: str


class RobotStatusResponse(BaseModel):
    mode: str
    connected: bool
    state: str
    route_id: str | None = None
    distance_cm: float | None = None
    error: str | None = None
    progress: float | None = Field(default=None, ge=0, le=1)
    updated_at: datetime
