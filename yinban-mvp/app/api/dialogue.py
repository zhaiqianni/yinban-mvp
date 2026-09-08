from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import DialogueRequest, DialogueResponse, RoutePointResponse


router = APIRouter(prefix="/api", tags=["dialogue"])


@router.post("/dialogue", response_model=DialogueResponse)
def dialogue(payload: DialogueRequest, request: Request) -> DialogueResponse:
    runtime = request.app.state.runtime
    result = runtime.intent_router.match(payload.text)
    answer = runtime.dialogue_engine.reply(payload.text, result)

    if result.intent == "stop":
        runtime.robot.stop()
    elif result.intent == "help":
        runtime.robot.stop()

    route_labels: list[str] = []
    route_points: list[RoutePointResponse] = []
    robot_route_id = None
    physical_available = False
    destinations = list(result.destinations) if result.intent == "navigate" else []
    if result.intent == "navigate" and not destinations and result.destination:
        destinations = [result.destination]
    destination_names = [
        runtime.intent_router.hospital["destinations"][destination]["name"]
        for destination in destinations
        if destination in runtime.intent_router.hospital["destinations"]
    ]
    if result.intent == "navigate" and result.destination:
        route = runtime.route_planner.plan_sequence(destinations)
        route_labels = route.labels
        route_points = [
            RoutePointResponse(
                node_id=point.node_id,
                label=point.label,
                x=point.x,
                y=point.y,
            )
            for point in route.points
        ]
        robot_route_id = route.robot_route_id
        physical_available = route.physical_available

    guide_route_id = robot_route_id
    if route_labels and runtime.robot.mode == "simulation" and not guide_route_id:
        guide_route_id = "SIMULATION"
    guide_available = bool(guide_route_id)

    return DialogueResponse(
        intent=result.intent,
        destination=result.destination,
        destinations=destinations,
        destination_names=destination_names,
        answer=answer,
        route=route_labels,
        route_points=route_points,
        robot_route_id=robot_route_id,
        physical_available=physical_available,
        guide_route_id=guide_route_id,
        guide_available=guide_available,
    )
