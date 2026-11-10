"""Persistent state of each side's air campaign (phase, target list, BDA)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from .profile import Category, Phase, TargetSystem


@dataclass
class TargetRecord:
    """What a side's planners remember about one target across turns."""

    key: str
    name: str
    first_nominated_turn: int
    strikes: int = 0
    last_struck_turn: int = -1
    #: Effect assessed from BDA after the last strike (0..1).
    assessed_effect: float = 0.0
    #: How reliable the assessment is (0..1).
    bda_confidence: float = 0.0

    def __setstate__(self, state: dict[str, Any]) -> None:
        defaults = TargetRecord("", "", 0).__dict__
        self.__dict__.update({**defaults, **state})


@dataclass
class NominationSnapshot:
    """One JIPTL line, kept for the UI."""

    rank: int
    key: str
    name: str
    system: TargetSystem
    target_class: str
    priority: float
    confidence: float
    desired_effect: float
    assessed_effect: float
    bda_confidence: float
    status: str
    planned: bool = False


@dataclass
class PhaseChange:
    turn: int
    phase: Phase
    reason: str

    @property
    def title(self) -> str:
        return self.phase.title


@dataclass
class SideCampaign:
    phase: Phase = Phase.POSTURE
    phase_since_turn: int = 0
    history: list[PhaseChange] = field(default_factory=list)
    #: Commander's intent for the current period, for the UI.
    intent: str = ""
    targets: dict[str, TargetRecord] = field(default_factory=dict)
    jiptl: list[NominationSnapshot] = field(default_factory=list)
    #: Sorties apportioned and actually planned this period, per category.
    apportioned: dict[Category, int] = field(default_factory=dict)
    planned: dict[Category, int] = field(default_factory=dict)
    total_sorties: int = 0
    #: Measures of effectiveness from the last assessment, for the UI.
    moes: dict[str, float] = field(default_factory=dict)
    #: Baselines captured when the current phase started.
    baseline: dict[str, float] = field(default_factory=dict)
    #: Turns without an enemy offensive while in DEFENSE.
    quiet_turns: int = 0
    #: Packages that were planned but scrubbed, with the reason, for the UI.
    scrubbed: list[tuple[str, str]] = field(default_factory=list)
    #: Fighters held on ground alert this period, for the UI.
    qra: list[str] = field(default_factory=list)
    #: Planning profile the phase belongs to.
    profile_name: str = ""
    #: Phase an interrupt left, resumed when the interrupt is over.
    resume_phase: str = ""
    #: Consecutive turns each sustained condition has held, by condition key.
    #: Reset on every phase change.
    condition_counters: dict[str, int] = field(default_factory=dict)
    #: Baselines captured once, when the side first planned (campaign-long
    #: MOEs such as own losses and bases lost).
    campaign_baseline: dict[str, float] = field(default_factory=dict)
    #: Modifiers active this period, with the turn they last triggered.
    modifiers: dict[str, int] = field(default_factory=dict)
    #: Sustain counters of modifier conditions (kept across phase changes).
    modifier_counters: dict[str, int] = field(default_factory=dict)
    #: Enemy aircraft the side's own sensors saw in the last period.
    enemy_sorties_seen: int = 0
    #: Massed raids planned this period, for the UI.
    raids: list[str] = field(default_factory=list)
    #: Bearings enemy air activity was observed on, per own control point id
    #: (game.commander.jfacc.observations: 36 bins, decayed per turn).
    observed_axes: dict[str, list[float]] = field(default_factory=dict)
    #: How often each own ground object was hit (decayed), by TGO id.
    attacked: dict[str, float] = field(default_factory=dict)
    #: Turn the observation history was last decayed.
    observed_turn: int = -1
    #: Emission control order per own radar SAM site, by TGO id
    #: (game.commander.jfacc.iads: active, ambush or dark).
    iads_orders: dict[str, str] = field(default_factory=dict)
    #: Own SAM sites that fired, with the turn they last fired, by TGO id.
    fired_sites: dict[str, int] = field(default_factory=dict)
    #: Turn the IADS was last repositioned, and the moves made, for the UI.
    moves_turn: int = -1
    iads_moves: list[str] = field(default_factory=list)
    #: Loss experience (game.commander.jfacc.experience): decayed (expected,
    #: actual) aircraft lost per package kind, and the expected losses of
    #: the plan about to fly.
    experience: dict[str, tuple[float, float]] = field(default_factory=dict)
    expected_losses: dict[str, float] = field(default_factory=dict)
    #: The main push planned this period (full turns): the turn's main
    #: effort in one block as long as the mission. None without one.
    push_start: Optional[datetime] = None
    push_end: Optional[datetime] = None

    @property
    def push(self) -> Optional[tuple[datetime, datetime]]:
        if self.push_start is None or self.push_end is None:
            return None
        return self.push_start, self.push_end

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update({**SideCampaign().__dict__, **state})
        # Saves from before phases were data kept the phase to resume after
        # DEFENSE as an index into the Western phase order.
        legacy_resume = self.baseline.pop("resume_phase", None)
        if legacy_resume is not None and not self.resume_phase:
            order = [
                "posture",
                "strategic",
                "sead_rollback",
                "battlefield_prep",
                "ground_offensive",
            ]
            index = min(max(int(legacy_resume), 0), len(order) - 1)
            self.resume_phase = order[index]

    def record(self, key: str, name: str, turn: int) -> TargetRecord:
        record = self.targets.get(key)
        if record is None:
            record = TargetRecord(key=key, name=name, first_nominated_turn=turn)
            self.targets[key] = record
        return record

    @property
    def phase_title(self) -> str:
        return self.phase.title

    def change_phase(self, phase: Phase, turn: int, reason: str) -> None:
        self.phase = phase
        self.phase_since_turn = turn
        self.history.append(PhaseChange(turn, phase, reason))
        self.baseline = {}
        self.quiet_turns = 0
        self.condition_counters = {}


@dataclass
class AirCampaignState:
    sides: dict[bool, SideCampaign] = field(default_factory=dict)
    #: Minutes after the period start at which the DCS mission starts.
    window_offset_min: int = 0
    #: Packages deferred past the DCS window, resolved after the mission.
    deferred_packages: dict[bool, list[Any]] = field(default_factory=dict)
    #: The ATO period planned this turn, when a side uses the JFACC planner.
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
    period_turn: int = -1
    #: A focused turn (settings.focused_turns): the DCS window is fixed at
    #: the end of the lead-in and covers the rest of the period.
    focused: bool = False

    def __setstate__(self, state: dict[str, Any]) -> None:
        self.__dict__.update({**AirCampaignState().__dict__, **state})

    def period_for(self, turn: int) -> Optional[tuple[datetime, datetime]]:
        if (
            self.period_turn != turn
            or self.period_start is None
            or self.period_end is None
        ):
            return None
        return self.period_start, self.period_end

    def note_period(
        self,
        turn: int,
        start: datetime,
        end: datetime,
        lead_in_min: Optional[int] = None,
    ) -> None:
        """Record the period planned this turn. ``lead_in_min`` makes it a
        focused turn whose DCS window starts after that lead-in."""
        if self.period_turn != turn or self.period_start is None:
            self.period_turn = turn
            self.period_start = start
            self.period_end = end
            self.focused = lead_in_min is not None
            self.window_offset_min = lead_in_min or 0
            self.deferred_packages = {}
            return
        self.period_start = min(self.period_start, start)
        self.period_end = max(self.period_end or end, end)

    def side(self, blue: bool) -> SideCampaign:
        side = self.sides.get(blue)
        if side is None:
            side = SideCampaign()
            self.sides[blue] = side
        return side

    def maybe_side(self, blue: bool) -> Optional[SideCampaign]:
        return self.sides.get(blue)
