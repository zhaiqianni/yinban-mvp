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
            destinations = result.destinations or (result.destination,)
            if len(destinations) > 1:
                stops = []
                chinese_ordinals = "一二三四五六七八九十"
                for index, destination in enumerate(destinations, start=1):
                    destination_config = self.hospital["destinations"][destination]
                    ordinal = (
                        chinese_ordinals[index - 1]
                        if index <= len(chinese_ordinals)
                        else str(index)
                    )
                    stops.append(
                        f"第{ordinal}站：{destination_config['name']}，"
                        f"位于{destination_config['location']}。"
                    )
                return "按您说的顺序，" + " ".join(stops)
            return self.hospital["destinations"][result.destination]["answer"]
        if result.intent == "process" and result.destination:
            return self.hospital["processes"][result.destination]["answer"]
        return unknown_reply(text)
