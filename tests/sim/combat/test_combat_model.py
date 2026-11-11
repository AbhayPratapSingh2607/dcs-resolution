"""Tests for the fast-forward combat model.

Most tests use small seeded Monte Carlo runs over synthetic scenarios (real
aircraft, weapon and air defense data, minimal game). The full calibration
suite with larger samples is resources/tools/combat_calibration.py.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from dcs import planes, vehicles
from dcs.statics import Fortification

from game.ato.flighttype import FlightType
from game.ato.flightstate.killed import Killed
from game.debriefing import AirLosses, Debriefing, GroundLosses
from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import CombatGroup, CombatGroupRole
from game.ground_forces.combat_stance import CombatStance
from game.sim.combat.model.environment import CombatEnvironment
from game.sim.combat.model.engine import radar_horizon_km
from game.sim.combat.model.groundbattle import FrontState, GroundWar, SideState
from game.sim.combat.model.profiles import (
    Guidance,
    WeaponRole,
    _count_from_name,
    normalize_weapon_name,
)
from game.sim.combat.model.scenario import Scenario, loadout, point, weapon
from game.sim.gameupdateevents import GameUpdateEvents
from game.theater.player import Player
from game.timeofday import TimeOfDay

AD = vehicles.AirDefence
OVERCAST_LOW = CombatEnvironment(TimeOfDay.Day, 15, 800, 2500, 0.95, False, False)


@pytest.fixture(autouse=True)
def quiet() -> Any:
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


# --------------------------------------------------------------------- data


def test_weapon_names_normalize_with_counts() -> None:
    assert normalize_weapon_name("2xAIM-9M") == ("AIM9M", 2)
    assert normalize_weapon_name("R-60M x 2") == ("R60M", 2)
    assert normalize_weapon_name("AIM-120C-2X") == ("AIM120C", 2)
    assert normalize_weapon_name("R-73 (AA-11 Archer) - Infra Red") == ("R73", 1)
    assert _count_from_name("3 GBU-38") == 3
    assert _count_from_name("Mk-82 * 6") == 6
    assert _count_from_name("250 lb MC Mk.II") == 1


@pytest.mark.parametrize(
    "group,role,guidance",
    [
        ("AIM-120C", WeaponRole.A2A, Guidance.ARH),
        ("AIM-7M", WeaponRole.A2A, Guidance.SARH),
        ("AIM-9X", WeaponRole.A2A, Guidance.IR),
        ("GBU-12", WeaponRole.A2G, Guidance.LASER),
        ("GBU-38", WeaponRole.A2G, Guidance.GPS),
        ("Mk 82", WeaponRole.A2G, Guidance.UNGUIDED),
        ("CBU-97", WeaponRole.A2G, Guidance.CLUSTER),
        ("AGM-65D", WeaponRole.A2G, Guidance.IIR),
        ("AGM-88C HARM", WeaponRole.ARM, Guidance.ANTI_RADIATION),
        ("AN/AAQ-28 LITENING", WeaponRole.TGP, Guidance.NONE),
    ],
)
def test_weapon_classification(
    group: str, role: WeaponRole, guidance: Guidance
) -> None:
    scenario = Scenario()
    profile = scenario.model.profiles.weapon(weapon(group))
    assert profile.role is role
    assert profile.guidance is guidance


def test_radar_range_follows_fourth_root_of_rcs() -> None:
    scenario = Scenario()
    from game.dcs.aircrafttype import AircraftType

    eagle = scenario.model.profiles.aircraft(
        next(AircraftType.for_dcs_type(planes.F_15C))
    )
    assert eagle.radar_km == 110
    assert eagle.radar_detection_range_km(5) == pytest.approx(110)
    # 1/16th the RCS -> half the range.
    assert eagle.radar_detection_range_km(5 / 16) == pytest.approx(55)


def test_radar_horizon() -> None:
    # A target at 100 m is seen by a 5 m mast at about 50 km, at 10 km altitude
    # from about 420 km.
    assert radar_horizon_km(5, 100) == pytest.approx(50.4, abs=1)
    assert radar_horizon_km(5, 10000) > 400


def test_weather_blocks_lasers_but_not_gps_or_radar() -> None:
    env = OVERCAST_LOW
    assert env.laser_factor(7000) < 0.1
    assert env.laser_factor(500) == pytest.approx(1.0)
    night = CombatEnvironment(TimeOfDay.Night, 20, None, None, 0, False, False)
    assert night.tv_factor(5000) < 0.4
    assert night.ground_fire_factor(thermal_sights=True) > night.ground_fire_factor(
        False
    )


# --------------------------------------------------------------------- ledger


def test_partial_kill_and_revert() -> None:
    scenario = Scenario()
    flight = scenario.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.BARCAP,
        4,
        loadout(("AIM-120C", 2)),
        point(0, 0),
    )
    member = flight.roster.members[1]
    events = GameUpdateEvents()
    assert not scenario.results.kill_flight_member(flight, member, events)  # type: ignore[arg-type]
    assert flight.count == 3
    assert len(scenario.results.air_losses) == 1
    for m in list(flight.roster.members):
        scenario.results.kill_flight_member(flight, m, events)  # type: ignore[arg-type]
    assert isinstance(flight.state, Killed)

    scenario.results.revert(events)
    assert flight.count == 4
    assert flight.roster.members[1] is member
    assert not scenario.results.air_losses


def test_theater_unit_kill_is_reverted() -> None:
    scenario = Scenario()
    site = scenario.sam("SA-6", point(0, 0), [AD.Kub_1S91_str, AD.Kub_2P25_ln])
    radar = next(iter(site.units))
    events = GameUpdateEvents()
    assert scenario.results.kill_theater_unit(radar, events)
    assert not radar.alive
    scenario.results.revert(events)
    assert radar.alive


# --------------------------------------------------------------------- air


def _a2a(seed: int) -> Scenario:
    s = Scenario(seed)
    blue = s.flight(
        Player.BLUE,
        planes.F_15C,
        FlightType.BARCAP,
        4,
        loadout(("AIM-120C", 4), ("AIM-9M", 4)),
        point(0, 0),
    )
    red = s.flight(
        Player.RED,
        planes.MiG_21Bis,
        FlightType.BARCAP,
        4,
        loadout(("R-60M", 2)),
        point(80, 0),
        altitude_m=6000,
    )
    s.air_combat([blue, red])
    return s


def test_air_combat_is_reproducible_from_seed() -> None:
    first = [str(e) for e in _a2a(7).results.log]
    second = [str(e) for e in _a2a(7).results.log]
    assert first and first == second


def test_technology_and_awareness_decide_air_combat() -> None:
    blue = red = 0
    for seed in range(25):
        s = _a2a(seed)
        blue += s.losses(Player.BLUE)
        red += s.losses(Player.RED)
    assert red > 4 * max(blue, 1)


def test_missiles_are_expended() -> None:
    s = _a2a(3)
    flight = s.game.blue.ato.packages[0].flights[0]
    airframes = s.model.airframes(flight)  # type: ignore[arg-type]
    remaining: int = sum(
        st.remaining
        for a in airframes
        for st in a.a2a_stores()
        if st.profile.guidance is Guidance.ARH
    )
    assert remaining < 16


# --------------------------------------------------------------------- SAM


def _sa10_transit(seed: int, sead: bool) -> int:
    s = Scenario(seed)
    package = s.package(Player.BLUE)
    strikers = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        4,
        loadout(("Mk 84", 2)),
        point(0, 0),
        package=package,
        altitude_m=7000,
    )
    if sead:
        s.flight(
            Player.BLUE,
            planes.F_16C_50,
            FlightType.SEAD_ESCORT,
            2,
            loadout(("AGM-88C HARM", 2)),
            point(0, 5),
            package=package,
            altitude_m=7000,
        )
    site = s.sam(
        "SA-10",
        point(60, 0),
        [
            AD.S_300PS_40B6M_tr,
            AD.S_300PS_64H6E_sr,
            AD.S_300PS_5P85C_ln,
            AD.S_300PS_5P85C_ln,
        ],
        iads=True,
    )
    return s.sam_transit(strikers, [site], windows=3)


def test_sead_protects_the_package() -> None:
    without = sum(_sa10_transit(seed, sead=False) for seed in range(15))
    with_sead = sum(_sa10_transit(seed, sead=True) for seed in range(15))
    assert without > 2 * with_sead


def test_altitude_keeps_aircraft_out_of_manpads() -> None:
    high = low = 0
    for seed in range(15):
        for altitude in (300, 5000):
            s = Scenario(seed)
            flight = s.flight(
                Player.BLUE,
                planes.A_10C,
                FlightType.CAS,
                4,
                loadout(("Mk 82", 2)),
                point(0, 0),
                altitude_m=altitude,
                speed_kph=600,
            )
            site = s.sam(
                "MANPADS", point(2, 0), [AD.SA_18_Igla_manpad, AD.ZSU_23_4_Shilka]
            )
            lost = s.sam_transit(flight, [site], windows=2)
            if altitude == 300:
                low += lost
            else:
                high += lost
    assert high == 0
    assert low > 0


def test_sam_magazine_runs_dry() -> None:
    s = Scenario(1)
    site = s.sam("SA-6", point(15, 0), [AD.Kub_1S91_str, AD.Kub_2P25_ln])
    flight = s.flight(
        Player.BLUE,
        planes.B_52H,
        FlightType.STRIKE,
        4,
        loadout(("Mk 82", 2)),
        point(0, 0),
        altitude_m=6000,
        speed_kph=800,
    )
    s.sam_transit(flight, [site], windows=6)
    from game.sim.combat.model.airdefense import site_for

    launcher = site_for(s.model, site).launchers[0]  # type: ignore[arg-type]
    assert launcher.missiles < launcher.profile.missiles


# --------------------------------------------------------------------- strike


def _factory(seed: int, bomb: str, env: CombatEnvironment | None = None) -> int:
    s = Scenario(seed, env=env)
    target = s.target("Factory", point(50, 0), [Fortification.Barracks_2] * 6)
    package = s.package(Player.BLUE, target)
    flight = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        4,
        loadout((bomb, 2), ("AN/AAQ-28 LITENING", 1)),
        point(30, 0),
        package=package,
    )
    s.strike(flight)
    return len(s.results.ground_losses)


def test_lgb_needs_clear_line_of_sight_gps_does_not() -> None:
    clear = sum(_factory(seed, "GBU-12") for seed in range(10))
    cloudy = sum(_factory(seed, "GBU-12", OVERCAST_LOW) for seed in range(10))
    jdam_cloudy = sum(_factory(seed, "GBU-38", OVERCAST_LOW) for seed in range(10))
    assert clear > 3 * max(cloudy, 1)
    assert jdam_cloudy > 3 * max(cloudy, 1)


# --------------------------------------------------------------------- ground


def _front(
    seed: int,
    blue: int,
    red: int,
    blue_stance: CombatStance,
    red_stance: CombatStance,
    rounds: int = 6,
) -> FrontState:
    s = Scenario(seed)
    tank = next(GroundUnitType.for_dcs_type(vehicles.Armor.T_72B))

    def groups(n: int) -> list[CombatGroup]:
        return [CombatGroup(CombatGroupRole.TANK, tank, 4) for _ in range(n // 4)]

    base = SimpleNamespace(total_armor=100)
    war = GroundWar(s.model, timedelta(minutes=10))
    front = FrontState(
        SimpleNamespace(name="Front"),  # type: ignore[arg-type]
        SideState(SimpleNamespace(base=base, captured=Player.BLUE), blue_stance, groups(blue), blue),  # type: ignore[arg-type]
        SideState(SimpleNamespace(base=base, captured=Player.RED), red_stance, groups(red), red),  # type: ignore[arg-type]
        s.model.rng(),
    )
    for _ in range(rounds):
        war._round(front, s.time, 1.0)
    return front


def test_defender_advantage_and_force_ratio() -> None:
    even_attacker = even_defender = 0
    breaks = 0
    for seed in range(20):
        even = _front(seed, 20, 20, CombatStance.AGGRESSIVE, CombatStance.DEFENSIVE)
        even_attacker += even.blue.losses
        even_defender += even.red.losses
        overwhelming = _front(
            seed, 60, 20, CombatStance.AGGRESSIVE, CombatStance.DEFENSIVE
        )
        breaks += overwhelming.red.broken
    assert even_attacker > even_defender
    assert breaks > 10


def test_broken_defense_withdraws_instead_of_dying() -> None:
    """Even a hopeless defense falls back once broken; a turn shouldn't wipe
    out a whole front."""
    defender_losses = 0
    for seed in range(20):
        front = _front(
            seed, 60, 20, CombatStance.AGGRESSIVE, CombatStance.DEFENSIVE, rounds=10
        )
        assert front.red.losses < front.red.initial_strength
        defender_losses += front.red.losses
    assert defender_losses / (20 * 20) < 0.6


def test_ground_losses_are_recorded_as_front_line_casualties() -> None:
    front = _front(1, 40, 20, CombatStance.BREAKTHROUGH, CombatStance.DEFENSIVE)
    assert front.blue.losses + front.red.losses > 0


# --------------------------------------------------------------------- debrief


def test_simulation_results_merge_into_debriefing() -> None:
    s = Scenario(2)
    site = s.sam("SA-6", point(0, 0), [AD.Kub_1S91_str, AD.Kub_2P25_ln])
    radar = next(iter(site.units))
    s.results.kill_theater_unit(radar, GameUpdateEvents())
    s.results.damage_runway(s.red_cp)  # type: ignore[arg-type]
    debriefing = Debriefing.__new__(Debriefing)
    debriefing.air_losses = AirLosses([], [])
    debriefing.ground_losses = GroundLosses()
    debriefing.parked_aircraft_losses = []
    debriefing.merge_simulation_results(s.results)
    assert [m.theater_unit for m in debriefing.ground_losses.enemy_ground_objects] == [
        radar
    ]
    assert debriefing.ground_losses.enemy_airfields == [s.red_cp]


# --------------------------------------------------------------------- quality


@pytest.mark.parametrize(
    "faction,tier",
    [
        ("Bluefor Modern", "nato_tier1"),
        ("USA 2005", "nato_tier1"),
        ("USA 1970 Vietnam War", "western"),
        ("Iraq 1991", "client_state"),
        ("Iran 2015", "client_state"),
        ("Russia 2010", "peer"),
        ("Russia 1980", "soviet_coldwar"),
        ("Insurgents", "irregular"),
    ],
)
def test_faction_force_quality(faction: str, tier: str) -> None:
    from game.sim.combat.model.forcequality import for_faction

    assert for_faction(faction).tier == tier


def _iraqi_sam_pk(blue: str, red: str) -> float:
    shots = kills = 0
    for seed in range(40):
        s = Scenario(seed, blue=blue, red=red)
        s.ewr("EWR", point(60, 30))
        site = s.sam(
            "SA-6",
            point(15, 0),
            [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln],
            iads=True,
        )
        flight = s.flight(
            Player.BLUE,
            planes.F_16C_50,
            FlightType.STRIKE,
            4,
            loadout(("Mk 84", 2), ("AN/ALQ-131 ECM", 1)),
            point(0, 0),
            altitude_m=6000,
        )
        s.sam_transit(flight, [site], windows=4)
        shots += s.model.shot_stats["sam"][0]
        kills += s.model.shot_stats["sam"][1]
    assert shots > 0
    return kills / shots


def test_combat_pk_is_far_below_test_pk() -> None:
    # Historically a few percent per missile at most against NATO jets.
    assert _iraqi_sam_pk("NATO Desert Storm", "Iraq 1991") < 0.05


def test_force_quality_matters() -> None:
    nato_vs_iraq = _iraqi_sam_pk("NATO Desert Storm", "Iraq 1991")
    peers = _iraqi_sam_pk("Russia 2010", "Russia 2010")
    assert peers > nato_vs_iraq


def test_force_quality_can_be_disabled() -> None:
    from game.settings import Settings

    settings = Settings()
    settings.combat_model_force_quality = False
    s = Scenario(1, settings=settings, blue="NATO Desert Storm", red="Iraq 1991")
    assert s.model.quality(Player.BLUE).tier == "neutral"
    assert s.model.quality(Player.RED).tier == "neutral"


def test_warned_fighters_outrun_long_shots() -> None:
    from game.sim.combat.model.airtoair import AirEngagement, MissileInFlight

    s = Scenario(5)
    shooter = s.flight(
        Player.RED,
        planes.F_14B,
        FlightType.BARCAP,
        1,
        loadout(("AIM-54C-MK60", 4)),
        point(0, 0),
    )
    target = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.BARCAP,
        1,
        loadout(("AIM-120C", 2)),
        point(140, 0),
    )
    engagement = AirEngagement.create(s.model, [shooter, target], s.time)  # type: ignore[list-item]
    a = s.model.airframes(shooter)[0]  # type: ignore[arg-type]
    t = s.model.airframes(target)[0]  # type: ignore[arg-type]
    phoenix = a.stores[0].profile
    hits_long = hits_short = 0
    for _ in range(300):
        t.alive, t.damaged = True, False
        t.chaff = t.flares = 100
        engagement.missiles = [MissileInFlight(a, t, phoenix, 0, 0.6, True, 140, 150)]
        engagement._resolve_missiles(s.time, s.events)
        hits_long += not t.alive
        t.alive, t.damaged = True, False
        engagement.missiles = [MissileInFlight(a, t, phoenix, 0, 0.6, True, 30, 150)]
        engagement._resolve_missiles(s.time, s.events)
        hits_short += not t.alive
    assert hits_long * 3 < hits_short


def _front_attack(seed: int, monkeypatch: Any) -> tuple[int, int]:
    """An A-10C pair with four APKWS pods each over a dispersed vehicle target scored
    as the front line: (rounds released, rounds brought home)."""
    from game.sim.combat.model import attack

    monkeypatch.setattr(attack.AttackRun, "_is_front_line", lambda self: True)
    monkeypatch.setattr(
        attack.AttackRun, "_front_line_flak", lambda self, airframes: airframes
    )
    s = Scenario(seed)
    target = s.target("Column", point(20, 0), [vehicles.Unarmed.Ural_375] * 40)
    package = s.package(Player.BLUE, target)
    flight = s.flight(
        Player.BLUE,
        planes.A_10C,
        FlightType.CAS,
        2,
        loadout(("LAU-131 7xMPP APKWS", 4)),
        point(0, 0),
        package=package,
    )
    report = s.strike(flight)
    left = sum(
        store.remaining
        for airframe in s.model.airframes(flight)  # type: ignore[arg-type]
        for store in airframe.a2g_stores((WeaponRole.A2G,))
    )
    return report.released, left


def test_cas_over_the_front_makes_a_few_passes_and_brings_the_rest_home(
    monkeypatch: Any,
) -> None:
    from game.sim.combat.model.attack import FRONT_LINE_PASSES

    released, left = _front_attack(1, monkeypatch)
    assert released == 2 * FRONT_LINE_PASSES
    assert left > 0
