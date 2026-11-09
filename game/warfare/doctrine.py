"""Combat doctrine: how a side fights (resources/combat/doctrines.yaml)."""

from __future__ import annotations

from dataclasses import dataclass, fields
from functools import cache
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from game.factions.faction import Faction


@dataclass(frozen=True)
class CombatDoctrine:
    name: str = "western"
    isr: float = 0.7
    prewar_mobile: float = 0.2
    strike_altitude: str = "medium"
    a2a_salvo: int = 1
    abort_threshold: float = 1.0
    cap_over_hvaa: bool = False
    sam_ambush: bool = False
    shoot_and_scoot: bool = False
    gps_jamming: bool = False
    decoy_discrimination: float = 0.3
    iads_rollback_first: bool = False
    decapitation: bool = False
    require_sead_escort: bool = False
    ground_support_priority: bool = False
    combined_arms: float = 0.8
    artillery_prep: float = 1.5
    maneuver: float = 1.0
    depth: float = 0.0
    morale_baseline: float = 0.75
    sat_optical_passes: int = 0
    sat_sar_passes: int = 0
    sat_quality: float = 0.0
    humint: float = 0.4
    sigint: float = 0.4
    counterintel: float = 0.5
    deception: float = 0.3
    roe_restrictive: bool = False
    collateral_sensitivity: float = 0.5
    #: Air campaign planning profile (resources/doctrine/planning/<name>.yaml).
    #: Empty means the legacy HTN planner.
    planning_profile: str = ""

    @property
    def low_level_strikes(self) -> bool:
        return self.strike_altitude == "low"


@cache
def _data() -> dict[str, Any]:
    from game.sim.combat.model.profiles import _load_yaml

    return _load_yaml("doctrines.yaml")


@cache
def doctrine_named(name: str) -> CombatDoctrine:
    data = _data().get("doctrines", {}).get(name)
    if data is None:
        return CombatDoctrine(name=name)
    known = {f.name: f.type for f in fields(CombatDoctrine)}
    values: dict[str, Any] = {"name": name}
    for key, value in data.items():
        if key in known:
            values[key] = value
    return CombatDoctrine(**values)


@cache
def for_faction_name(
    faction_name: str, flight_plan_doctrine: str = ""
) -> CombatDoctrine:
    if flight_plan_doctrine.lower() in ("ww2", "wwii"):
        return doctrine_named("ww2")
    from game.sim.combat.model.forcequality import for_faction

    tier = for_faction(faction_name).tier
    name = _data().get("tiers", {}).get(tier, "western")
    return doctrine_named(str(name))


def for_faction_obj(faction: Faction) -> CombatDoctrine:
    flight_doctrine = getattr(getattr(faction, "doctrine", None), "name", "") or ""
    return for_faction_name(faction.name, str(flight_doctrine))
