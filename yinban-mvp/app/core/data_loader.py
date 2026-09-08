from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import DATA_DIR


def load_json(filename: str, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    path = data_dir / filename
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)

