"""Air campaign planning profiles (resources/doctrine/planning/*.yaml).

A profile holds every doctrinal number the JFACC planner uses: the campaign
phases with their apportionment, flags and transitions, risk limits, package
scaling, weaponeering, counter-air and ground support layout. Keeping them in
data lets each doctrine plan its own way, and lets the planner be tuned
without code changes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, ClassVar, Optional, Union

import yaml

PROFILE_DIR = Path("resources/doctrine/planning")


class Phase:
    """A campaign phase, identified by its id in the planning profile.

    Phases are data: each profile defines its own (Western Desert Storm
    phases, Soviet air operations, ...). Instances are interned per id, so
    phases compare with ``is`` and saves holding the old ``Phase`` enum
    unpickle to the same objects (an enum member pickles as ``Phase(value)``).
    """

    _registry: ClassVar[dict[str, "Phase"]] = {}

    POSTURE: ClassVar["Phase"]
    STRATEGIC: ClassVar["Phase"]
    SEAD_ROLLBACK: ClassVar["Phase"]
    BATTLEFIELD_PREP: ClassVar["Phase"]
    GROUND_OFFENSIVE: ClassVar["Phase"]
    DEFENSE: ClassVar["Phase"]

    value: str
    title: str

    def __new__(cls, value: Union[str, "Phase"], title: Optional[str] = None) -> "Phase":
        if isinstance(value, Phase):
            return value
        existing = cls._registry.get(value)
        if existing is not None:
            if title and existing.title == existing.value:
                existing.title = title
            return existing
        phase = super().__new__(cls)
        phase.value = str(value)
        phase.title = title or str(value)
        cls._registry[phase.value] = phase
        return phase

    def __reduce__(self) -> tuple[Any, ...]:
        return Phase, (self.value, self.title)

    def __copy__(self) -> "Phase":
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> "Phase":
        return self

    def __repr__(self) -> str:
        return f"Phase({self.value!r})"

    def __str__(self) -> str:
        return self.value


Phase.POSTURE = Phase("posture", "Phase 0: Posture")
Phase.STRATEGIC = Phase("strategic", "Phase I: Strategic air campaign")
Phase.SEAD_ROLLBACK = Phase("sead_rollback", "Phase II: SEAD rollback")
Phase.BATTLEFIELD_PREP = Phase("battlefield_prep", "Phase III: Battlefield preparation")
Phase.GROUND_OFFENSIVE = Phase("ground_offensive", "Phase IV: Ground offensive")
Phase.DEFENSE = Phase("defense", "Defense")


class Family(Enum):
    """What kind of campaign a phase belongs to. Interrupts and modifiers
    select phases by family (e.g. any offensive phase gives way to a
    defensive one when the front collapses)."""

    POSTURE = "posture"
    OFFENSIVE = "offensive"
    DEFENSIVE = "defensive"


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


# ================================================================ conditions


@dataclass(frozen=True)
class Condition:
    """One MOE test, e.g. ``{moe: air_superiority, ge: 1.5, sustain: 2}``."""

    moe: str
    op: str
    value: Any
    #: Turns in a row the condition must hold.
    sustain: int = 1


@dataclass(frozen=True)
class When:
    """Conditions combined with all (and) or any (or). Items may nest."""

    mode: str
    items: tuple[Union[Condition, "When"], ...]

    @property
    def empty(self) -> bool:
        return not self.items


#: A condition that never holds.
NEVER = When("any", ())

#: Transition target meaning "the phase an interrupt left".
RESUME = "$resume"


@dataclass(frozen=True)
class Transition:
    to: str
    when: When
    #: Overrides the phase's minimum duration for this transition.
    min_turns: Optional[int] = None


@dataclass(frozen=True)
class Interrupt:
    """Enters ``to`` from any phase of the listed families as soon as the
    conditions hold (e.g. a defensive phase when the front is collapsing).
    While in ``to``, the same conditions holding again keep it there."""

    to: str
    when: When
    from_families: tuple[Family, ...]
    remember_resume: bool = True


@dataclass(frozen=True)
class Modifier:
    """An overlay on whatever phase is active (e.g. force preservation when
    the air war is being lost). ``effects`` are read by the planner."""

    name: str
    when: When
    effects: dict[str, Any]
    #: Turns the modifier stays on after its conditions stop holding.
    hold_turns: int = 1
    description: str = ""


# ==================================================================== phases


@dataclass(frozen=True)
class PhaseSpec:
    phase: Phase
    description: str
    apportionment: dict[Category, Share]
    family: Family = Family.OFFENSIVE
    target_weights: dict[TargetSystem, float] = field(default_factory=dict)
    #: Planner behaviour in this phase. Known flags:
    #:   ground_stance: attack | hold | defend (front-line stances)
    #:   strategic_reach: deep targets keep their priority (no depth decay)
    #:   defense_priority: attacks on fielded forces and LOCs count as defense
    #:   risk_multiplier: on the acceptable attrition limits
    #:   rollback_allowance: DEAD on the outer SAM layer may use risk.rollback_allowance
    #:   air_assault: helicopter assaults may be planned
    #:   cas_attrition: desired share of the enemy at the front destroyed by CAS
    #:   wave_preference: {category: wave index} for strike timing
    #:   raid_style: massed | opportunistic | none
    flags: dict[str, Any] = field(default_factory=dict)
    transitions: tuple[Transition, ...] = ()
    #: Minimum turns in the phase before transitions are checked (None: the
    #: profile's default).
    min_turns: Optional[int] = None

    @property
    def title(self) -> str:
        return self.phase.title

    def flag(self, name: str, default: Any = None) -> Any:
        return self.flags.get(name, default)


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
    #: The campaign's sequence of phases (for display and resuming).
    phase_order: list[Phase]
    min_phase_turns: int
    overflow_order: list[Category]
    desired_effects: dict[str, DesiredEffect]
    threat_support: dict[str, ThreatSupport]
    start: Optional[Phase] = None
    interrupts: tuple[Interrupt, ...] = ()
    modifiers: tuple[Modifier, ...] = ()

    # ----------------------------------------------------------- shortcuts

    def section(self, name: str) -> dict[str, Any]:
        value = self.raw.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default: Any) -> Any:
        return self.section(section).get(key, default)

    @property
    def start_phase(self) -> Phase:
        if self.start is not None:
            return self.start
        if self.phase_order:
            return self.phase_order[0]
        return next(iter(self.phases))

    def phase(self, phase_id: Union[str, Phase]) -> Optional[Phase]:
        """The profile's phase with this id, or None if it has no such phase."""
        key = phase_id.value if isinstance(phase_id, Phase) else str(phase_id)
        for phase in self.phases:
            if phase.value == key:
                return phase
        return None

    def family_of(self, phase: Phase) -> Family:
        spec = self.phases.get(phase)
        return spec.family if spec is not None else Family.OFFENSIVE

    @property
    def target_system_weights(self) -> dict[Phase, dict[TargetSystem, float]]:
        return {phase: spec.target_weights for phase, spec in self.phases.items()}

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
        spec = self.phases.get(phase)
        if spec is None:
            return 0.5
        return spec.target_weights.get(system, 0.5)

    def effect_for(self, target_class: str) -> DesiredEffect:
        return self.desired_effects.get(
            target_class, DesiredEffect(destroy=0.5, restrike_below=0.4, value=0.4)
        )

    def dmpis_for(self, target_class: str) -> int:
        return int(self.section("weaponeering").get("dmpis", {}).get(target_class, 2))


# =================================================================== parsing

_OPS = ("ge", "gt", "le", "lt", "eq", "ne")

_ParsedPhases = tuple[
    dict[Phase, PhaseSpec], list[Phase], Optional[Phase], tuple[Interrupt, ...], int
]


def _share(data: Any) -> Share:
    if isinstance(data, (int, float)):
        return Share(float(data), 0.0, 1.0)
    return Share(
        float(data.get("share", 0.0)),
        float(data.get("min", 0.0)),
        float(data.get("max", 1.0)),
    )


def parse_when(data: Any) -> When:
    """``{all: [...]}``, ``{any: [...]}``, a list (all of them) or a single
    condition such as ``{moe: air_superiority, ge: 1.5}``."""
    if data is None:
        return NEVER
    if isinstance(data, list):
        return When("all", tuple(_parse_item(d) for d in data))
    if isinstance(data, dict):
        for mode in ("all", "any"):
            if mode in data:
                return When(mode, tuple(_parse_item(d) for d in data[mode] or []))
        return When("all", (_parse_item(data),))
    raise ValueError(f"Can't parse condition {data!r}")


def _parse_item(data: Any) -> Union[Condition, When]:
    if isinstance(data, dict) and ("all" in data or "any" in data):
        return parse_when(data)
    if not isinstance(data, dict) or "moe" not in data:
        raise ValueError(f"Condition needs a moe: {data!r}")
    ops = [op for op in _OPS if op in data]
    if len(ops) != 1:
        raise ValueError(f"Condition needs exactly one of {_OPS}: {data!r}")
    return Condition(
        moe=str(data["moe"]),
        op=ops[0],
        value=data[ops[0]],
        sustain=int(data.get("sustain", 1)),
    )


def _weights(table: Any) -> dict[TargetSystem, float]:
    return {TargetSystem(system): float(w) for system, w in (table or {}).items()}


def _apportionment(spec: dict[str, Any]) -> dict[Category, Share]:
    table = spec.get("apportionment") or {}
    return {category: _share(table.get(category.value, 0.0)) for category in Category}


def _parse_phases(data: dict[str, Any]) -> _ParsedPhases:
    phases_data = data.get("phases", {}) or {}
    if "list" not in phases_data:
        return _translate_legacy_phases(data)
    phases: dict[Phase, PhaseSpec] = {}
    for phase_id, spec in (phases_data.get("list") or {}).items():
        phase = Phase(str(phase_id), spec.get("title"))
        phases[phase] = PhaseSpec(
            phase=phase,
            description=str(spec.get("description", phase.title)),
            apportionment=_apportionment(spec),
            family=Family(spec.get("family", "offensive")),
            target_weights=_weights(spec.get("target_weights")),
            flags=dict(spec.get("flags") or {}),
            transitions=tuple(
                Transition(
                    to=str(t["to"]),
                    when=parse_when(t.get("when")),
                    min_turns=t.get("min_turns"),
                )
                for t in spec.get("transitions") or []
            ),
            min_turns=spec.get("min_turns"),
        )
    order_ids = phases_data.get("order") or [
        p.value for p, s in phases.items() if s.family is not Family.DEFENSIVE
    ]
    order = [Phase(p) for p in order_ids if Phase(p) in phases]
    start = Phase(phases_data["start"]) if phases_data.get("start") else None
    interrupts = tuple(
        Interrupt(
            to=str(i["to"]),
            when=parse_when(i.get("when")),
            from_families=tuple(
                Family(f) for f in i.get("from_families", ["posture", "offensive"])
            ),
            remember_resume=bool(i.get("remember_resume", True)),
        )
        for i in phases_data.get("interrupts") or []
    )
    return phases, order, start, interrupts, int(phases_data.get("min_turns", 2))


#: Old ``advance_when`` keys -> (MOE, operator).
_LEGACY_ADVANCE = {
    "war_started": ("war_started", "eq"),
    "c2_degraded": ("c2_degraded", "ge"),
    "air_superiority": ("air_superiority", "ge"),
    "enemy_air_attrition": ("enemy_air_attrition", "ge"),
    "iads_effectiveness_below": ("iads_remaining", "le"),
    "enemy_ground_attrition": ("enemy_ground_attrition", "ge"),
    "force_ratio": ("main_effort_force_ratio", "ge"),
}

_LEGACY_IDS = [
    "posture",
    "strategic",
    "sead_rollback",
    "battlefield_prep",
    "ground_offensive",
    "defense",
]


def _translate_legacy_phases(data: dict[str, Any]) -> _ParsedPhases:
    """Profiles written before phases were data: the fixed Desert Storm phase
    ids with ``advance_when`` / ``enter_when`` / ``leave_when``, and
    phase-keyed tables elsewhere in the file."""
    phases_data = data.get("phases", {}) or {}
    order_ids = [
        p
        for p in phases_data.get("order", _LEGACY_IDS)
        if isinstance(phases_data.get(p), dict)
    ]
    risk = data.get("risk") or {}
    phase_multiplier = risk.get("phase_multiplier") or {}
    rollback_phases = (risk.get("rollback_allowance") or {}).get("phases", [])
    gs = data.get("ground_support") or {}
    attrition = gs.get("cas_attrition_per_period", {})
    assault_phases = (gs.get("air_assault") or {}).get("phases", [])
    weights = data.get("target_system_weights") or {}

    phases: dict[Phase, PhaseSpec] = {}
    interrupts: list[Interrupt] = []
    for phase_id in _LEGACY_IDS:
        spec = phases_data.get(phase_id)
        if not isinstance(spec, dict):
            continue
        phase = Phase(phase_id)
        if phase_id == "posture":
            family = Family.POSTURE
        elif phase_id == "defense":
            family = Family.DEFENSIVE
        else:
            family = Family.OFFENSIVE
        flags: dict[str, Any] = {
            "ground_stance": (
                "attack"
                if phase_id in ("battlefield_prep", "ground_offensive")
                else "hold"
            ),
            "strategic_reach": phase_id in ("strategic", "posture"),
            "defense_priority": phase_id == "defense",
            "risk_multiplier": float(phase_multiplier.get(phase_id, 1.0)),
            "rollback_allowance": phase_id in rollback_phases,
            "air_assault": phase_id in assault_phases,
        }
        if isinstance(attrition, dict):
            flags["cas_attrition"] = float(
                attrition.get(phase_id, attrition.get("default", 0.35))
            )
        else:
            flags["cas_attrition"] = float(attrition)
        transitions: list[Transition] = []
        advance = spec.get("advance_when") or {}
        if advance and phase_id in order_ids:
            index = order_ids.index(phase_id)
            if index + 1 < len(order_ids):
                conditions: list[Union[Condition, When]] = []
                for key, value in advance.items():
                    moe, op = _LEGACY_ADVANCE.get(key, (f"unknown:{key}", "eq"))
                    conditions.append(Condition(moe, op, value))
                transitions.append(
                    Transition(order_ids[index + 1], When("all", tuple(conditions)))
                )
        if phase_id == "defense":
            enter = spec.get("enter_when") or {}
            triggers: list[Union[Condition, When]] = []
            if "force_ratio_below" in enter:
                triggers.append(
                    Condition("min_force_ratio", "lt", enter["force_ratio_below"])
                )
            if enter.get("enemy_offensive_warning"):
                triggers.append(Condition("offensive_warning", "eq", True))
            if enter.get("base_threatened"):
                triggers.append(Condition("base_threatened", "eq", True))
            interrupts.append(
                Interrupt(
                    to="defense",
                    when=When("any", tuple(triggers)),
                    from_families=(Family.POSTURE, Family.OFFENSIVE),
                )
            )
            leave = spec.get("leave_when") or {}
            transitions.append(
                Transition(
                    RESUME,
                    When(
                        "all",
                        (
                            Condition(
                                "min_force_ratio",
                                "ge",
                                leave.get("force_ratio_above", 1.0),
                                sustain=int(leave.get("quiet_turns", 1)),
                            ),
                        ),
                    ),
                    min_turns=0,
                )
            )
        phases[phase] = PhaseSpec(
            phase=phase,
            description=str(spec.get("description", phase.title)),
            apportionment=_apportionment(spec),
            family=family,
            target_weights=_weights(weights.get(phase_id)),
            flags=flags,
            transitions=tuple(transitions),
            min_turns=0 if family is Family.POSTURE else None,
        )
    order = [Phase(p) for p in order_ids if p != "defense"]
    return phases, order, None, tuple(interrupts), int(phases_data.get("min_turns", 2))


def parse_profile(name: str, data: dict[str, Any]) -> PlanningProfile:
    phases, order, start, interrupts, min_turns = _parse_phases(data)
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
    modifiers = tuple(
        Modifier(
            name=str(mod_name),
            when=parse_when(mod.get("when")),
            effects=dict(mod.get("effects") or {}),
            hold_turns=int(mod.get("hold_turns", 1)),
            description=str(mod.get("description", "")),
        )
        for mod_name, mod in (data.get("modifiers") or {}).items()
    )
    return PlanningProfile(
        name=name,
        raw=data,
        phases=phases,
        phase_order=order,
        min_phase_turns=min_turns,
        overflow_order=[Category(c) for c in data.get("overflow_order", [])],
        desired_effects=effects,
        threat_support=support,
        start=start,
        interrupts=interrupts,
        modifiers=modifiers,
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
