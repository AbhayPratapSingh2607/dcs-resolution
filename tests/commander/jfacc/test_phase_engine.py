"""The data-driven phase engine: conditions, sustain, interrupts, $resume,
modifiers, profile changes and loading saves from before phases were data."""

from __future__ import annotations

import base64
import pickle
from typing import Any

import pytest
import yaml

from game.commander.jfacc.assessment import CampaignAssessment, FrontAssessment
from game.commander.jfacc.campaignstate import SideCampaign
from game.commander.jfacc.moes import REGISTRY, Evaluator, MoeContext
from game.commander.jfacc.phases import PhaseManager
from game.commander.jfacc.profile import (
    Family,
    Phase,
    load_profile,
    parse_profile,
    parse_when,
)


def _front(ratio: float, warning: bool = False) -> FrontAssessment:
    return FrontAssessment(
        front=None,  # type: ignore[arg-type]
        friendly_cp=None,  # type: ignore[arg-type]
        enemy_cp=None,  # type: ignore[arg-type]
        friendly_units=10 * ratio,
        enemy_units=10,
        troops_in_contact=True,
        enemy_offensive_warning=warning,
        base_threatened=False,
    )


def _assessment(**kwargs: Any) -> CampaignAssessment:
    values: dict[str, Any] = dict(
        turn=1,
        c2_degraded=0.0,
        air_superiority=1.0,
        own_fighters=20.0,
        enemy_fighters=20.0,
        battle_area_sams=10,
        enemy_ground_strength=100.0,
        fronts=[_front(1.2)],
        own_bases=5,
    )
    values.update(kwargs)
    return CampaignAssessment(**values)


TOY = """
name: toy
phases:
  min_turns: 2
  start: opening
  order: [opening, exploit]
  list:
    opening:
      title: "Opening air operation"
      family: offensive
      apportionment: {oca: 0.5, dca: 0.5}
      flags: {raid_style: massed}
      transitions:
        - to: exploit
          when: {moe: air_superiority, ge: 1.5, sustain: 2}
        - to: pvo
          min_turns: 0
          when: {moe: own_air_losses, ge: 0.4}
    exploit:
      title: "Exploitation"
      family: offensive
      apportionment: {cas: 1.0}
    pvo:
      title: "Air defense"
      family: defensive
      apportionment: {dca: 1.0}
      transitions:
        - to: $resume
          min_turns: 0
          when: {all: [{moe: air_superiority, ge: 1.0}, {moe: own_air_losses, le: 0.3}]}
  interrupts:
    - to: pvo
      from_families: [offensive]
      when: {any: [{moe: min_force_ratio, lt: 0.5}, {moe: bases_lost, ge: 1}]}
modifiers:
  force_preservation:
    description: "Pull back under the SAM umbrella"
    hold_turns: 2
    when: {moe: own_air_losses, ge: 0.25}
    effects: {dca_forward_scale: 0.4}
"""


@pytest.fixture()
def toy():  # type: ignore[no-untyped-def]
    return parse_profile("toy", yaml.safe_load(TOY))


def test_custom_phases_parse(toy) -> None:  # type: ignore[no-untyped-def]
    opening = toy.phase("opening")
    assert opening is Phase("opening")
    assert opening.title == "Opening air operation"
    assert toy.start_phase is opening
    assert toy.family_of(toy.phase("pvo")) is Family.DEFENSIVE
    assert toy.phases[opening].flag("raid_style") == "massed"
    assert [p.value for p in toy.phase_order] == ["opening", "exploit"]


def test_sustain_needs_consecutive_turns(toy) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(toy)
    side = SideCampaign()
    manager.decide(side, _assessment(), 0)
    strong = _assessment(air_superiority=2.0)
    weak = _assessment(air_superiority=1.0)
    # Min turns (2) first, then the condition must hold two turns running.
    assert manager.decide(side, strong, 1).phase.value == "opening"
    assert manager.decide(side, strong, 2).phase.value == "opening"
    assert manager.decide(side, weak, 3).phase.value == "opening"
    assert manager.decide(side, strong, 4).phase.value == "opening"
    decision = manager.decide(side, strong, 5)
    assert decision.phase.value == "exploit" and decision.changed
    assert "air superiority" in decision.reason


def test_interrupt_and_resume(toy) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(toy)
    side = SideCampaign()
    manager.decide(side, _assessment(), 0)
    decision = manager.decide(side, _assessment(fronts=[_front(0.3)]), 1)
    assert decision.phase.value == "pvo" and decision.changed
    assert side.resume_phase == "opening"
    # Still outnumbered: stays.
    assert manager.decide(side, _assessment(fronts=[_front(0.3)]), 2).phase.value == "pvo"
    # Front stable and air balance restored: back to the phase it left.
    decision = manager.decide(side, _assessment(air_superiority=1.2), 3)
    assert decision.phase.value == "opening" and decision.changed
    assert side.resume_phase == ""


def test_bases_lost_uses_campaign_baseline(toy) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(toy)
    side = SideCampaign()
    manager.decide(side, _assessment(own_bases=5), 0)
    assert side.campaign_baseline["own_bases"] == 5
    decision = manager.decide(side, _assessment(own_bases=4), 1)
    assert decision.phase.value == "pvo"
    assert "1 bases lost" in decision.reason


def test_transition_into_defensive_phase(toy) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(toy)
    side = SideCampaign()
    manager.decide(side, _assessment(own_fighters=20.0), 0)
    decision = manager.decide(side, _assessment(own_fighters=10.0), 1)
    assert decision.phase.value == "pvo"


def test_modifier_holds_for_its_duration(toy) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(toy)
    side = SideCampaign()
    assert manager.decide(side, _assessment(own_fighters=20.0), 0).modifiers == ()
    on = manager.decide(side, _assessment(own_fighters=14.0), 1)
    assert [m.name for m in on.modifiers] == ["force_preservation"]
    assert on.modifiers[0].effects["dca_forward_scale"] == 0.4
    # Conditions gone, but hold_turns keeps it one more turn.
    held = manager.decide(side, _assessment(own_fighters=20.0), 2)
    assert [m.name for m in held.modifiers] == ["force_preservation"]
    assert manager.decide(side, _assessment(own_fighters=20.0), 3).modifiers == ()


def test_switching_profile_restarts_at_its_start(toy) -> None:  # type: ignore[no-untyped-def]
    western = load_profile("western")
    assert western is not None
    side = SideCampaign()
    PhaseManager(western).decide(side, _assessment(), 0)
    assert side.phase is Phase.STRATEGIC
    decision = PhaseManager(toy).decide(side, _assessment(), 1)
    assert decision.phase.value == "opening"
    assert side.profile_name == "toy"
    assert "profile changed" in side.history[-1].reason


def test_unknown_transition_target_is_an_error() -> None:
    data = yaml.safe_load(TOY)
    data["phases"]["list"]["exploit"]["transitions"] = [
        {"to": "nowhere", "min_turns": 0, "when": {"moe": "turns_in_phase", "ge": 0}}
    ]
    profile = parse_profile("broken", data)
    manager = PhaseManager(profile)
    side = SideCampaign()
    side.change_phase(profile.phase("exploit"), 0, "test")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        manager.decide(side, _assessment(), 1)


# ----------------------------------------------------------------- MOEs


def test_condition_parsing_and_any_all() -> None:
    when = parse_when(
        {"any": [{"moe": "c2_degraded", "ge": 0.5}, {"all": [
            {"moe": "air_superiority", "gt": 2}, {"moe": "war_started", "eq": True}
        ]}]}
    )
    side = SideCampaign()
    ctx = MoeContext(side, _assessment(c2_degraded=0.1, air_superiority=3.0), 1)
    assert Evaluator(ctx).check(when)[0]
    ctx = MoeContext(side, _assessment(c2_degraded=0.1, air_superiority=1.0), 1)
    assert not Evaluator(ctx).check(when)[0]
    with pytest.raises(ValueError):
        parse_when({"moe": "c2_degraded", "ge": 1, "le": 2})


def test_every_profile_condition_uses_a_known_moe() -> None:
    from pathlib import Path

    from game.commander.jfacc.profile import Condition, PROFILE_DIR, When

    def moes(when: When) -> set[str]:
        names: set[str] = set()
        for item in when.items:
            names |= moes(item) if isinstance(item, When) else {item.moe}
        return names

    for path in Path(PROFILE_DIR).glob("*.yaml"):
        profile = load_profile(path.stem)
        assert profile is not None
        used: set[str] = set()
        for spec in profile.phases.values():
            for transition in spec.transitions:
                used |= moes(transition.when)
        for interrupt in profile.interrupts:
            used |= moes(interrupt.when)
        for modifier in profile.modifiers:
            used |= moes(modifier.when)
        assert used <= set(REGISTRY), (path.stem, used - set(REGISTRY))
        assert isinstance(Condition, type)


# ------------------------------------------------------------- migration

#: An AirCampaignState pickled by the code before phases were data (Phase
#: was an Enum): red in DEFENSE, resuming SEAD rollback (index 2).
LEGACY_STATE = (
    "gASVOwIAAAAAAACMImdhbWUuY29tbWFuZGVyLmpmYWNjLmNhbXBhaWduc3RhdGWUjBBBaXJDYW1w"
    "YWlnblN0YXRllJOUKYGUfZQojAVzaWRlc5R9lIloAIwMU2lkZUNhbXBhaWdulJOUKYGUfZQojAVw"
    "aGFzZZSMHGdhbWUuY29tbWFuZGVyLmpmYWNjLnByb2ZpbGWUjAVQaGFzZZSTlIwHZGVmZW5zZZSF"
    "lFKUjBBwaGFzZV9zaW5jZV90dXJulEsFjAdoaXN0b3J5lF2UKGgAjAtQaGFzZUNoYW5nZZSTlCmB"
    "lH2UKIwEdHVybpRLA2gLaA6MDXNlYWRfcm9sbGJhY2uUhZRSlIwGcmVhc29ulIwIcm9sbGJhY2uU"
    "dWJoFimBlH2UKGgZSwVoC2gRaB2MCGF0dGFja2VklHViZYwGaW50ZW50lIwAlIwHdGFyZ2V0c5R9"
    "lIwFamlwdGyUXZSMC2FwcG9ydGlvbmVklH2UjAdwbGFubmVklH2UjA10b3RhbF9zb3J0aWVzlEsA"
    "jARtb2VzlH2UjAhiYXNlbGluZZR9lIwMcmVzdW1lX3BoYXNllEdAAAAAAAAAAHOMC3F1aWV0X3R1"
    "cm5zlEsAjAhzY3J1YmJlZJRdlIwDcXJhlF2UdWJzjBF3aW5kb3dfb2Zmc2V0X21pbpRLAIwRZGVm"
    "ZXJyZWRfcGFja2FnZXOUfZSMDHBlcmlvZF9zdGFydJROjApwZXJpb2RfZW5klE6MC3BlcmlvZF90"
    "dXJulEr/////dWIu"
)


def test_legacy_save_loads_and_resumes() -> None:
    state = pickle.loads(base64.b64decode(LEGACY_STATE))
    side = state.side(False)
    assert side.phase is Phase.DEFENSE
    assert [c.phase for c in side.history] == [Phase.SEAD_ROLLBACK, Phase.DEFENSE]
    assert side.history[0].title == "Phase II: SEAD rollback"
    assert side.resume_phase == "sead_rollback"
    assert "resume_phase" not in side.baseline
    western = load_profile("western")
    assert western is not None
    decision = PhaseManager(western).decide(
        side, _assessment(fronts=[_front(1.5)]), 6
    )
    assert decision.phase is Phase.SEAD_ROLLBACK and decision.changed


def test_phases_round_trip_through_pickle(toy) -> None:  # type: ignore[no-untyped-def]
    side = SideCampaign()
    PhaseManager(toy).decide(side, _assessment(), 0)
    copy = pickle.loads(pickle.dumps(side))
    assert copy.phase is side.phase
    assert copy.phase.title == "Opening air operation"


# ------------------------------------------------------- legacy profiles

LEGACY_PROFILE = """
name: old
risk:
  phase_multiplier: {strategic: 1.5}
  rollback_allowance: {phases: [strategic], limit: 0.1, max_route_weight: 8}
ground_support:
  cas_attrition_per_period: {default: 0.3, defense: 0.5}
  air_assault: {phases: [ground_offensive]}
target_system_weights:
  strategic: {iads: 0.9, air: 1.0}
phases:
  min_turns: 2
  order: [posture, strategic, ground_offensive]
  posture:
    apportionment: {dca: 1.0}
    advance_when: {war_started: true}
  strategic:
    apportionment: {oca: 1.0}
    advance_when: {air_superiority: 1.5}
  ground_offensive:
    apportionment: {cas: 1.0}
  defense:
    apportionment: {dca: 1.0}
    enter_when: {force_ratio_below: 0.8}
    leave_when: {force_ratio_above: 1.1, quiet_turns: 1}
"""


def test_legacy_profile_schema_is_translated() -> None:
    profile = parse_profile("old", yaml.safe_load(LEGACY_PROFILE))
    strategic = profile.phases[Phase.STRATEGIC]
    assert strategic.flag("risk_multiplier") == 1.5
    assert strategic.flag("rollback_allowance") is True
    assert strategic.flag("cas_attrition") == 0.3
    assert strategic.target_weights
    assert profile.phases[Phase.GROUND_OFFENSIVE].flag("air_assault") is True
    assert profile.phases[Phase.DEFENSE].flag("cas_attrition") == 0.5
    assert profile.phases[Phase.POSTURE].family is Family.POSTURE
    assert [t.to for t in strategic.transitions] == ["ground_offensive"]
    assert profile.interrupts[0].to == "defense"
    manager = PhaseManager(profile)
    side = SideCampaign()
    assert manager.decide(side, _assessment(), 0).phase is Phase.STRATEGIC
    assert manager.decide(side, _assessment(fronts=[_front(0.5)]), 1).phase is Phase.DEFENSE
    assert manager.decide(side, _assessment(fronts=[_front(1.2)]), 2).phase is Phase.STRATEGIC
