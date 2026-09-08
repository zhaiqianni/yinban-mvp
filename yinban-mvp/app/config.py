from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


APP_DIR = Path(__file__).resolve().parent
WEB_DIR = APP_DIR / "web"
DATA_DIR = APP_DIR / "data"


@dataclass(frozen=True)
class Settings:
    mode: str = "simulation"
    robot_port: str = ""
    robot_baud: int = 115200
    host: str = "127.0.0.1"
    port: int = 8000

    @classmethod
    def from_env(cls) -> "Settings":
        mode = os.getenv("YINBAN_MODE", "simulation").strip().lower()
        if mode not in {"simulation", "hardware", "auto"}:
            mode = "simulation"
        return cls(
            mode=mode,
            robot_port=os.getenv("YINBAN_ROBOT_PORT", "").strip(),
            robot_baud=int(os.getenv("YINBAN_ROBOT_BAUD", "115200")),
            host=os.getenv("YINBAN_HOST", "127.0.0.1"),
            port=int(os.getenv("YINBAN_PORT", "8000")),
        )

