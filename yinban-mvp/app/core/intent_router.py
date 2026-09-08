from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntentResult:
    intent: str
    destination: str | None = None
    matched_keyword: str | None = None
    confidence: float = 0.0


class IntentRouter:
    def __init__(self, hospital: dict[str, Any], intents: dict[str, Any]) -> None:
        self.hospital = hospital
        self.intents = intents

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"[\s，。！？、,.!?]+", "", text).lower()

    def match(self, text: str) -> IntentResult:
        normalized = self.normalize(text)
        if not normalized:
            return IntentResult("unknown")

        for keyword in self.intents["stopKeywords"]:
            if self.normalize(keyword) in normalized:
                return IntentResult("stop", matched_keyword=keyword, confidence=1.0)

        for keyword in self.intents["helpKeywords"]:
            if self.normalize(keyword) in normalized:
                return IntentResult("help", matched_keyword=keyword, confidence=1.0)

        for process_id, process in self.hospital["processes"].items():
            for keyword in process["keywords"]:
                if self.normalize(keyword) in normalized:
                    return IntentResult(
                        "process",
                        destination=process_id,
                        matched_keyword=keyword,
                        confidence=0.9,
                    )

        for destination_id, destination in self.hospital["destinations"].items():
            aliases = sorted(destination["aliases"], key=len, reverse=True)
            for alias in aliases:
                if self.normalize(alias) in normalized:
                    return IntentResult(
                        "navigate",
                        destination=destination_id,
                        matched_keyword=alias,
                        confidence=0.95,
                    )

        return IntentResult("unknown", confidence=0.0)
