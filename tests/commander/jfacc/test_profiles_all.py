"""Every planning profile is well formed, each doctrine but WWII has one,
and the OPFOR campaigns pick offense or defense from the balance of forces."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from game.commander.jfacc.apportionment import Apportionment
from game.commander.jfacc.assessment import CampaignAssessment, FrontAssessment
from game.commander.jfacc.campaignstate import SideCampaign
from game.commander.jfacc.phases import PhaseManager
from game.commander.jfacc.planner import JfaccPlanner
from game.commander.jfacc.profile import (
    PROFILE_DIR,
    RESUME,
    Category,
    Family,
    load_profile,
    merge_profiles,
)
from game.warfare.doctrine import _data, doctrine_named

PROFILES = sorted(p.stem for p in Path(PROFILE_DIR).glob("*.yaml"))
OPFOR = ["russian_modern", "soviet", "client", "irregular"]


@pytest.mark.parametrize("name", PROFILES)
def test_profile_is_well_formed(name: str) -> None:
    profile = load_profile(name)
    assert profile is not None
    assert profile.start_phase in profile.phases
    assert profile.phase_order and all(p in profile.phases for p in profile.phase_order)
    for phase, spec in profile.phases.items():
        for category, share in spec.apportionment.items():
            assert share.min <= share.share <= share.max, (name, phase, category)
        assert sum(s.share for s in spec.apportionment.values()) == pytest.approx(
            1.0, abs=0.05
        ), (name, phase)
        assert spec.target_weights, (name, phase)
        assert spec.flag("ground_stance", "hold") in ("attack", "hold", "defend")
        assert spec.flag("raid_style", "none") in ("massed", "opportunistic", "none")
        for transition in spec.transitions:
            assert transition.to == RESUME or profile.phase(transition.to), (
                name,
                phase,
                transition.to,
            )
    for interrupt in profile.interrupts:
        assert profile.phase(interrupt.to), (name, interrupt.to)
    # Every campaign can go on the defensive.
    assert any(s.family is Family.DEFENSIVE for s in profile.phases.values()), name


def test_shared_phase_ids_have_one_title() -> None:
    titles: dict[str, set[str]] = {}
    for name in PROFILES:
        profile = load_profile(name)
        assert profile is not None
        for phase in profile.phases:
            titles.setdefault(phase.value, set()).add(phase.title)
    assert all(len(t) == 1 for t in titles.values()), titles


def test_every_doctrine_but_ww2_has_a_profile() -> None:
    for name in _data()["doctrines"]:
        doctrine = doctrine_named(name)
        if name == "ww2":
            assert not doctrine.planning_profile
            continue
        assert doctrine.planning_profile, name
        assert load_profile(doctrine.planning_profile) is not None, name


def test_profiles_inherit_and_override() -> None:
    russian = load_profile("russian_modern")
    soviet = load_profile("soviet")
    client = load_profile("client")
    assert russian is not None and soviet is not None and client is not None
    # Soviet adjusts the Russian campaign (merge: true) ...
    assert [p.value for p in soviet.phase_order] == [p.value for p in russian.phase_order]
    iao = soviet.phase("initial_air_operation")
    assert iao is not None
    assert soviet.phases[iao].flag("risk_multiplier") == 1.3
    assert soviet.phases[iao].flag("raid_style") == "massed"
    # ... and keeps what it doesn't override.
    assert soviet.get("packages", "require_sead", True) is False
    assert soviet.get("packages", "max_strikers", 0) == 12
    # Client replaces the campaign entirely.
    assert client.phase("initial_air_operation") is None
    assert client.start_phase.value == "readiness"
    assert client.get("dca", "hvaa_cap", True) is False
    # OPFOR doctrines accept more risk than NATO.
    western = load_profile("western")
    assert western is not None
    for profile in (russian, soviet, client):
        assert profile.attrition_limit > western.attrition_limit


def test_merge_replaces_phases_unless_asked() -> None:
    base = {"phases": {"list": {"a": {}, "b": {}}}, "dca": {"x": 1, "y": 2}}
    replaced = merge_profiles(base, {"phases": {"list": {"c": {}}}, "dca": {"y": 3}})
    assert list(replaced["phases"]["list"]) == ["c"]
    assert replaced["dca"] == {"x": 1, "y": 3}
    merged = merge_profiles(base, {"phases": {"merge": True, "list": {"c": {}}}})
    assert list(merged["phases"]["list"]) == ["a", "b", "c"]
    assert "merge" not in merged["phases"]


# ------------------------------------------------------------- stance


def _front(ratio: float) -> FrontAssessment:
    return FrontAssessment(
        front=None,  # type: ignore[arg-type]
        friendly_cp=None,  # type: ignore[arg-type]
        enemy_cp=None,  # type: ignore[arg-type]
        friendly_units=10 * ratio,
        enemy_units=10,
        troops_in_contact=True,
        enemy_offensive_warning=False,
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
        fronts=[_front(1.0)],
        own_bases=5,
    )
    values.update(kwargs)
    return CampaignAssessment(**values)


@pytest.mark.parametrize(
    "name,favourable,unfavourable",
    [
        ("russian_modern", "initial_air_operation", "pvo_defense"),
        ("soviet", "initial_air_operation", "pvo_defense"),
        ("client", "limited_offensive", "homeland_air_defense"),
        ("irregular", "harass", "survive"),
    ],
)
def test_opfor_picks_its_campaign_from_the_balance(
    name: str, favourable: str, unfavourable: str
) -> None:
    profile = load_profile(name)
    assert profile is not None
    strong = _assessment(air_superiority=1.5, fronts=[_front(1.5)])
    weak = _assessment(air_superiority=0.4, fronts=[_front(0.9)])
    side = SideCampaign()
    assert PhaseManager(profile).decide(side, strong, 1).phase.value == favourable
    side = SideCampaign()
    assert PhaseManager(profile).decide(side, weak, 1).phase.value == unfavourable


def test_russian_air_operation_is_time_bound() -> None:
    profile = load_profile("russian_modern")
    assert profile is not None
    manager = PhaseManager(profile)
    side = SideCampaign()
    even = _assessment(air_superiority=1.0, fronts=[_front(1.0)])
    assert manager.decide(side, even, 1).phase.value == "initial_air_operation"
    phases = [manager.decide(side, even, turn).phase.value for turn in range(2, 6)]
    assert phases[-1] == "front_offensive", phases


def test_losing_the_air_war_turns_russia_to_defense_and_preservation() -> None:
    profile = load_profile("russian_modern")
    assert profile is not None
    manager = PhaseManager(profile)
    side = SideCampaign()
    manager.decide(side, _assessment(air_superiority=1.0, own_fighters=40.0), 1)
    decision = manager.decide(
        side, _assessment(air_superiority=0.6, own_fighters=24.0), 2
    )
    assert decision.phase.value == "pvo_defense"
    assert [m.name for m in decision.modifiers] == ["force_preservation"]


# ----------------------------------------------------- modifier effects


def _planner_with(modifiers: tuple[Any, ...], phase: str = "initial_air_operation") -> Any:
    profile = load_profile("russian_modern")
    assert profile is not None
    planner = JfaccPlanner.__new__(JfaccPlanner)
    planner.profile = profile
    planner.modifiers = modifiers
    planner.spec = profile.phases[profile.phase(phase)]  # type: ignore[index]
    planner.apportionment = Apportionment.for_phase(profile, planner.spec, 100)
    return planner


def test_force_preservation_cuts_offensive_sorties() -> None:
    profile = load_profile("russian_modern")
    assert profile is not None
    preservation = profile.modifiers[0]
    planner = _planner_with((preservation,))
    oca = planner.apportionment.quota[Category.OCA]
    dca = planner.apportionment.quota[Category.DCA]
    planner._apply_category_scaling()
    assert planner.apportionment.quota[Category.OCA] == round(oca * 0.3)
    assert planner.apportionment.ceiling[Category.OCA] < round(100 * 0.35)
    assert planner.apportionment.quota[Category.DCA] == dca
    assert planner.raid_style == "none"
    assert planner.effect("cap_under_own_sam", False) is True
    assert planner.effect("dca_forward_scale", 1.0) == 0.4


def test_effects_combine() -> None:
    a = SimpleNamespace(effects={"risk_scale": 0.5, "raid_style": "none"})
    b = SimpleNamespace(effects={"risk_scale": 0.5, "cap_under_own_sam": True})
    planner = _planner_with((a, b))
    assert planner.effect("risk_scale", 1.0) == 0.25
    assert planner.effect("cap_under_own_sam", False) is True
    assert planner.raid_style == "none"
    assert _planner_with(()).raid_style == "massed"
