from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IntentResult:
    intent: str
    destination: str | None = None
    destinations: tuple[str, ...] = ()
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

        destination_matches = self._find_destinations(normalized)
        if len(destination_matches) > 1:
            destinations = tuple(item[0] for item in destination_matches)
            return IntentResult(
                "navigate",
                destination=destinations[0],
                destinations=destinations,
                matched_keyword=destination_matches[0][1],
                confidence=0.95,
            )

        for process_id, process in self.hospital["processes"].items():
            for keyword in process["keywords"]:
                if self.normalize(keyword) in normalized:
                    return IntentResult(
                        "process",
                        destination=process_id,
                        matched_keyword=keyword,
                        confidence=0.9,
                    )

        if destination_matches:
            destination_id, alias = destination_matches[0]
            return IntentResult(
                "navigate",
                destination=destination_id,
                destinations=(destination_id,),
                matched_keyword=alias,
                confidence=0.95,
            )

        return IntentResult("unknown", confidence=0.0)

    def _find_destinations(self, normalized: str) -> list[tuple[str, str]]:
        """Return distinct destinations in the order they appear in the request."""
        matches: list[tuple[int, int, str, str]] = []
        for destination_id, destination in self.hospital["destinations"].items():
            for alias in destination["aliases"]:
                normalized_alias = self.normalize(alias)
                position = normalized.find(normalized_alias)
                if position >= 0:
                    matches.append(
                        (position, -len(normalized_alias), destination_id, alias)
                    )

        ordered: list[tuple[str, str]] = []
        seen: set[str] = set()
        for _, _, destination_id, alias in sorted(matches):
            if destination_id not in seen:
                seen.add(destination_id)
                ordered.append((destination_id, alias))
        return ordered
