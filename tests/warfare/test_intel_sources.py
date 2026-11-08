"""Satellites, agencies, deception and collateral damage."""

from __future__ import annotations

import logging
import pickle
import random
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest
from dcs import planes, vehicles
from dcs.statics import Fortification

from game.ato.flighttype import FlightType
from game.sim.combat.model.environment import CombatEnvironment
from game.sim.combat.model.scenario import Scenario, loadout, point
from game.theater.player import Player
from game.timeofday import TimeOfDay
from game.warfare import WarState
from game.warfare.agencies import reliability, run_agencies
from game.warfare.collateral import built_up_fraction, risk_at
from game.warfare.intel import Contact, IntelPicture, IntelSource
from game.warfare.satellites import run_satellites

AD = vehicles.AirDefence
OVERCAST = CombatEnvironment(TimeOfDay.Day, 15, 800, 2500, 1.0, False, False)
NIGHT = CombatEnvironment(TimeOfDay.Night, 15, None, None, 0.0, False, False)
CLEAR = CombatEnvironment.clear_day()


@pytest.fixture(autouse=True)
def quiet() -> Any:
    logging.disable(logging.WARNING)
    yield
    logging.disable(logging.NOTSET)


def _world(
    blue: str, red: str, mobile: bool = False, seed: int = 1
) -> tuple[Scenario, WarState, Any]:
    s = Scenario(seed, blue=blue, red=red)
    war_state = WarState()
    war_state.intel[True] = IntelPicture(isr=0.9, initialized=True)
    war_state.intel[False] = IntelPicture(isr=0.4, initialized=True)
    s.game.war_state = war_state  # type: ignore[attr-defined]
    site = s.sam("SA-6", point(110, 10), [AD.Kub_1S91_str, AD.Kub_2P25_ln])
    if mobile:
        site.task = cast(Any, SimpleNamespace(description="MERAD"))
    return s, war_state, site


# --------------------------------------------------------------------- satellites


def _imaged(
    env: CombatEnvironment,
    blue: str = "Bluefor Modern",
    red: str = "Iraq 1991",
    mobile: bool = False,
    runs: int = 40,
) -> int:
    found = 0
    for seed in range(runs):
        s, war_state, site = _world(blue, red, mobile, seed)
        run_satellites(
            cast(Any, s.game), war_state, Player.BLUE, random.Random(seed), env
        )
        found += war_state.intel[True].knows(site)
    return found


def test_optical_needs_daylight_and_clear_skies() -> None:
    clear = _imaged(CLEAR)
    overcast = _imaged(OVERCAST)
    night = _imaged(NIGHT)
    # Blue has SAR passes too, so bad weather degrades rather than blinds.
    assert clear > overcast and clear > night
    assert overcast > 0 and night > 0


def test_no_space_programme_no_imagery() -> None:
    assert _imaged(CLEAR, blue="Iraq 1991", red="Bluefor Modern") == 0


def test_camouflage_and_deception_hide_mobile_units() -> None:
    fixed = _imaged(CLEAR, red="Russia 1980", runs=60)
    mobile_deceptive = _imaged(CLEAR, red="Russia 1980", mobile=True, runs=60)
    mobile_open = _imaged(CLEAR, red="Greece 2005", mobile=True, runs=60)
    assert fixed > mobile_open > mobile_deceptive


# --------------------------------------------------------------------- agencies


def test_counterintelligence_lowers_reliability() -> None:
    s, war_state, _ = _world("Bluefor Modern", "Iraq 1991")
    against_iraq = reliability(cast(Any, s.game), war_state, Player.BLUE, "humint")
    s2, war_state2, _ = _world("Bluefor Modern", "Russia 1980")
    against_soviets = reliability(cast(Any, s2.game), war_state2, Player.BLUE, "humint")
    assert against_iraq > against_soviets


def test_agencies_produce_true_and_false_reports() -> None:
    true_tips = false_tips = 0
    for seed in range(60):
        s, war_state, _ = _world("Iraq 1991", "Bluefor Modern", seed=seed)
        # Iraq's agencies looking at blue: weak, against strong counterintel.
        for _ in range(3):
            s.sam(
                "Hawk", point(-40, 5 * _), [AD.Hawk_ln, AD.Hawk_tr], player=Player.BLUE
            )
        report = run_agencies(
            cast(Any, s.game), war_state, Player.RED, random.Random(seed)
        )
        true_tips += report.tips_true
        false_tips += report.tips_false
    assert true_tips > 0 and false_tips > 0
    assert false_tips > true_tips * 0.5  # A poor agency is often wrong.


def test_phantoms_fade_and_clear() -> None:
    picture = IntelPicture()
    rng = random.Random(1)
    phantom = picture.add_phantom(1000, 1000, 1, rng)
    assert picture.clear_phantoms_near(0, 0, 5000, 1.0, rng) == 1
    picture.add_phantom(1000, 1000, 1, rng)
    game = SimpleNamespace(theater=SimpleNamespace(controlpoints=[]))
    picture.decay(cast(Any, game), 5)
    assert not picture.phantoms
    assert phantom.kind == "SAM"


# --------------------------------------------------------------------- deception


def test_strike_on_a_decoy_spares_the_real_site() -> None:
    s, war_state, _ = _world("Bluefor Modern", "Russia 1980")
    target = s.target("SA-8", point(40, 0), [AD.Osa_9A33_ln, AD.Osa_9A33_ln])
    war_state.deception[target.id] = [(3000.0, 0.0)]
    picture = war_state.intel[True]
    picture.latch_decoy(cast(Any, target), 0, (3000.0, 0.0))
    package = s.package(Player.BLUE, target)
    flight = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.DEAD,
        2,
        loadout(("Mk 82", 4)),
        point(30, 0),
        package=package,
    )
    report = s.strike(flight)
    assert report.released > 0
    assert all(u.alive for u in target.units)
    assert war_state.deception[target.id] == []
    contact = picture.contact(cast(Any, target))
    assert contact is not None and contact.decoy_index is None


def test_recon_sees_through_decoys() -> None:
    from game.warfare.deception import maybe_fooled

    exposed = 0
    for seed in range(40):
        s, war_state, site = _world("Bluefor Modern", "Russia 1980", seed=seed)
        picture = war_state.intel[True]
        war_state.deception[site.id] = [(2000.0, 0.0)]
        picture.latch_decoy(site, 0, (2000.0, 0.0))
        maybe_fooled(
            cast(Any, s.game),
            war_state,
            picture,
            site,
            IntelSource.RECON,
            random.Random(seed),
        )
        exposed += picture.contact(site).decoy_index is None  # type: ignore[union-attr]
    assert exposed > 20


# --------------------------------------------------------------------- collateral


class _Terrain:
    """A 20 x 20 km grid, built up in the northern half."""

    origin_x = 0.0
    origin_y = 0.0
    cell = 200.0

    def __init__(self) -> None:
        self.built_up = np.zeros((100, 100), dtype=bool)
        self.built_up[50:, :] = True

    @property
    def shape(self) -> tuple[int, int]:
        return self.built_up.shape  # type: ignore[return-value]


def _game_with_terrain() -> Any:
    return SimpleNamespace(
        theater=SimpleNamespace(farp_terrain=_Terrain(), controlpoints=[]),
        settings=SimpleNamespace(collateral_damage_enabled=True),
    )


def test_collateral_risk_follows_built_up_area() -> None:
    game = _game_with_terrain()
    town = point(15, 10)
    country = point(3, 10)
    assert built_up_fraction(game, town) == pytest.approx(1.0)
    assert risk_at(game, town) > 0.9
    assert risk_at(game, country) == pytest.approx(0.0)


def _incidents(bomb: str, x_km: float) -> int:
    total = 0
    for seed in range(30):
        s = Scenario(seed)
        s.game.theater.farp_terrain = _Terrain()  # type: ignore[attr-defined]
        s.game.theater.controlpoints = []  # type: ignore[attr-defined]
        target = s.target("Factory", point(x_km, 10), [Fortification.Barracks_2] * 4)
        package = s.package(Player.BLUE, target)
        weapons = [(bomb, 2)]
        if bomb == "GBU-12":
            weapons.append(("AN/AAQ-28 LITENING", 1))
        flight = s.flight(
            Player.BLUE,
            planes.F_16C_50,
            FlightType.STRIKE,
            4,
            loadout(*weapons),
            point(x_km - 20, 10),
            package=package,
        )
        s.strike(flight)
        total += len(s.results.collateral_events)
    return total


def test_collateral_incidents_depend_on_place_and_weapon() -> None:
    in_town_dumb = _incidents("Mk 82", 15)
    in_town_precise = _incidents("GBU-12", 15)
    in_country_dumb = _incidents("Mk 82", 3)
    assert in_town_dumb > in_town_precise
    assert in_town_dumb > in_country_dumb == 0


# --------------------------------------------------------------------- saves


def test_old_pickles_get_new_defaults() -> None:
    contact = Contact(tgo_id=cast(Any, "x"))
    state = dict(contact.__dict__)
    del state["decoy_index"]
    restored = Contact.__new__(Contact)
    restored.__setstate__(state)
    assert restored.decoy_index is None

    picture = IntelPicture()
    state = dict(picture.__dict__)
    del state["phantoms"]
    del state["airbase_quality"]
    restored_picture = IntelPicture.__new__(IntelPicture)
    restored_picture.__setstate__(state)
    assert restored_picture.phantoms == {}

    war_state = WarState()
    blob = pickle.dumps(war_state)
    assert pickle.loads(blob).deception == {}
