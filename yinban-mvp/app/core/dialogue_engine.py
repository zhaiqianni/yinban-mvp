from __future__ import annotations

from typing import Any

from app.core.intent_router import IntentResult
from app.core.safety_rules import unknown_reply


class DialogueEngine:
    def __init__(self, hospital: dict[str, Any]) -> None:
        self.hospital = hospital

    def reply(self, text: str, result: IntentResult) -> str:
        if result.intent == "stop":
            return "好的，已停止导引。"
        if result.intent == "help":
            return (
                "已触发本地求助提醒。请留在安全位置，并立即联系现场工作人员；"
                "如情况紧急，请拨打急救电话。"
            )
        if result.intent == "navigate" and result.destination:
            return self.hospital["destinations"][result.destination]["answer"]
        if result.intent == "process" and result.destination:
            return self.hospital["processes"][result.destination]["answer"]
        return unknown_reply(text)

