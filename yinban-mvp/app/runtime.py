from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.core.data_loader import load_json
from app.core.dialogue_engine import DialogueEngine
from app.core.intent_router import IntentRouter
from app.core.route_planner import RoutePlanner
from app.services.robot_link import RobotController, build_robot_controller


@dataclass
class Runtime:
    settings: Settings
    intent_router: IntentRouter
    dialogue_engine: DialogueEngine
    route_planner: RoutePlanner
    robot: RobotController


def build_runtime(
    settings: Settings | None = None,
    robot: RobotController | None = None,
) -> Runtime:
    active_settings = settings or Settings.from_env()
    hospital = load_json("hospital.json")
    intents = load_json("intents.json")
    routes = load_json("routes.json")
    return Runtime(
        settings=active_settings,
        intent_router=IntentRouter(hospital, intents),
        dialogue_engine=DialogueEngine(hospital),
        route_planner=RoutePlanner(routes, hospital["startNode"]),
        robot=robot or build_robot_controller(active_settings),
    )

