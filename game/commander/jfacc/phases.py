"""Campaign phase management (Desert Storm style phasing with a DEFENSE override).

Phases advance when the measured conditions of the current phase's exit
criteria are met and the phase has run for its minimum duration. The DEFENSE
phase overrides any offensive phase while the enemy has the initiative, and
the campaign resumes the phase it left once the front has stabilised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .assessment import CampaignAssessment
from .campaignstate import SideCampaign
from .profile import Phase, PlanningProfile


@dataclass(frozen=True)
class PhaseDecision:
    phase: Phase
    changed: bool
    reason: str


def _capture_baseline(side: SideCampaign, assessment: CampaignAssessment) -> None:
    if side.baseline:
        return
    side.baseline = {
        "enemy_fighters": assessment.enemy_fighters,
        "battle_area_sams": float(assessment.battle_area_sams),
        "enemy_ground_strength": assessment.enemy_ground_strength,
    }


def _ratio_drop(side: SideCampaign, key: str, now: float) -> float:
    """Share of the phase-start value that has been destroyed."""
    start = side.baseline.get(key, 0.0)
    if start <= 0:
        return 1.0
    return max(0.0, 1.0 - now / start)


def _advance_met(
    criteria: dict[str, object],
    side: SideCampaign,
    assessment: CampaignAssessment,
) -> tuple[bool, str]:
    if not criteria:
        return False, ""
    reasons: list[str] = []
    for key, value in criteria.items():
        threshold = value if isinstance(value, bool) else float(value)  # type: ignore[arg-type]
        if key == "war_started":
            ok = assessment.war_started == threshold
            reasons.append("hostilities have begun")
        elif key == "c2_degraded":
            ok = assessment.c2_degraded >= float(threshold)
            reasons.append(f"C2 {assessment.c2_degraded:.0%} degraded")
        elif key == "air_superiority":
            ok = assessment.air_superiority >= float(threshold)
            reasons.append(
                f"air superiority ratio {min(assessment.air_superiority, 99):.1f}"
            )
        elif key == "enemy_air_attrition":
            drop = _ratio_drop(side, "enemy_fighters", assessment.enemy_fighters)
            ok = drop >= float(threshold)
            reasons.append(f"enemy air force {drop:.0%} attrited")
        elif key == "iads_effectiveness_below":
            start = side.baseline.get("battle_area_sams", 0.0)
            remaining = (
                0.0 if start <= 0 else assessment.battle_area_sams / max(start, 1.0)
            )
            ok = remaining <= float(threshold)
            reasons.append(f"battle-area IADS at {remaining:.0%}")
        elif key == "enemy_ground_attrition":
            drop = _ratio_drop(
                side, "enemy_ground_strength", assessment.enemy_ground_strength
            )
            ok = drop >= float(threshold)
            reasons.append(f"enemy ground forces {drop:.0%} attrited")
        elif key == "force_ratio":
            ok = assessment.main_effort_force_ratio >= float(threshold)
            reasons.append(
                f"main effort force ratio "
                f"{min(assessment.main_effort_force_ratio, 99):.1f}"
            )
        else:
            ok = False
        if not ok:
            return False, ""
    return True, ", ".join(reasons)


def _defense_triggered(
    spec_enter: dict[str, object], assessment: CampaignAssessment
) -> Optional[str]:
    below = spec_enter.get("force_ratio_below")
    if below is not None and assessment.min_force_ratio < float(below):  # type: ignore[arg-type]
        return f"outnumbered at the front (ratio {assessment.min_force_ratio:.2f})"
    if spec_enter.get("enemy_offensive_warning") and assessment.any_offensive_warning:
        return "intelligence warns of an enemy offensive"
    if spec_enter.get("base_threatened") and assessment.any_base_threatened:
        return "enemy forces threaten a friendly base"
    return None


class PhaseManager:
    def __init__(self, profile: PlanningProfile) -> None:
        self.profile = profile

    def decide(
        self, side: SideCampaign, assessment: CampaignAssessment, turn: int
    ) -> PhaseDecision:
        profile = self.profile
        order = profile.phase_order
        if not side.history:
            side.change_phase(order[0] if order else Phase.STRATEGIC, turn, "start")
        _capture_baseline(side, assessment)

        defense = profile.phases.get(Phase.DEFENSE)
        if defense is not None:
            trigger = _defense_triggered(defense.enter_when, assessment)
            if side.phase is not Phase.DEFENSE and trigger is not None:
                # Remember which offensive phase to resume.
                side.baseline["resume_phase"] = float(
                    order.index(side.phase) if side.phase in order else 0
                )
                resume_index = side.baseline["resume_phase"]
                side.change_phase(Phase.DEFENSE, turn, trigger)
                side.baseline["resume_phase"] = resume_index
                _capture_baseline(side, assessment)
                return PhaseDecision(Phase.DEFENSE, True, trigger)
            if side.phase is Phase.DEFENSE:
                if trigger is not None:
                    side.quiet_turns = 0
                    return PhaseDecision(Phase.DEFENSE, False, trigger)
                above = float(defense.leave_when.get("force_ratio_above", 1.0))
                quiet_needed = int(defense.leave_when.get("quiet_turns", 1))
                if assessment.min_force_ratio >= above:
                    side.quiet_turns += 1
                if side.quiet_turns >= quiet_needed:
                    index = int(side.baseline.get("resume_phase", 1))
                    resume = order[min(max(index, 0), len(order) - 1)]
                    if resume is Phase.POSTURE and len(order) > 1:
                        resume = order[1]
                    reason = "front stabilised; resuming the offensive campaign"
                    side.change_phase(resume, turn, reason)
                    _capture_baseline(side, assessment)
                    return PhaseDecision(resume, True, reason)
                return PhaseDecision(Phase.DEFENSE, False, "holding")

        if side.phase not in order:
            side.change_phase(order[0], turn, "reset")
            _capture_baseline(side, assessment)
        index = order.index(side.phase)
        spec = profile.phases[side.phase]
        held = turn - side.phase_since_turn
        min_turns = 0 if side.phase is Phase.POSTURE else profile.min_phase_turns
        if index + 1 < len(order) and held >= min_turns:
            met, reason = _advance_met(spec.advance_when, side, assessment)
            if met:
                next_phase = order[index + 1]
                side.change_phase(next_phase, turn, reason)
                _capture_baseline(side, assessment)
                return PhaseDecision(next_phase, True, reason)
        return PhaseDecision(side.phase, False, "conditions for advancing not met")
