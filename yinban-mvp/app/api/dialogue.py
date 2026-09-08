from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import DialogueRequest, DialogueResponse


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
    robot_route_id = None
    physical_available = False
    destinations = list(result.destinations)
    if not destinations and result.destination:
        destinations = [result.destination]
    destination_names = [
        runtime.intent_router.hospital["destinations"][destination]["name"]
        for destination in destinations
        if destination in runtime.intent_router.hospital["destinations"]
    ]
    if result.intent == "navigate" and result.destination:
        route = runtime.route_planner.plan_sequence(destinations)
        route_labels = route.labels
        robot_route_id = route.robot_route_id
        physical_available = route.physical_available

    return DialogueResponse(
        intent=result.intent,
        destination=result.destination,
        destinations=destinations,
        destination_names=destination_names,
        answer=answer,
        route=route_labels,
        robot_route_id=robot_route_id,
        physical_available=physical_available,
    )
