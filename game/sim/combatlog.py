from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class CombatDomain(Enum):
    AIR = "Air-to-air"
    AIR_DEFENSE = "Air defense"
    STRIKE = "Strike"
    GROUND = "Ground"


@dataclass(frozen=True)
class CombatLogEntry:
    time: datetime
    domain: CombatDomain
    #: "blue", "red" or "" for neutral narration.
    side: str
    text: str

    def __str__(self) -> str:
        side = f"[{self.side.upper()}] " if self.side else ""
        return f"{self.time:%H:%M:%S} {self.domain.value}: {side}{self.text}"


@dataclass
class CombatLog:
    entries: list[CombatLogEntry] = field(default_factory=list)

    def add(self, time: datetime, domain: CombatDomain, side: str, text: str) -> None:
        self.entries.append(CombatLogEntry(time, domain, side, text))

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)
