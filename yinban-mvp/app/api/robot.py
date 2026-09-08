from __future__ import annotations

from fastapi import APIRouter, Request

from app.models.schemas import (
    CommandResponse,
    RobotStartRequest,
    RobotStatusResponse,
)


router = APIRouter(prefix="/api/robot", tags=["robot"])


def _command_response(robot, result: tuple[bool, str]) -> CommandResponse:
    accepted, message = result
    return CommandResponse(accepted=accepted, mode=robot.mode, message=message)


@router.post("/start", response_model=CommandResponse)
def start(payload: RobotStartRequest, request: Request) -> CommandResponse:
    robot = request.app.state.runtime.robot
    return _command_response(
        robot,
        robot.start(payload.route_id.upper(), payload.step_count),
    )


@router.post("/stop", response_model=CommandResponse)
def stop(request: Request) -> CommandResponse:
    robot = request.app.state.runtime.robot
    return _command_response(robot, robot.stop())


@router.post("/resume", response_model=CommandResponse)
def resume(request: Request) -> CommandResponse:
    robot = request.app.state.runtime.robot
    return _command_response(robot, robot.resume())


@router.post("/reset", response_model=CommandResponse)
def reset(request: Request) -> CommandResponse:
    robot = request.app.state.runtime.robot
    return _command_response(robot, robot.reset())


@router.get("/status", response_model=RobotStatusResponse)
def status(request: Request) -> RobotStatusResponse:
    snapshot = request.app.state.runtime.robot.status()
    return RobotStatusResponse(
        mode=snapshot.mode,
        connected=snapshot.connected,
        state=snapshot.state.value,
        route_id=snapshot.route_id,
        distance_cm=snapshot.distance_cm,
        error=snapshot.error,
        progress=snapshot.progress,
        updated_at=snapshot.updated_at,
    )
