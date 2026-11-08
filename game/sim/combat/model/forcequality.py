"""Force quality: training, readiness, integration and doctrine of a side.

See resources/combat/force_quality.yaml for the data and the historical
rationale.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import cache
from typing import Any

from .profiles import _load_yaml


@dataclass(frozen=True)
class ForceQuality:
    tier: str
    aircrew: float = 1.0
    sam_crew: float = 1.0
    readiness: float = 0.9
    iads_integration: float = 1.0
    arm_fear: float = 0.4
    standoff_doctrine: bool = False
    gci_dependent: bool = False
    ew_support: float = 1.0


#: Used when force quality is disabled: everyone equal, as before.
NEUTRAL = ForceQuality("neutral")


@cache
def _data() -> dict[str, Any]:
    return _load_yaml("force_quality.yaml")


@cache
def tier(name: str) -> ForceQuality:
    tiers = _data().get("tiers", {})
    data = tiers.get(name)
    if data is None:
        logging.warning(f"Unknown force quality tier {name}")
        return NEUTRAL
    return ForceQuality(
        tier=name,
        aircrew=float(data.get("aircrew", 1.0)),
        sam_crew=float(data.get("sam_crew", 1.0)),
        readiness=float(data.get("readiness", 0.9)),
        iads_integration=float(data.get("iads_integration", 1.0)),
        arm_fear=float(data.get("arm_fear", 0.4)),
        standoff_doctrine=bool(data.get("standoff_doctrine", False)),
        gci_dependent=bool(data.get("gci_dependent", False)),
        ew_support=float(data.get("ew_support", 1.0)),
    )


@cache
def for_faction(faction_name: str) -> ForceQuality:
    data = _data()
    for entry in data.get("factions", []):
        if re.search(str(entry["pattern"]), faction_name, re.IGNORECASE):
            return tier(str(entry["tier"]))
    return tier(str(data.get("default_tier", "western")))
