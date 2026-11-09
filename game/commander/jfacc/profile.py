"""Air campaign planning profiles (resources/doctrine/planning/*.yaml).

A profile holds every doctrinal number the JFACC planner uses: phase
apportionment, transition conditions, risk limits, package scaling,
weaponeering, counter-air and ground support layout. Keeping them in data
lets the planner be tuned without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, Optional

import yaml

PROFILE_DIR = Path("resources/doctrine/planning")


class Phase(Enum):
    POSTURE = "posture"
    STRATEGIC = "strategic"
    SEAD_ROLLBACK = "sead_rollback"
    BATTLEFIELD_PREP = "battlefield_prep"
    GROUND_OFFENSIVE = "ground_offensive"
    DEFENSE = "defense"

    @property
    def title(self) -> str:
        return {
            Phase.POSTURE: "Phase 0: Posture",
            Phase.STRATEGIC: "Phase I: Strategic air campaign",
            Phase.SEAD_ROLLBACK: "Phase II: SEAD rollback",
            Phase.BATTLEFIELD_PREP: "Phase III: Battlefield preparation",
            Phase.GROUND_OFFENSIVE: "Phase IV: Ground offensive",
            Phase.DEFENSE: "Defense",
        }[self]


class Category(Enum):
    """Apportionment categories (JP 3-30 air apportionment)."""

    DCA = "dca"
    SUPPORT = "support"
    OCA = "oca"
    SEAD = "sead"
    STRIKE = "strike"
    INTERDICTION = "interdiction"
    CAS = "cas"

    @property
    def title(self) -> str:
        return {
            Category.DCA: "Defensive counter-air",
            Category.SUPPORT: "Support (AEW&C, tankers)",
            Category.OCA: "Offensive counter-air",
            Category.SEAD: "SEAD/DEAD",
            Category.STRIKE: "Strategic attack",
            Category.INTERDICTION: "Air interdiction",
            Category.CAS: "Close air support",
        }[self]


class TargetSystem(Enum):
    IADS = "iads"
    AIR = "air"
    C2 = "c2"
    POL = "pol"
    LOC = "loc"
    FIELDED = "fielded"
    NAVAL = "naval"


@dataclass(frozen=True)
class Share:
    share: float
    min: float
    max: float


@dataclass(frozen=True)
class PhaseSpec:
    phase: Phase
    description: str
    apportionment: dict[Category, Share]
    advance_when: dict[str, Any] = field(default_factory=dict)
    enter_when: dict[str, Any] = field(default_factory=dict)
    leave_when: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DesiredEffect:
    destroy: float
    restrike_below: float
    value: float


@dataclass(frozen=True)
class ThreatSupport:
    sweep: int
    escort: int
    sead: int
    jammer: int


@dataclass(frozen=True)
class PlanningProfile:
    name: str
    raw: dict[str, Any]
    phases: dict[Phase, PhaseSpec]
    phase_order: list[Phase]
    min_phase_turns: int
    overflow_order: list[Category]
    target_system_weights: dict[Phase, dict[TargetSystem, float]]
    desired_effects: dict[str, DesiredEffect]
    threat_support: dict[str, ThreatSupport]

    # ----------------------------------------------------------- shortcuts

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default: Any) -> Any:
        return self.section(section).get(key, default)

    @property
    def period_hours(self) -> float:
        return float(self.get("period", "hours", 6))

    @property
    def wave_fractions(self) -> list[float]:
        return [float(f) for f in self.get("period", "wave_fractions", [0.25, 0.75])]

    @property
    def mc_rate(self) -> float:
        return float(self.get("sorties", "mission_capable_rate", 0.8))

    def turnaround_hours(self, role: str) -> float:
        table = self.get("sorties", "turnaround_hours", {})
        return float(table.get(role, table.get("fighter", 2.0)))

    @property
    def max_sorties_per_airframe(self) -> int:
        return int(self.get("sorties", "max_sorties_per_airframe", 2))

    @property
    def attrition_limit(self) -> float:
        return float(self.get("risk", "attrition_limit", 0.02))

    @property
    def absolute_attrition_limit(self) -> float:
        return float(self.get("risk", "absolute_limit", 0.08))

    def priority_multiplier(self, kind: str) -> float:
        table = self.get("risk", "priority_multiplier", {})
        return float(table.get(kind, 1.0))

    def system_weight(self, phase: Phase, system: TargetSystem) -> float:
        return self.target_system_weights.get(phase, {}).get(system, 0.5)

    def effect_for(self, target_class: str) -> DesiredEffect:
        return self.desired_effects.get(
            target_class, DesiredEffect(destroy=0.5, restrike_below=0.4, value=0.4)
        )

    def dmpis_for(self, target_class: str) -> int:
        return int(self.section("weaponeering").get("dmpis", {}).get(target_class, 2))


def _share(data: Any) -> Share:
    if isinstance(data, (int, float)):
        return Share(float(data), 0.0, 1.0)
    return Share(
        float(data.get("share", 0.0)),
        float(data.get("min", 0.0)),
        float(data.get("max", 1.0)),
    )


def parse_profile(name: str, data: dict[str, Any]) -> PlanningProfile:
    phases_data = data.get("phases", {})
    phases: dict[Phase, PhaseSpec] = {}
    for phase in Phase:
        spec = phases_data.get(phase.value)
        if not isinstance(spec, dict):
            continue
        apportionment = {
            category: _share(spec.get("apportionment", {}).get(category.value, 0.0))
            for category in Category
        }
        phases[phase] = PhaseSpec(
            phase=phase,
            description=str(spec.get("description", phase.title)),
            apportionment=apportionment,
            advance_when=dict(spec.get("advance_when") or {}),
            enter_when=dict(spec.get("enter_when") or {}),
            leave_when=dict(spec.get("leave_when") or {}),
        )
    order = [
        Phase(p)
        for p in phases_data.get("order", [p.value for p in Phase])
        if Phase(p) in phases
    ]
    weights = {
        Phase(phase): {
            TargetSystem(system): float(weight) for system, weight in table.items()
        }
        for phase, table in (data.get("target_system_weights") or {}).items()
    }
    effects = {
        str(key): DesiredEffect(
            destroy=float(value.get("destroy", 0.5)),
            restrike_below=float(value.get("restrike_below", 0.4)),
            value=float(value.get("value", 0.5)),
        )
        for key, value in (data.get("desired_effects") or {}).items()
    }
    support = {
        str(level): ThreatSupport(
            sweep=int(value.get("sweep", 0)),
            escort=int(value.get("escort", 0)),
            sead=int(value.get("sead", 0)),
            jammer=int(value.get("jammer", 0)),
        )
        for level, value in (
            (data.get("packages") or {}).get("threat_levels") or {}
        ).items()
    }
    return PlanningProfile(
        name=name,
        raw=data,
        phases=phases,
        phase_order=order,
        min_phase_turns=int(phases_data.get("min_turns", 2)),
        overflow_order=[Category(c) for c in data.get("overflow_order", [])],
        target_system_weights=weights,
        desired_effects=effects,
        threat_support=support,
    )


@cache
def load_profile(name: str) -> Optional[PlanningProfile]:
    if not name:
        return None
    path = PROFILE_DIR / f"{name}.yaml"
    if not path.exists():
        logging.warning(f"Planning profile {name} not found at {path}")
        return None
    with path.open(encoding="utf-8") as data_file:
        data = yaml.safe_load(data_file) or {}
    return parse_profile(name, data)


def category_for_task(task: object) -> Optional[Category]:
    """The apportionment category a flight type's sorties count against."""
    from game.ato.flighttype import FlightType

    mapping = {
        FlightType.BARCAP: Category.DCA,
        FlightType.TARCAP: Category.DCA,
        FlightType.INTERCEPTION: Category.DCA,
        FlightType.AEWC: Category.SUPPORT,
        FlightType.REFUELING: Category.SUPPORT,
        FlightType.SWEEP: Category.OCA,
        FlightType.ESCORT: Category.OCA,
        FlightType.OCA_AIRCRAFT: Category.OCA,
        FlightType.OCA_RUNWAY: Category.OCA,
        FlightType.SEAD: Category.SEAD,
        FlightType.SEAD_ESCORT: Category.SEAD,
        FlightType.SEAD_SWEEP: Category.SEAD,
        FlightType.DEAD: Category.SEAD,
        FlightType.STRIKE: Category.STRIKE,
        FlightType.BAI: Category.INTERDICTION,
        FlightType.ARMED_RECON: Category.INTERDICTION,
        FlightType.ANTISHIP: Category.INTERDICTION,
        FlightType.CAS: Category.CAS,
    }
    return mapping.get(task)  # type: ignore[call-overload]

