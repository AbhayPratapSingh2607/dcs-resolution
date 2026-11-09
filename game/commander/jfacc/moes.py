"""Measures of effectiveness (MOEs) that phase transitions, interrupts and
modifiers test, by name.

Every MOE is computed from the side's own campaign assessment (its
intelligence picture) and its campaign memory. Nothing here reads the
enemy's true state.

Add an MOE with ``@moe("name", "label {value}")``. The label is used in the
reason recorded with a phase change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from .assessment import CampaignAssessment
from .campaignstate import SideCampaign
from .profile import Condition, When


@dataclass
class MoeContext:
    side: SideCampaign
    assessment: CampaignAssessment
    turn: int


@dataclass(frozen=True)
class MoeSpec:
    name: str
    compute: Callable[[MoeContext], Any]
    #: Format for the reason text; ``{value}`` is replaced.
    label: str
    #: Label used when a boolean MOE is true.
    true_label: Optional[str] = None


REGISTRY: dict[str, MoeSpec] = {}


def moe(
    name: str, label: str, true_label: Optional[str] = None
) -> Callable[[Callable[[MoeContext], Any]], Callable[[MoeContext], Any]]:
    def register(fn: Callable[[MoeContext], Any]) -> Callable[[MoeContext], Any]:
        REGISTRY[name] = MoeSpec(name, fn, label, true_label)
        return fn

    return register


def _ratio_drop(baseline: dict[str, float], key: str, now: float) -> float:
    """Share of the baseline value that has been destroyed."""
    start = baseline.get(key, 0.0)
    if start <= 0:
        return 1.0
    return max(0.0, 1.0 - now / start)


def _capped(value: float) -> float:
    return min(value, 99.0) if not math.isnan(value) else 0.0


# ------------------------------------------------------------------- MOEs


@moe("war_started", "hostilities started: {value}", "hostilities have begun")
def _war_started(ctx: MoeContext) -> bool:
    return ctx.assessment.war_started


@moe("c2_degraded", "C2 {value:.0%} degraded")
def _c2_degraded(ctx: MoeContext) -> float:
    return ctx.assessment.c2_degraded


@moe("air_superiority", "air superiority ratio {value:.1f}")
def _air_superiority(ctx: MoeContext) -> float:
    return _capped(ctx.assessment.air_superiority)


@moe("enemy_air_attrition", "enemy air force {value:.0%} attrited")
def _enemy_air_attrition(ctx: MoeContext) -> float:
    return _ratio_drop(ctx.side.baseline, "enemy_fighters", ctx.assessment.enemy_fighters)


@moe("iads_remaining", "battle-area IADS at {value:.0%}")
def _iads_remaining(ctx: MoeContext) -> float:
    start = ctx.side.baseline.get("battle_area_sams", 0.0)
    if start <= 0:
        return 0.0
    return ctx.assessment.battle_area_sams / max(start, 1.0)


@moe("enemy_ground_attrition", "enemy ground forces {value:.0%} attrited")
def _enemy_ground_attrition(ctx: MoeContext) -> float:
    return _ratio_drop(
        ctx.side.baseline, "enemy_ground_strength", ctx.assessment.enemy_ground_strength
    )


@moe("main_effort_force_ratio", "main effort force ratio {value:.1f}")
def _main_effort_force_ratio(ctx: MoeContext) -> float:
    return _capped(ctx.assessment.main_effort_force_ratio)


@moe("min_force_ratio", "weakest front force ratio {value:.2f}")
def _min_force_ratio(ctx: MoeContext) -> float:
    return _capped(ctx.assessment.min_force_ratio)


@moe(
    "offensive_warning",
    "enemy offensive warning: {value}",
    "intelligence warns of an enemy offensive",
)
def _offensive_warning(ctx: MoeContext) -> bool:
    return ctx.assessment.any_offensive_warning


@moe(
    "base_threatened",
    "base threatened: {value}",
    "enemy forces threaten a friendly base",
)
def _base_threatened(ctx: MoeContext) -> bool:
    return ctx.assessment.any_base_threatened


@moe("turns_in_phase", "{value} turns in the phase")
def _turns_in_phase(ctx: MoeContext) -> int:
    return ctx.turn - ctx.side.phase_since_turn


@moe("own_air_losses", "own fighter force {value:.0%} lost")
def _own_air_losses(ctx: MoeContext) -> float:
    """Share of the side's fighter strength lost since the war started
    (campaign baseline, not the phase baseline)."""
    start = ctx.side.campaign_baseline.get("own_fighters", 0.0)
    if start <= 0:
        return 0.0
    return max(0.0, 1.0 - ctx.assessment.own_fighters / start)


@moe("bases_lost", "{value} bases lost")
def _bases_lost(ctx: MoeContext) -> int:
    start = ctx.side.campaign_baseline.get("own_bases", 0.0)
    return max(0, int(start - ctx.assessment.own_bases))


@moe("bases_taken", "{value} bases taken")
def _bases_taken(ctx: MoeContext) -> int:
    start = ctx.side.campaign_baseline.get("own_bases", 0.0)
    return max(0, int(ctx.assessment.own_bases - start))


@moe("enemy_sortie_pressure", "{value:.0f} enemy aircraft seen last period")
def _enemy_sortie_pressure(ctx: MoeContext) -> float:
    return float(ctx.side.enemy_sorties_seen)


# --------------------------------------------------------------- evaluation


def value_of(name: str, ctx: MoeContext) -> Any:
    spec = REGISTRY.get(name)
    if spec is None:
        raise KeyError(f"Unknown MOE {name!r}")
    return spec.compute(ctx)


def _compare(op: str, value: Any, threshold: Any) -> bool:
    if isinstance(threshold, bool) or isinstance(value, bool):
        if op == "eq":
            return bool(value) == bool(threshold)
        if op == "ne":
            return bool(value) != bool(threshold)
    value_f = float(value)
    threshold_f = float(threshold)
    return {
        "ge": value_f >= threshold_f,
        "gt": value_f > threshold_f,
        "le": value_f <= threshold_f,
        "lt": value_f < threshold_f,
        "eq": value_f == threshold_f,
        "ne": value_f != threshold_f,
    }[op]


def describe(condition: Condition, value: Any) -> str:
    spec = REGISTRY.get(condition.moe)
    if spec is None:
        return f"{condition.moe} {value}"
    if spec.true_label is not None and isinstance(value, bool) and value:
        return spec.true_label
    try:
        return spec.label.format(value=value)
    except (ValueError, TypeError):
        return f"{condition.moe} {value}"


class Evaluator:
    """Evaluates conditions against one assessment. Conditions with
    ``sustain`` count consecutive turns in ``counters`` (stored in the side's
    campaign state); ``prefix`` keeps the counters of different conditions
    apart."""

    def __init__(self, ctx: MoeContext, counters: Optional[dict[str, int]] = None):
        self.ctx = ctx
        self.counters = counters if counters is not None else {}
        self._values: dict[str, Any] = {}

    def value(self, name: str) -> Any:
        if name not in self._values:
            try:
                self._values[name] = value_of(name, self.ctx)
            except KeyError:
                self._values[name] = None
        return self._values[name]

    def check(self, when: When, prefix: str = "") -> tuple[bool, str]:
        """(met, reason). Every item is evaluated (no short circuit) so
        sustain counters stay correct."""
        if when.empty:
            return False, ""
        results: list[tuple[bool, str]] = [
            self._check_item(item, f"{prefix}.{i}") for i, item in enumerate(when.items)
        ]
        if when.mode == "any":
            met = [reason for ok, reason in results if ok]
            return (True, met[0]) if met else (False, "")
        if all(ok for ok, _ in results):
            return True, ", ".join(reason for _, reason in results if reason)
        return False, ""

    def _check_item(self, item: Union[Condition, When], key: str) -> tuple[bool, str]:
        if isinstance(item, When):
            return self.check(item, key)
        value = self.value(item.moe)
        ok = value is not None and _compare(item.op, value, item.value)
        if item.sustain > 1:
            count = self.counters.get(key, 0) + 1 if ok else 0
            self.counters[key] = count
            ok = count >= item.sustain
        return ok, describe(item, value) if ok else ""
