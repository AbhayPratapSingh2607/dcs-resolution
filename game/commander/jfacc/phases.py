"""Campaign phase management, driven by the planning profile.

Each profile defines its phases. Each phase has a family (posture,
offensive, defensive) and ordered transitions with MOE conditions (see
``moes.py``). The engine runs once per turn:

1. Interrupts first. An interrupt enters its phase from any phase of the
   listed families as soon as its conditions hold (for example, any
   offensive phase gives way to the defense when the front collapses). It
   remembers the phase it left. While in the interrupt's phase, the same
   conditions holding again keep the side there.
2. Then the current phase's transitions, in order, once the phase has run its
   minimum number of turns. ``$resume`` returns to the phase an interrupt
   left.

Modifiers are overlays on whatever phase is active, such as force
preservation when the air war is being lost. They are evaluated after the
phase is decided.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .assessment import CampaignAssessment
from .campaignstate import SideCampaign
from .moes import Evaluator, MoeContext
from .profile import RESUME, Family, Modifier, Phase, PlanningProfile


@dataclass(frozen=True)
class PhaseDecision:
    phase: Phase
    changed: bool
    reason: str
    #: Modifiers active this period.
    modifiers: tuple[Modifier, ...] = field(default=())


def _capture_baseline(side: SideCampaign, assessment: CampaignAssessment) -> None:
    if not side.campaign_baseline:
        side.campaign_baseline = {
            "own_fighters": assessment.own_fighters,
            "enemy_fighters": assessment.enemy_fighters,
            "own_bases": float(assessment.own_bases),
        }
    if side.baseline:
        return
    side.baseline = {
        "enemy_fighters": assessment.enemy_fighters,
        "battle_area_sams": float(assessment.battle_area_sams),
        "enemy_ground_strength": assessment.enemy_ground_strength,
    }


class PhaseManager:
    def __init__(self, profile: PlanningProfile) -> None:
        self.profile = profile

    # ------------------------------------------------------------ helpers

    def _first_campaign_phase(self) -> Phase:
        """The first phase after posture, where a resumed campaign restarts."""
        for phase in self.profile.phase_order:
            if self.profile.family_of(phase) is not Family.POSTURE:
                return phase
        return self.profile.start_phase

    def _resolve(self, side: SideCampaign, target: str) -> Optional[Phase]:
        if target == RESUME:
            phase = self.profile.phase(side.resume_phase) if side.resume_phase else None
            if phase is None or self.profile.family_of(phase) is Family.POSTURE:
                phase = self._first_campaign_phase()
            return phase
        phase = self.profile.phase(target)
        if phase is None:
            raise ValueError(
                f"Planning profile {self.profile.name}: unknown phase {target!r}"
            )
        return phase

    def _change(
        self,
        side: SideCampaign,
        assessment: CampaignAssessment,
        phase: Phase,
        turn: int,
        reason: str,
    ) -> None:
        side.change_phase(phase, turn, reason)
        side.profile_name = self.profile.name
        _capture_baseline(side, assessment)

    def _min_turns(self, phase: Phase, override: Optional[int]) -> int:
        if override is not None:
            return int(override)
        spec = self.profile.phases[phase]
        if spec.min_turns is not None:
            return int(spec.min_turns)
        return self.profile.min_phase_turns

    # ------------------------------------------------------------- decide

    def decide(
        self, side: SideCampaign, assessment: CampaignAssessment, turn: int
    ) -> PhaseDecision:
        decision = self._decide_phase(side, assessment, turn)
        modifiers = self._modifiers(side, assessment, turn)
        return PhaseDecision(decision.phase, decision.changed, decision.reason, modifiers)

    def _decide_phase(
        self, side: SideCampaign, assessment: CampaignAssessment, turn: int
    ) -> PhaseDecision:
        profile = self.profile
        if not side.history:
            self._change(side, assessment, profile.start_phase, turn, "start")
        elif side.phase not in profile.phases:
            # The side switched planning profile (e.g. from the legacy planner
            # or another doctrine): start that profile's campaign.
            reason = f"planning profile changed to {profile.name}"
            side.resume_phase = ""
            self._change(side, assessment, profile.start_phase, turn, reason)
        _capture_baseline(side, assessment)
        side.profile_name = profile.name

        evaluator = Evaluator(MoeContext(side, assessment, turn), side.condition_counters)
        family = profile.family_of(side.phase)

        # Interrupts.
        for i, interrupt in enumerate(profile.interrupts):
            target = self._resolve(side, interrupt.to)
            assert target is not None
            met, reason = evaluator.check(interrupt.when, f"interrupt{i}")
            if side.phase is target:
                if met:
                    # Still under the conditions that brought us here: reset
                    # the counters for leaving.
                    side.condition_counters.clear()
                    return PhaseDecision(target, False, reason)
                continue
            if family in interrupt.from_families and met:
                left = side.phase
                self._change(side, assessment, target, turn, reason)
                if interrupt.remember_resume:
                    side.resume_phase = left.value
                return PhaseDecision(target, True, reason)

        # Transitions.
        spec = profile.phases[side.phase]
        held = turn - side.phase_since_turn
        for i, transition in enumerate(spec.transitions):
            if held < self._min_turns(side.phase, transition.min_turns):
                continue
            met, reason = evaluator.check(
                transition.when, f"{side.phase.value}:{i}"
            )
            if not met:
                continue
            target = self._resolve(side, transition.to)
            assert target is not None
            if target is side.phase:
                continue
            if transition.to == RESUME:
                reason = reason or "front stabilised"
                reason = f"{reason}; resuming the campaign"
                side.resume_phase = ""
            self._change(side, assessment, target, turn, reason)
            return PhaseDecision(target, True, reason)
        return PhaseDecision(side.phase, False, "conditions for changing phase not met")

    def _modifiers(
        self, side: SideCampaign, assessment: CampaignAssessment, turn: int
    ) -> tuple[Modifier, ...]:
        evaluator = Evaluator(MoeContext(side, assessment, turn), side.modifier_counters)
        active: list[Modifier] = []
        for modifier in self.profile.modifiers:
            met, _ = evaluator.check(modifier.when, f"modifier:{modifier.name}")
            if met:
                side.modifiers[modifier.name] = turn
            last = side.modifiers.get(modifier.name)
            if last is not None and turn - last < max(1, modifier.hold_turns):
                active.append(modifier)
            elif last is not None:
                del side.modifiers[modifier.name]
        return tuple(active)
