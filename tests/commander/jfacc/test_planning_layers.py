"""Unit tests for the JFACC planner layers that don't need a game:
profile loading, phase transitions, apportionment, the sortie ledger, the
timeline and the risk estimate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

from game.commander.jfacc import sorties
from game.commander.jfacc.apportionment import Apportionment
from game.commander.jfacc.assessment import CampaignAssessment, FrontAssessment
from game.commander.jfacc.campaignstate import AirCampaignState, SideCampaign
from game.commander.jfacc.phases import PhaseManager
from game.commander.jfacc.profile import Category, Phase, load_profile
from game.commander.jfacc.risk import estimate
from game.commander.jfacc.scheduler import Timeline
from game.commander.jfacc.threat import RouteThreat

START = datetime(2020, 6, 1, 6, 0)
END = START + timedelta(hours=6)


@pytest.fixture(scope="module")
def profile():  # type: ignore[no-untyped-def]
    loaded = load_profile("western")
    assert loaded is not None
    return loaded


# ---------------------------------------------------------------- profile


def test_profile_loads_all_phases(profile) -> None:  # type: ignore[no-untyped-def]
    assert profile.phase_order == [
        Phase.POSTURE,
        Phase.STRATEGIC,
        Phase.SEAD_ROLLBACK,
        Phase.BATTLEFIELD_PREP,
        Phase.GROUND_OFFENSIVE,
    ]
    assert Phase.DEFENSE in profile.phases
    assert 0 < profile.mc_rate <= 1
    assert profile.period_hours == 6


def test_apportionment_shares_are_consistent(profile) -> None:  # type: ignore[no-untyped-def]
    for phase, spec in profile.phases.items():
        for category, share in spec.apportionment.items():
            assert share.min <= share.share <= share.max, (phase, category)
        assert sum(s.share for s in spec.apportionment.values()) == pytest.approx(
            1.0, abs=0.05
        ), phase


def test_unknown_profile_is_none() -> None:
    assert load_profile("does-not-exist") is None


# ----------------------------------------------------------------- phases


def _assessment(**overrides: object) -> CampaignAssessment:
    values: dict[str, object] = dict(
        turn=1,
        c2_degraded=0.0,
        air_superiority=1.0,
        own_fighters=20.0,
        enemy_fighters=20.0,
        battle_area_sams=10,
        enemy_ground_strength=50.0,
    )
    values.update(overrides)
    return CampaignAssessment(**values)  # type: ignore[arg-type]


def _front(ratio: float, warning: bool = False) -> FrontAssessment:
    return FrontAssessment(
        front=object(),  # type: ignore[arg-type]
        friendly_cp=object(),  # type: ignore[arg-type]
        enemy_cp=object(),  # type: ignore[arg-type]
        friendly_units=10 * ratio,
        enemy_units=10,
        troops_in_contact=True,
        enemy_offensive_warning=warning,
        base_threatened=False,
    )


def test_posture_advances_to_strategic_when_war_starts(profile) -> None:  # type: ignore[no-untyped-def]
    side = SideCampaign()
    decision = PhaseManager(profile).decide(side, _assessment(fronts=[_front(1.2)]), 0)
    assert decision.phase is Phase.STRATEGIC
    assert decision.changed


def test_strategic_holds_for_min_turns(profile) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(profile)
    side = SideCampaign()
    manager.decide(side, _assessment(fronts=[_front(1.2)]), 0)
    assert side.phase is Phase.STRATEGIC
    winning = _assessment(
        c2_degraded=0.8,
        air_superiority=3.0,
        enemy_fighters=5.0,
        fronts=[_front(1.2)],
    )
    # Criteria met immediately, but the phase must run its minimum length.
    assert manager.decide(side, winning, 1).phase is Phase.STRATEGIC
    assert manager.decide(side, winning, 2).phase is Phase.SEAD_ROLLBACK


def test_strategic_needs_all_criteria(profile) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(profile)
    side = SideCampaign()
    manager.decide(side, _assessment(fronts=[_front(1.2)]), 0)
    # Air superiority without C2 degradation is not enough.
    partial = _assessment(air_superiority=3.0, enemy_fighters=5.0, fronts=[_front(1.2)])
    assert manager.decide(side, partial, 5).phase is Phase.STRATEGIC


def test_defense_overrides_and_resumes(profile) -> None:  # type: ignore[no-untyped-def]
    manager = PhaseManager(profile)
    side = SideCampaign()
    manager.decide(side, _assessment(fronts=[_front(1.2)]), 0)
    assert side.phase is Phase.STRATEGIC
    attacked = _assessment(fronts=[_front(0.3, warning=True)])
    decision = manager.decide(side, attacked, 1)
    assert decision.phase is Phase.DEFENSE and decision.changed
    calm = _assessment(fronts=[_front(1.5)])
    turn = 2
    while side.phase is Phase.DEFENSE and turn < 10:
        manager.decide(side, calm, turn)
        turn += 1
    assert side.phase is Phase.STRATEGIC


# --------------------------------------------------------- apportionment


def test_apportionment_quota_and_overflow(profile) -> None:  # type: ignore[no-untyped-def]
    spec = profile.phases[Phase.STRATEGIC]
    app = Apportionment.for_phase(profile, spec, 100)
    oca = app.remaining(Category.OCA)
    assert oca == app.quota[Category.OCA] > 0
    app.spend(Category.OCA, oca)
    assert app.remaining(Category.OCA) == 0
    assert not app.can_afford(Category.OCA, 2)
    app.begin_overflow()
    # During overflow a category may grow to its ceiling.
    assert app.remaining(Category.OCA) == app.ceiling[Category.OCA] - oca


def test_apportionment_overflow_respects_total(profile) -> None:  # type: ignore[no-untyped-def]
    spec = profile.phases[Phase.STRATEGIC]
    app = Apportionment.for_phase(profile, spec, 20)
    for category in Category:
        app.spend(category, app.quota[category])
    app.begin_overflow()
    leftover = app.unused()
    for category in Category:
        if app.remaining(category) > 0:
            assert not app.can_afford(category, leftover + 1)


# ------------------------------------------------------------ sortie ledger


@dataclass
class _Aircraft:
    variant_id: str = "F-16C"


class _Squadron:
    def __init__(self, untasked: int, name: str = "VF-1") -> None:
        self.untasked_aircraft = untasked
        self.name = name
        self.aircraft = _Aircraft()

    def __hash__(self) -> int:
        return id(self)


@pytest.fixture
def ledger(profile, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sorties, "role_for", lambda squadron: "fighter")
    return sorties.SortieLedger(profile, START, END, seed=7)


def test_ledger_mc_rate(ledger, profile) -> None:  # type: ignore[no-untyped-def]
    squadron = _Squadron(20)
    capable = ledger.mission_capable(squadron)
    assert abs(capable - 20 * profile.mc_rate) <= 1
    assert ledger.mission_capable(_Squadron(1, "det")) == 1
    assert ledger.mission_capable(_Squadron(0, "empty")) == 0


def test_ledger_no_double_booking(ledger) -> None:  # type: ignore[no-untyped-def]
    squadron = _Squadron(2)
    capable = ledger.mission_capable(squadron)
    first = ledger.find(squadron, capable, START, START + timedelta(hours=2))
    assert first is not None and first.fresh == capable
    ledger.commit(first)
    squadron.untasked_aircraft -= first.fresh
    # Overlapping sortie: nothing left.
    assert ledger.find(squadron, 1, START + timedelta(hours=1), START + timedelta(hours=3)) is None


def test_ledger_second_sortie_after_turnaround(ledger, profile) -> None:  # type: ignore[no-untyped-def]
    squadron = _Squadron(2)
    capable = ledger.mission_capable(squadron)
    land = START + timedelta(hours=1.5)
    first = ledger.find(squadron, capable, START, land)
    assert first is not None
    ledger.commit(first)
    squadron.untasked_aircraft -= first.fresh
    turnaround = timedelta(hours=profile.turnaround_hours("fighter"))
    early = ledger.find(squadron, 1, land + turnaround / 2, land + turnaround)
    assert early is None
    later = ledger.find(squadron, capable, land + turnaround, land + turnaround * 2)
    assert later is not None
    # The same jets fly again: no extra inventory.
    assert later.fresh == 0 and later.reused == capable
    ledger.commit(later)
    assert ledger.second_sorties() == capable
    # Surge limit: no third sortie.
    third_start = land + turnaround * 3
    if profile.max_sorties_per_airframe == 2:
        assert ledger.find(squadron, 1, third_start, third_start + timedelta(hours=1)) is None


def test_ledger_release(ledger) -> None:  # type: ignore[no-untyped-def]
    squadron = _Squadron(4)
    alloc = ledger.find(squadron, 2, START, START + timedelta(hours=2))
    assert alloc is not None
    ledger.commit(alloc)
    assert ledger.sorties_flown() == 2
    ledger.release(alloc)
    assert ledger.sorties_flown() == 0


# ---------------------------------------------------------------- timeline


@dataclass
class _Point:
    x: float
    y: float

    def distance_to_point(self, other: "_Point") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


def test_timeline_deconflicts_nearby_targets(profile) -> None:  # type: ignore[no-untyped-def]
    timeline = Timeline(profile, START, END)
    here = _Point(0, 0)
    first = timeline.strike_tot(here, preferred_wave=0)  # type: ignore[arg-type]
    assert first is not None and first >= timeline.earliest
    timeline.reserve(first, here)  # type: ignore[arg-type]
    second = timeline.strike_tot(here, preferred_wave=0)  # type: ignore[arg-type]
    assert second is not None
    assert abs(second - first) >= timeline.separation
    # A distant target can share the TOT.
    far = _Point(timeline.corridor_m * 3, 0)
    assert timeline.strike_tot(far, preferred_wave=0) == first  # type: ignore[arg-type]


def test_timeline_waves_cover_period(profile) -> None:  # type: ignore[no-untyped-def]
    waves = Timeline(profile, START, END).wave_times()
    assert waves == sorted(waves)
    assert all(START <= w < END for w in waves)
    assert waves[-1] - waves[0] > timedelta(hours=3)


def test_relief_chain_has_no_gaps(profile) -> None:  # type: ignore[no-untyped-def]
    timeline = Timeline(profile, START, END)
    on_station = timedelta(minutes=40)
    tots = timeline.relief_tots(on_station)
    assert tots[0] <= START + timedelta(minutes=15)
    for a, b in zip(tots, tots[1:]):
        assert b - a < on_station
    assert tots[-1] + on_station >= END


# -------------------------------------------------------------------- risk


def test_risk_falls_with_sead_and_jamming() -> None:
    threat = RouteThreat(sam_weight=8.0, air_strength=0.0)
    bare = estimate(threat, 0, 0, 0, False).expected_loss_rate
    sead = estimate(threat, 6, 0, 0, False).expected_loss_rate
    full = estimate(threat, 6, 2, 0, False).expected_loss_rate
    assert bare > sead > full > 0


def test_risk_falls_with_escort_and_awacs() -> None:
    threat = RouteThreat(sam_weight=0.0, air_strength=20.0)
    bare = estimate(threat, 0, 0, 0, False).expected_loss_rate
    escorted = estimate(threat, 0, 0, 4, False).expected_loss_rate
    awacs = estimate(threat, 0, 0, 4, True).expected_loss_rate
    assert bare > escorted > awacs


def test_risk_unthreatened_is_zero() -> None:
    assert estimate(RouteThreat(), 0, 0, 0, False).expected_loss_rate == 0


# ---------------------------------------------------------- campaign state


def test_campaign_state_sides_are_independent() -> None:
    state = AirCampaignState()
    blue = state.side(True)
    red = state.side(False)
    blue.phase = Phase.SEAD_ROLLBACK
    assert red.phase is not Phase.SEAD_ROLLBACK
    assert state.maybe_side(True) is blue


def test_risk_grows_faster_than_sam_weight() -> None:
    def rate(weight: float) -> float:
        threat = RouteThreat(sam_weight=weight, target_defended=True)
        return estimate(threat, 0, 0, 0, False).expected_loss_rate

    # Overlapping sites compound: doubling the weight more than doubles the
    # exposure (until the loss rate saturates).
    assert rate(4) > 0
    assert rate(4) / rate(2) > 2


def test_transit_and_front_line_reduce_exposure() -> None:
    defended = RouteThreat(sam_weight=6.0, target_defended=True)
    transit = RouteThreat(sam_weight=6.0, target_defended=False)
    full = estimate(defended, 4, 0, 0, False).expected_loss_rate
    assert estimate(transit, 4, 0, 0, False).expected_loss_rate < full
    assert estimate(defended, 4, 0, 0, False, front_line=True).expected_loss_rate < full


def test_rollback_allowance_is_configured(profile) -> None:  # type: ignore[no-untyped-def]
    allowance = profile.section("risk")["rollback_allowance"]
    assert "strategic" in allowance["phases"]
    assert allowance["limit"] > profile.attrition_limit


# ------------------------------------------------------------ CAS estimate


def test_cas_kills_follow_the_loadout(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from types import SimpleNamespace

    from game.commander.jfacc import casestimate
    from game.sim.combat.model import profiles as combat_profiles
    from game.sim.combat.model.profiles import Guidance, Warhead, WeaponRole

    weapons = {
        "maverick": SimpleNamespace(
            role=WeaponRole.A2G, guidance=Guidance.IIR, warhead=Warhead.HEAVY,
            count=1, accuracy=0.8,
        ),
        "cbu": SimpleNamespace(
            role=WeaponRole.A2G, guidance=Guidance.CLUSTER, warhead=Warhead.CLUSTER,
            count=1, accuracy=0.5,
        ),
        "jdam": SimpleNamespace(
            role=WeaponRole.A2G, guidance=Guidance.GPS, warhead=Warhead.HEAVY,
            count=1, accuracy=0.9,
        ),
        "aim9": SimpleNamespace(
            role=WeaponRole.A2A, guidance=Guidance.IR, warhead=Warhead.NONE,
            count=1, accuracy=0.0,
        ),
    }
    fake = SimpleNamespace(
        weapon=lambda name: weapons[name],
        aircraft=lambda _: SimpleNamespace(generation=4.0),
    )
    monkeypatch.setattr(combat_profiles.CombatProfiles, "instance", lambda: fake)

    def flight(*loadout: str, members: int = 2) -> SimpleNamespace:
        pylons = {i: w for i, w in enumerate(loadout)}
        member = SimpleNamespace(loadout=SimpleNamespace(pylons=pylons))
        return SimpleNamespace(
            unit_type=SimpleNamespace(has_built_in_target_pod=True),
            count=members,
            iter_members=lambda: [member] * members,
        )

    a2a_only = casestimate.expected_front_kills(flight("aim9", "aim9"))
    mavericks = casestimate.expected_front_kills(flight("maverick", "maverick"))
    jdams = casestimate.expected_front_kills(flight("jdam", "jdam"))
    assert a2a_only == 0
    # Seekers find moving vehicles; coordinate-seeking bombs mostly miss.
    assert mavericks > 2 * jdams
    # More weapons, more kills; more aircraft, more kills.
    assert casestimate.expected_front_kills(
        flight("maverick", "maverick", "cbu", "cbu")
    ) > mavericks
    assert casestimate.expected_front_kills(
        flight("maverick", "maverick", members=4)
    ) == pytest.approx(2 * mavericks)
    # Cluster bombs do more against soft vehicles than against armor.
    assert casestimate.expected_front_kills(
        flight("cbu"), armor_share=0.0
    ) > casestimate.expected_front_kills(flight("cbu"), armor_share=1.0)


def test_flight_types_map_to_apportionment_categories() -> None:
    from game.ato.flighttype import FlightType
    from game.commander.jfacc.profile import category_for_task

    assert category_for_task(FlightType.BARCAP) is Category.DCA
    assert category_for_task(FlightType.DEAD) is Category.SEAD
    assert category_for_task(FlightType.CAS) is Category.CAS
    assert category_for_task(FlightType.AEWC) is Category.SUPPORT
    assert category_for_task(FlightType.TRANSPORT) is None


def test_procurement_is_configured(profile) -> None:  # type: ignore[no-untyped-def]
    assert profile.section("procurement")["replacements_per_squadron"] > 0
