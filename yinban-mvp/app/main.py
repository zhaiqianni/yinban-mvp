from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api import dialogue, navigation, robot
from app.config import Settings, WEB_DIR
from app.runtime import build_runtime
from app.services.robot_link import RobotController


def create_app(
    settings: Settings | None = None,
    robot_controller: RobotController | None = None,
) -> FastAPI:
    runtime = build_runtime(settings, robot_controller)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        runtime.robot.connect()
        application.state.runtime = runtime
        yield
        runtime.robot.close()

    application = FastAPI(
        title="银伴医院智能陪诊导引机器人",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.include_router(dialogue.router)
    application.include_router(navigation.router)
    application.include_router(robot.router)
    application.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @application.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @application.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return application


app = create_app()


if __name__ == "__main__":
    settings = Settings.from_env()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)

