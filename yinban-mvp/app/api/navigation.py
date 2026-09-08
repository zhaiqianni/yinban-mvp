from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import RoutePointResponse, RouteResponse


router = APIRouter(prefix="/api/navigation", tags=["navigation"])


@router.get("/{destination}", response_model=RouteResponse)
def navigation(destination: str, request: Request) -> RouteResponse:
    try:
        route = request.app.state.runtime.route_planner.plan(destination)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知目的地") from exc
    return RouteResponse(
        destination=route.destination,
        destination_name=route.destination_name,
        node_ids=route.node_ids,
        labels=route.labels,
        points=[
            RoutePointResponse(
                node_id=point.node_id,
                label=point.label,
                x=point.x,
                y=point.y,
            )
            for point in route.points
        ],
        robot_route_id=route.robot_route_id,
        physical_available=route.physical_available,
    )
