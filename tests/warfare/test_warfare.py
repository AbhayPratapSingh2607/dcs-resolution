"""Tests for campaign warfare systems: IADS, EW, intelligence, morale, doctrine."""

from __future__ import annotations

import logging
import pickle
import random
from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from dcs import planes, vehicles

from game.ato.flighttype import FlightType
from game.dcs.groundunittype import GroundUnitType
from game.ground_forces.ai_ground_planner import CombatGroup, CombatGroupRole
from game.ground_forces.combat_stance import CombatStance
from game.settings.settings import FogOfWar
from game.sim.combat.model.groundbattle import FrontState, GroundWar, SideState
from game.sim.combat.model.scenario import Scenario, loadout, point
from game.theater.iadsnetwork.iadsrole import IadsRole
from game.theater.player import Player
from game.warfare import WarState
from game.warfare.doctrine import for_faction_name
from game.warfare.iads import dependency_targets, site_status
from game.warfare.intel import CONFIRMED, IntelPicture, IntelSource
from game.warfare.morale import MIN_RESOLVE, MoraleState, describe, performance_factor

AD = vehicles.AirDefence


@pytest.fixture(autouse=True)
def quiet() -> Any:
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


# --------------------------------------------------------------------- doctrine


@pytest.mark.parametrize(
    "faction,doctrine",
    [
        ("Bluefor Modern", "western"),
        ("Iraq 1991", "client"),
        ("Russia 2010", "russian_modern"),
        ("Russia 1980", "soviet"),
        ("Insurgents", "irregular"),
    ],
)
def test_doctrine_by_faction(faction: str, doctrine: str) -> None:
    assert for_faction_name(faction).name == doctrine


def test_ww2_factions_use_ww2_doctrine() -> None:
    assert for_faction_name("Germany 1944", "ww2").name == "ww2"


def test_western_doctrine_rolls_back_iads() -> None:
    western = for_faction_name("USA 2005")
    assert western.iads_rollback_first and western.decapitation
    assert not for_faction_name("Iraq 1991").iads_rollback_first


# --------------------------------------------------------------------- IADS


def _group(tgo: Any, role: IadsRole, alive: bool) -> Any:
    return SimpleNamespace(
        ground_object=tgo, iads_role=role, units=[SimpleNamespace(alive=alive)]
    )


def _network_game(alive: dict[IadsRole, bool]) -> tuple[Any, Any, dict[IadsRole, Any]]:
    cp = SimpleNamespace(captured=Player.RED)
    sam = SimpleNamespace(control_point=cp, name="SAM")
    nodes_tgos = {
        role: SimpleNamespace(control_point=cp, name=role.value) for role in alive
    }
    connections = {
        i: _group(nodes_tgos[role], role, ok)
        for i, (role, ok) in enumerate(alive.items())
    }
    node = SimpleNamespace(
        group=SimpleNamespace(ground_object=sam), connections=connections
    )
    network = SimpleNamespace(advanced_iads=True, nodes=[node])
    game = SimpleNamespace(theater=SimpleNamespace(iads_network=network))
    return game, sam, nodes_tgos


def test_iads_site_fully_connected() -> None:
    game, sam, _ = _network_game(
        {
            IadsRole.EWR: True,
            IadsRole.COMMAND_CENTER: True,
            IadsRole.CONNECTION_NODE: True,
            IadsRole.POWER_SOURCE: True,
        }
    )
    status = site_status(cast(Any, game), cast(Any, sam))
    assert status is not None and status.networked and status.has_power


def test_iads_decapitation_cuts_the_site_off() -> None:
    game, sam, _ = _network_game(
        {
            IadsRole.EWR: True,
            IadsRole.COMMAND_CENTER: False,
            IadsRole.POWER_SOURCE: False,
        }
    )
    status = site_status(cast(Any, game), cast(Any, sam))
    assert status is not None
    assert status.has_ew_cue and not status.has_c2 and not status.networked
    assert not status.has_power


def test_iads_basic_mode_has_no_dependencies() -> None:
    game, sam, _ = _network_game({IadsRole.EWR: True})
    game.theater.iads_network.advanced_iads = False
    assert site_status(cast(Any, game), cast(Any, sam)) is None


def test_decapitation_targets_command_centres_first() -> None:
    game, sam, tgos = _network_game(
        {IadsRole.POWER_SOURCE: True, IadsRole.COMMAND_CENTER: True}
    )
    targets = dependency_targets(cast(Any, game), [cast(Any, sam)])
    assert targets[0] is tgos[IadsRole.COMMAND_CENTER]


# --------------------------------------------------------------------- intel


def _site() -> Any:
    s = Scenario(1)
    return s.sam(
        "SA-6", point(10, 0), [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln]
    )


def test_observations_build_confidence() -> None:
    tgo = _site()
    picture = IntelPicture(isr=0.8)
    rng = random.Random(1)
    assert not picture.knows(tgo)
    picture.observe(tgo, 0.3, IntelSource.ELINT, 1, rng)
    assert not picture.knows(tgo)
    picture.observe(tgo, 0.3, IntelSource.VISUAL, 1, rng)
    assert picture.knows(tgo)
    assert not picture.confirmed(tgo)
    picture.observe(tgo, 0.95, IntelSource.RECON, 1, rng)
    assert picture.confirmed(tgo)
    assert picture.error_m(tgo) <= 1000


def test_estimated_position_is_within_the_error() -> None:
    tgo = _site()
    picture = IntelPicture()
    picture.observe(tgo, 0.6, IntelSource.ELINT, 1, random.Random(3))
    error = picture.error_m(tgo)
    offset = picture.estimated_position(tgo).distance_to_point(tgo.position)
    assert offset <= error + 1


def test_mobile_contacts_go_stale() -> None:
    tgo = _site()
    tgo.task = SimpleNamespace(description="MERAD")
    picture = IntelPicture()
    picture.observe(tgo, 0.6, IntelSource.ENGAGEMENT, 1, random.Random(1))
    before = picture.contact(tgo)
    assert before is not None
    confidence = before.confidence

    class _Game:
        theater = SimpleNamespace(controlpoints=[SimpleNamespace(ground_objects=[tgo])])

    game = _Game()
    for turn in range(2, 6):
        picture.decay(cast(Any, game), turn)
    assert picture.contact(tgo).confidence < confidence * 0.5  # type: ignore[union-attr]


def test_battle_damage_assessment_can_be_wrong() -> None:
    tgo = _site()
    picture = IntelPicture(isr=0.5)
    rng = random.Random(7)
    unit = next(iter(tgo.units))
    unit.alive = False
    misses = 0
    for _ in range(200):
        picture.contacts.clear()
        picture.report_kill(tgo, unit.id, 0.7, rng)
        contact = picture.contact(tgo)
        misses += contact is not None and unit.id not in contact.believed_dead
    assert 30 < misses < 90  # Roughly 30% of kills go unreported.
    # Recon settles it.
    picture.observe(tgo, 0.95, IntelSource.RECON, 2, rng)
    assert unit.id in picture.contact(tgo).believed_dead  # type: ignore[union-attr]


def test_overclaims() -> None:
    tgo = _site()
    picture = IntelPicture()
    picture.overclaim(tgo, 1.0, random.Random(1))
    assert not picture.believed_alive(tgo)
    assert not tgo.is_dead


# --------------------------------------------------------------------- morale


def test_morale_performance_and_recovery() -> None:
    assert performance_factor(0.75) == pytest.approx(1.0)
    assert performance_factor(0.0) < 0.9
    assert performance_factor(1.0) > 1.0
    assert MoraleState.recover(0.2, 0.75, 0.1) == pytest.approx(0.3)
    assert MoraleState.recover(0.9, 0.75, 0.1) == pytest.approx(0.85)
    assert describe(0.2) == "broken" and describe(0.9) == "excellent"


def test_resolve_never_collapses_completely() -> None:
    morale = MoraleState()
    for _ in range(50):
        morale.adjust_resolve(Player.RED, -0.2)
    assert morale.national_resolve(Player.RED) == pytest.approx(MIN_RESOLVE)
    # War-weariness lowers every baseline.
    assert morale.baseline(0.8, Player.RED) < morale.baseline(0.8, Player.BLUE)


def test_war_state_pickles() -> None:
    state = WarState()
    state.morale.adjust_resolve(Player.BLUE, -0.3)
    restored = pickle.loads(pickle.dumps(state))
    assert restored.morale.national_resolve(Player.BLUE) == pytest.approx(0.7)


# --------------------------------------------------------------------- fog of war


class _FogGame:
    def __init__(self, mode: FogOfWar, picture: IntelPicture) -> None:
        self.settings = SimpleNamespace(fog_of_war=mode, intel_enabled=True)
        self._picture = picture
        self.war_state = SimpleNamespace(
            intel_enabled=lambda game: True,
            picture=lambda game, viewer: self._picture,
        )


def test_fog_of_war_strict_and_soft() -> None:
    from game.server.fogofwar import tgo_view

    tgo = _site()
    picture = IntelPicture()
    strict = cast(Any, _FogGame(FogOfWar.STRICT, picture))
    soft = cast(Any, _FogGame(FogOfWar.SOFT, picture))
    off = cast(Any, _FogGame(FogOfWar.OFF, picture))
    assert tgo_view(strict, tgo) is None
    view = tgo_view(soft, tgo)
    assert view is not None and not view.known and not view.confirmed
    full = tgo_view(off, tgo)
    assert full is not None and full.confirmed
    picture.observe(tgo, 0.6, IntelSource.ELINT, 1, random.Random(1))
    estimated = tgo_view(strict, tgo)
    assert estimated is not None and estimated.known and not estimated.confirmed
    assert estimated.uncertainty_m > 0


def test_detection_summary_names_the_source() -> None:
    from game.server.fogofwar import detection_summary

    tgo = _site()
    picture = IntelPicture()
    strict = cast(Any, _FogGame(FogOfWar.STRICT, picture))
    off = cast(Any, _FogGame(FogOfWar.OFF, picture))
    assert detection_summary(strict, tgo) == "Not detected"
    assert detection_summary(off, tgo) is None
    picture.observe(tgo, 0.5, IntelSource.PREWAR, 0, random.Random(1))
    assert detection_summary(strict, tgo) == (
        "Known from pre-war intelligence, confidence 50%"
    )
    picture.observe(tgo, 0.9, IntelSource.SATELLITE, 2, random.Random(1))
    assert detection_summary(strict, tgo) == (
        "Detected via satellite imagery, turn 2, confidence 95%"
    )


# --------------------------------------------------------------------- recon


def test_recon_capable_aircraft() -> None:
    from game.dcs.aircrafttype import AircraftType

    Scenario(1)  # Headless setup for unit data.
    reaper = next(AircraftType.for_dcs_type(planes.MQ_9_Reaper))
    assert reaper.capable_of(FlightType.RECON)
    assert reaper.task_priority(FlightType.RECON) >= 600
    from dcs import helicopters

    chinook = next(AircraftType.for_dcs_type(helicopters.CH_47D))
    assert (
        not chinook.capable_of(FlightType.RECON)
        or chinook.task_priority(FlightType.RECON) < 300
    )


# --------------------------------------------------------------------- combat effects


class _Morale:
    def __init__(self, value: float) -> None:
        self.value = value

    def squadron(self, squadron: Any) -> float:
        return self.value

    def front(self, cp: Any) -> float:
        return self.value

    def sam_crew(self, tgo: Any) -> float:
        return self.value


def _sa6_shots(decoys: bool, seed: int) -> tuple[int, int]:
    s = Scenario(seed, blue="NATO Desert Storm", red="Iraq 1991")
    site = s.sam(
        "SA-6", point(15, 0), [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln]
    )
    package = s.package(Player.BLUE)
    weapons = [("Mk 84", 2)]
    if decoys:
        weapons.append(("ADM-141A TALD", 2))
    flight = s.flight(
        Player.BLUE,
        planes.FA_18C_hornet,
        FlightType.STRIKE,
        4,
        loadout(*weapons),
        point(0, 0),
        package=package,
        altitude_m=6000,
    )
    s.sam_transit(flight, [site], windows=2)
    from game.sim.combat.model.airdefense import site_for

    state = site_for(s.model, cast(Any, site))
    return state.shots, sum(l.missiles for l in state.launchers)


def test_decoys_draw_sam_fire() -> None:
    plain = sum(_sa6_shots(False, seed)[0] for seed in range(20))
    with_decoys = sum(_sa6_shots(True, seed)[0] for seed in range(20))
    assert with_decoys > plain


def test_unknown_sites_get_surprise() -> None:
    def losses(known: bool) -> int:
        total = 0
        for seed in range(60):
            # A doctrine without SAM ambushes, so surprise comes only from intel.
            s = Scenario(seed, blue="NATO Desert Storm", red="Greece 2005")
            s.game.war_state = SimpleNamespace(  # type: ignore[attr-defined]
                knows=lambda game, viewer, tgo, k=known: k
            )
            site = s.sam(
                "SA-11", point(20, 0), [AD.SA_11_Buk_LN_9A310M1, AD.SA_11_Buk_SR_9S18M1]
            )
            flight = s.flight(
                Player.BLUE,
                planes.F_16C_50,
                FlightType.STRIKE,
                4,
                loadout(("Mk 84", 2)),
                point(0, 0),
                altitude_m=6000,
            )
            total += s.sam_transit(flight, [site], windows=3)
        return total

    assert losses(known=False) > losses(known=True)


def test_low_morale_makes_flights_give_up_sooner() -> None:
    def factor(morale: float, faction: str = "") -> float:
        s = Scenario(1, red=faction)
        s.game.war_state = SimpleNamespace(morale=_Morale(morale))  # type: ignore[attr-defined]
        flight = s.flight(
            Player.RED,
            planes.MiG_29S,
            FlightType.STRIKE,
            2,
            loadout(("Mk 84", 2)),
            point(0, 0),
        )
        return s.model.abort_factor(cast(Any, flight))

    assert factor(0.2) > factor(0.75) > factor(0.95)
    # Doctrine: client-state aircrews break off more readily.
    assert factor(0.75, "Iraq 1991") > factor(0.75, "Russia 2010")


def test_low_morale_lowers_skill() -> None:
    def skill(morale: float) -> float:
        s = Scenario(1)
        s.game.war_state = SimpleNamespace(morale=_Morale(morale))  # type: ignore[attr-defined]
        flight = s.flight(
            Player.BLUE,
            planes.F_16C_50,
            FlightType.BARCAP,
            2,
            loadout(("AIM-120C", 2)),
            point(0, 0),
        )
        return s.model.airframes(cast(Any, flight))[0].skill

    assert skill(0.2) < skill(0.75) < skill(1.0)


def test_combined_arms_and_unsupported_armor() -> None:
    s = Scenario(1)
    tank = next(GroundUnitType.for_dcs_type(vehicles.Armor.T_72B))
    ifv = next(GroundUnitType.for_dcs_type(vehicles.Armor.BMP_2))
    art = next(GroundUnitType.for_dcs_type(vehicles.Artillery.SAU_Gvozdika))
    base = SimpleNamespace(total_armor=100)

    def side(groups: list[CombatGroup], player: Player) -> SideState:
        return SideState(
            cast(Any, SimpleNamespace(base=base, captured=player)),
            CombatStance.AGGRESSIVE,
            groups,
            sum(g.size for g in groups),
        )

    war = GroundWar(s.model, timedelta(minutes=10))
    mixed = side(
        [
            CombatGroup(CombatGroupRole.TANK, tank, 8),
            CombatGroup(CombatGroupRole.IFV, ifv, 8),
            CombatGroup(CombatGroupRole.ARTILLERY, art, 4),
        ],
        Player.BLUE,
    )
    pure = side([CombatGroup(CombatGroupRole.TANK, tank, 20)], Player.BLUE)
    infantry_heavy = side(
        [
            CombatGroup(CombatGroupRole.TANK, tank, 4),
            CombatGroup(CombatGroupRole.IFV, ifv, 16),
        ],
        Player.RED,
    )
    mixed_direct, mixed_indirect = war._tactics(mixed, infantry_heavy, True)
    pure_direct, _ = war._tactics(pure, infantry_heavy, True)
    assert mixed_direct > 1.0 > pure_direct
    # Artillery preparation before the assault.
    assert mixed_indirect > 1.0


def test_intel_report_lists_known_sites_and_resolve() -> None:
    from game.warfare.intel_report import build_intel_report
    from game.warfare.intel import PhantomContact
    from game.warfare.morale import MoraleState
    from uuid import uuid4

    tgo = _site()
    cp = tgo.control_point
    picture = IntelPicture()
    morale = MoraleState()
    morale.adjust_resolve(Player.RED, -0.6)
    game = cast(
        Any,
        SimpleNamespace(
            settings=SimpleNamespace(
                fog_of_war=FogOfWar.STRICT,
                war_weariness_enabled=True,
                space_and_agency_intel=False,
            ),
            war_state=SimpleNamespace(
                intel_enabled=lambda game: True,
                morale_enabled=lambda game: True,
                picture=lambda game, viewer: picture,
                morale=morale,
                collateral_incidents={True: 2},
            ),
            theater=SimpleNamespace(
                conflicts=lambda: [],
                control_points_for=lambda player: [cp] if player.is_red else [],
            ),
        ),
    )
    report = build_intel_report(game)
    assert report.own_resolve == "excellent" and report.enemy_resolve == "~shaken"
    assert report.collateral_incidents == 2
    assert report.contacts == []  # Nothing detected yet.

    picture.observe(tgo, 0.5, IntelSource.ELINT, 1, random.Random(1))
    picture.phantoms[uuid4()] = PhantomContact(
        uuid4(), cp.position.x, cp.position.y, 0.6, 5000, 2
    )
    report = build_intel_report(game)
    assert [c.source for c in report.contacts] == ["agency report", "ELINT"]
    real = report.contacts[1]
    assert real.status == "unconfirmed" and real.kind == "unknown"
    assert real.position_error.startswith("~")

    picture.observe(tgo, 0.99, IntelSource.RECON, 3, random.Random(1))
    real = build_intel_report(game).contacts[0]
    assert (real.status, real.position_error) == ("confirmed", "exact")
    assert real.kind != "unknown"
