"""Monte Carlo calibration of the fast-forward combat model.

Runs a set of reference scenarios many times with different seeds and prints
average outcomes next to the band we expect from history and doctrine. Use it
after changing combat data or model constants:

    .venv/Scripts/python resources/tools/combat_calibration.py [runs]
"""

from __future__ import annotations

import logging
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, cast

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dcs import planes, vehicles  # noqa: E402
from dcs.unit import Skill  # noqa: E402

from datetime import timedelta  # noqa: E402

from dcs.statics import Fortification  # noqa: E402

from game.ato.flighttype import FlightType  # noqa: E402
from game.ground_forces.combat_stance import CombatStance  # noqa: E402
from game.sim.combat.model.environment import CombatEnvironment  # noqa: E402
from game.sim.combat.model.scenario import Scenario, loadout, point  # noqa: E402
from game.theater.player import Player  # noqa: E402
from game.timeofday import TimeOfDay  # noqa: E402

AD = vehicles.AirDefence


@dataclass
class Outcome:
    blue_losses: float
    red_losses: float
    extra: float = 0.0
    #: Blue sorties exposed, for loss rate per sortie.
    sorties: int = 0
    #: SAM missiles fired / that killed (for per-missile Pk).
    sam_shots: int = 0
    sam_kills: int = 0
    #: Air-to-air missiles fired / that hit.
    a2a_shots: int = 0
    a2a_hits: int = 0


def _with_stats(s: Scenario, outcome: Outcome, sorties: int) -> Outcome:
    stats = s.model.shot_stats
    outcome.sorties = sorties
    outcome.sam_shots, outcome.sam_kills = stats["sam"]
    # Blue's missiles: the historical figures are for coalition launches.
    outcome.a2a_shots, outcome.a2a_hits = stats["a2a:blue"]
    return outcome


@dataclass
class Summary:
    blue: float
    red: float
    extra: float
    loss_per_sortie: float
    sam_pk: float
    a2a_pk: float

    def describe(self) -> str:
        parts = [f"blue {self.blue:4.2f}", f"red {self.red:4.2f}"]
        if self.loss_per_sortie >= 0:
            parts.append(f"loss/sortie {self.loss_per_sortie:6.2%}")
        if self.sam_pk >= 0:
            parts.append(f"SAM Pk/missile {self.sam_pk:6.2%}")
        if self.a2a_pk >= 0:
            parts.append(f"AAM Pk {self.a2a_pk:5.1%}")
        return "  ".join(parts)


@dataclass
class HistoricalCheck:
    name: str
    run: Callable[[int], Outcome]
    record: str
    passes: Callable[[Summary], bool]


def summarize(outcomes: list[Outcome]) -> Summary:
    sorties = sum(o.sorties for o in outcomes)
    sam_shots = sum(o.sam_shots for o in outcomes)
    a2a_shots = sum(o.a2a_shots for o in outcomes)
    blue_total = sum(o.blue_losses for o in outcomes)
    return Summary(
        blue=statistics.mean(o.blue_losses for o in outcomes),
        red=statistics.mean(o.red_losses for o in outcomes),
        extra=statistics.mean(o.extra for o in outcomes),
        loss_per_sortie=blue_total / sorties if sorties else -1,
        sam_pk=sum(o.sam_kills for o in outcomes) / sam_shots if sam_shots else -1,
        a2a_pk=sum(o.a2a_hits for o in outcomes) / a2a_shots if a2a_shots else -1,
    )


@dataclass
class Check:
    name: str
    run: Callable[[int], Outcome]
    expectation: str
    passes: Callable[[float, float, float], bool]


def eagles_vs_fishbeds(seed: int) -> Outcome:
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
        loadout(("R-60M", 2), ("R-13M - AAM, IR guided", 2)),
        point(80, 0),
        altitude_m=6000,
    )
    s.air_combat([blue, red])
    return Outcome(s.losses(Player.BLUE), s.losses(Player.RED))


def vipers_mirror(seed: int) -> Outcome:
    s = Scenario(seed)
    weapons = loadout(("AIM-120C", 4), ("AIM-9X", 2))
    blue = s.flight(
        Player.BLUE, planes.F_16C_50, FlightType.BARCAP, 4, weapons, point(0, 0)
    )
    red = s.flight(
        Player.RED, planes.F_16C_50, FlightType.BARCAP, 4, weapons, point(90, 0)
    )
    s.air_combat([blue, red])
    return Outcome(s.losses(Player.BLUE), s.losses(Player.RED))


def flankers_vs_eagles_sparrows(seed: int) -> Outcome:
    s = Scenario(seed)
    blue = s.flight(
        Player.BLUE,
        planes.F_15C,
        FlightType.BARCAP,
        4,
        loadout(("AIM-7M", 4), ("AIM-9M", 4)),
        point(0, 0),
    )
    red = s.flight(
        Player.RED,
        planes.Su_27,
        FlightType.BARCAP,
        4,
        loadout(("R-27ER", 4), ("R-73 (AA-11 Archer) - Infra Red", 2)),
        point(90, 0),
    )
    s.air_combat([blue, red])
    return Outcome(s.losses(Player.BLUE), s.losses(Player.RED))


def skill_gap(seed: int) -> Outcome:
    s = Scenario(seed)
    weapons = loadout(("AIM-120C", 4), ("AIM-9M", 2))
    blue = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.BARCAP,
        4,
        weapons,
        point(0, 0),
        skill=Skill.Excellent,
    )
    red = s.flight(
        Player.RED,
        planes.F_16C_50,
        FlightType.BARCAP,
        4,
        weapons,
        point(90, 0),
        skill=Skill.Average,
    )
    s.air_combat([blue, red])
    return Outcome(s.losses(Player.BLUE), s.losses(Player.RED))


def escorted_strike(seed: int) -> Outcome:
    """4 Hornets with bombs escorted by 2 Eagles, intercepted by 4 MiG-29s."""
    s = Scenario(seed)
    package = s.package(Player.BLUE)
    strikers = s.flight(
        Player.BLUE,
        planes.FA_18C_hornet,
        FlightType.STRIKE,
        4,
        loadout(("Mk 84", 4), ("AIM-9M", 2)),
        point(0, 0),
        package=package,
    )
    escort = s.flight(
        Player.BLUE,
        planes.F_15C,
        FlightType.ESCORT,
        2,
        loadout(("AIM-120C", 4), ("AIM-9M", 2)),
        point(0, 0),
        package=package,
    )
    red = s.flight(
        Player.RED,
        planes.MiG_29S,
        FlightType.BARCAP,
        4,
        loadout(("R-77", 2), ("R-73 (AA-11 Archer) - Infra Red", 2)),
        point(80, 0),
    )
    s.air_combat([strikers, escort, red])
    striker_losses = sum(1 for l in s.results.air_losses if l.flight is strikers)
    return Outcome(s.losses(Player.BLUE), s.losses(Player.RED), striker_losses)


def strike_through_sa10(seed: int, sead: bool = False) -> Outcome:
    s = Scenario(seed, blue="Bluefor Modern", red="Russia 2010")
    package = s.package(Player.BLUE)
    strikers = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        4,
        loadout(("Mk 84", 2), ("AIM-120C", 2)),
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
            loadout(("AGM-88C HARM", 2), ("AIM-120C", 2)),
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
            AD.S_300PS_54K6_cp,
            AD.S_300PS_5P85C_ln,
            AD.S_300PS_5P85C_ln,
            AD.S_300PS_5P85D_ln,
        ],
        iads=True,
    )
    losses = s.sam_transit(strikers, [site], windows=3)
    radars_killed = sum(1 for u in s.results.ground_losses)
    return _with_stats(s, Outcome(losses, 0, radars_killed), 4)


def low_level_vs_manpads(seed: int, altitude: float) -> Outcome:
    s = Scenario(seed)
    strikers = s.flight(
        Player.BLUE,
        planes.A_10C,
        FlightType.CAS,
        4,
        loadout(("Mk 82", 4)),
        point(0, 0),
        altitude_m=altitude,
        speed_kph=600,
    )
    site = s.sam(
        "MANPADS",
        point(2, 0),
        [AD.SA_18_Igla_manpad, AD.SA_18_Igla_manpad, AD.ZSU_23_4_Shilka],
    )
    losses = s.sam_transit(strikers, [site], windows=2)
    return Outcome(losses, 0)


def _dogfight(seed: int, env: CombatEnvironment) -> int:
    s = Scenario(seed, env=env)
    blue = s.flight(
        Player.BLUE,
        planes.F_86F_Sabre,
        FlightType.BARCAP,
        2,
        loadout(),
        point(0, 0),
        altitude_m=7000,
        speed_kph=800,
    )
    red = s.flight(
        Player.RED,
        planes.MiG_15bis,
        FlightType.BARCAP,
        2,
        loadout(),
        point(15, 0),
        altitude_m=7000,
        speed_kph=800,
    )
    s.air_combat([blue, red])
    return s.losses(Player.BLUE) + s.losses(Player.RED)


def night_dogfight(seed: int) -> Outcome:
    """Gun and rear-aspect IR fight: kills at night vs the same fight by day."""
    night = _dogfight(seed, NIGHT)
    day = _dogfight(seed, CombatEnvironment.clear_day())
    return Outcome(night, 0, day)


def factory_strike(
    seed: int,
    bomb: str,
    env: CombatEnvironment | None = None,
    aircraft: Any = planes.F_16C_50,
    tgp: bool = True,
) -> Outcome:
    s = Scenario(seed, env=env)
    target = s.target("Factory", point(50, 0), [Fortification.Barracks_2] * 6)
    weapons = [(bomb, 2)]
    if tgp:
        weapons.append(("AN/AAQ-28 LITENING", 1))
    package = s.package(Player.BLUE, target)
    flight = s.flight(
        Player.BLUE,
        aircraft,
        FlightType.STRIKE,
        4,
        loadout(*weapons),
        point(30, 0),
        package=package,
        altitude_m=7000,
    )
    report = s.strike(flight)
    return Outcome(report.losses, 0, report.kills)


def ground_war(
    seed: int, blue: int, red: int, blue_stance: CombatStance, red_stance: CombatStance
) -> Outcome:
    from game.sim.combat.model.groundbattle import GroundWar, FrontState, SideState
    from game.ground_forces.ai_ground_planner import CombatGroup, CombatGroupRole
    from game.dcs.groundunittype import GroundUnitType
    from types import SimpleNamespace

    s = Scenario(seed)
    tank = next(GroundUnitType.for_dcs_type(vehicles.Armor.T_72B))

    def groups(n: int) -> list[CombatGroup]:
        return [CombatGroup(CombatGroupRole.TANK, tank, 4) for _ in range(n // 4)]

    base = SimpleNamespace(total_armor=100)
    war = GroundWar(s.model, timedelta(minutes=10))
    front = FrontState(
        cast(Any, SimpleNamespace(name="Front")),
        SideState(
            cast(Any, SimpleNamespace(base=base, captured=Player.BLUE)),
            blue_stance,
            groups(blue),
            blue,
        ),
        SideState(
            cast(Any, SimpleNamespace(base=base, captured=Player.RED)),
            red_stance,
            groups(red),
            red,
        ),
        s.model.rng(),
    )
    for _ in range(10):  # A fast-forwarded turn: about 1h45 of fighting.
        war._round(front, s.time, 1.0)
    return Outcome(front.blue.losses, front.red.losses, float(front.red.broken))


# ---------------------------------------------------------------------------
# Historical validation
# ---------------------------------------------------------------------------


def _iraqi_iads(s: Scenario, red_x: float) -> list[Any]:
    """A 1991-style Iraqi sector: EWR, SA-2, SA-3, SA-6 and a Roland."""
    s.ewr("EWR", point(red_x + 40, 30))
    return [
        s.sam(
            "SA-2",
            point(red_x, 15),
            [AD.SNR_75V, AD.S_75M_Volhov, AD.S_75M_Volhov, AD.S_75M_Volhov],
            iads=True,
        ),
        s.sam(
            "SA-3",
            point(red_x + 20, -10),
            [AD.snr_s_125_tr, AD.p_19_s_125_sr, AD.x_5p73_s_125_ln, AD.x_5p73_s_125_ln],
            iads=True,
        ),
        s.sam(
            "SA-6",
            point(red_x + 35, 5),
            [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln],
            iads=True,
        ),
        s.sam("Roland", point(red_x + 45, 0), [AD.Roland_Radar, AD.Roland_ADS]),
    ]


def desert_storm_strike(seed: int) -> Outcome:
    """Night-one style package (4 strikers with pods, 2 HARM shooters, 2 escorts)
    crossing an intact Iraqi sector (3 minutes inside overlapping rings), then
    the attack on a point-defended target."""
    s = Scenario(seed, blue="NATO Desert Storm", red="Iraq 1991")
    sites = _iraqi_iads(s, 60)
    target = s.target(
        "Bunkers", point(100, 0), [Fortification.Barracks_2] * 4 + [AD.ZSU_23_4_Shilka]
    )
    package = s.package(Player.BLUE, target)
    strikers = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        4,
        loadout(("Mk 84", 2), ("AN/ALQ-131 ECM", 1), ("AIM-9M", 2)),
        point(75, 0),
        package=package,
        altitude_m=6500,
    )
    sead = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.SEAD_ESCORT,
        2,
        loadout(("AGM-88C HARM", 2), ("AN/ALQ-131 ECM", 1)),
        point(75, 5),
        package=package,
        altitude_m=7000,
    )
    escort = s.flight(
        Player.BLUE,
        planes.F_15C,
        FlightType.ESCORT,
        2,
        loadout(("AIM-7M", 4), ("AIM-9M", 4)),
        point(75, -5),
        package=package,
        altitude_m=8000,
    )
    # About three minutes crossing the rings on the way in.
    for flight in (sead, strikers, escort):
        s.sam_transit(flight, sites, windows=3)
    s.strike(strikers)
    lost = 8 - sum(f.count for f in (strikers, sead, escort))
    return _with_stats(s, Outcome(lost, 0), 8)


def allied_force(seed: int) -> Outcome:
    """NATO at medium altitude with HARM shooters over SA-3/SA-6 crews that
    fear ARMs, 4 minutes in range."""
    from game.sim.combat.model.airdefense import sead_hunt

    s = Scenario(seed, blue="NATO OIF", red="Syria 2011")
    s.ewr("EWR", point(90, 30))
    sites = [
        s.sam(
            "SA-3",
            point(60, 10),
            [AD.snr_s_125_tr, AD.p_19_s_125_sr, AD.x_5p73_s_125_ln, AD.x_5p73_s_125_ln],
            iads=True,
        ),
        s.sam(
            "SA-6",
            point(75, -10),
            [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln],
            iads=True,
        ),
    ]
    package = s.package(Player.BLUE)
    strikers = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.STRIKE,
        4,
        loadout(("GBU-12", 2), ("AN/ALQ-131 ECM", 1)),
        point(60, 0),
        package=package,
        altitude_m=7500,
    )
    sead = s.flight(
        Player.BLUE,
        planes.F_16C_50,
        FlightType.SEAD_ESCORT,
        2,
        loadout(("AGM-88C HARM", 2), ("AN/ALQ-131 ECM", 1)),
        point(60, 4),
        package=package,
        altitude_m=7500,
    )
    sead_hunt(s.model, s.time, s.events)
    s.sam_transit(sead, sites, windows=4)
    s.sam_transit(strikers, sites, windows=4)
    lost = 6 - strikers.count - sead.count
    return _with_stats(s, Outcome(lost, 0), 6)


def linebacker(seed: int) -> Outcome:
    """A 3-ship B-52 cell through an SA-2 belt over Hanoi, 5 minutes."""
    s = Scenario(seed, blue="USA 1970 Vietnam War", red="Vietnam 1970")
    s.ewr("EWR", point(80, 40))
    sites = [
        s.sam(
            f"SA-2 {i}",
            point(50 + 12 * i, 12 if i % 2 else -12),
            [AD.SNR_75V, AD.S_75M_Volhov, AD.S_75M_Volhov, AD.S_75M_Volhov],
            iads=True,
        )
        for i in range(4)
    ]
    cell = s.flight(
        Player.BLUE,
        planes.B_52H,
        FlightType.STRIKE,
        3,
        loadout(("Mk 82", 2)),
        point(30, 0),
        altitude_m=10000,
        speed_kph=850,
    )
    lost = s.sam_transit(cell, sites, windows=5)
    return _with_stats(s, Outcome(lost, 0), 3)


def yom_kippur(seed: int) -> Outcome:
    """Israeli F-4Es without modern pods, low over an intact SA-6/ZSU belt."""
    s = Scenario(seed, blue="Israel 1973", red="Syria 1973")
    sites = [
        s.sam("SA-6", point(10, 5), [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln]),
        s.sam(
            "SA-6 b", point(20, -5), [AD.Kub_1S91_str, AD.Kub_2P25_ln, AD.Kub_2P25_ln]
        ),
        s.sam(
            "ZSU",
            point(8, 0),
            [AD.ZSU_23_4_Shilka, AD.ZSU_23_4_Shilka, AD.SA_18_Igla_manpad],
        ),
    ]
    flight = s.flight(
        Player.BLUE,
        planes.F_4E_45MC,
        FlightType.CAS,
        4,
        loadout(("Mk 82", 4)),
        point(0, 0),
        altitude_m=1500,
        speed_kph=850,
    )
    lost = s.sam_transit(flight, sites, windows=3)
    return _with_stats(s, Outcome(lost, 0), 4)


def desert_storm_air(seed: int) -> Outcome:
    """F-15Cs with AWACS against Iraqi MiG-29s and MiG-23s."""
    s = Scenario(seed, blue="NATO Desert Storm", red="Iraq 1991")
    s.flight(
        Player.BLUE,
        planes.E_3A,
        FlightType.AEWC,
        1,
        loadout(),
        point(-150, 0),
        altitude_m=9000,
        speed_kph=650,
    )
    eagles = s.flight(
        Player.BLUE,
        planes.F_15C,
        FlightType.BARCAP,
        4,
        loadout(("AIM-7M", 4), ("AIM-9M", 4)),
        point(0, 0),
    )
    fulcrums = s.flight(
        Player.RED,
        planes.MiG_29A,
        FlightType.BARCAP,
        2,
        loadout(("R-27R", 2), ("R-60M", 2)),
        point(90, 0),
        altitude_m=6000,
    )
    floggers = s.flight(
        Player.RED,
        planes.MiG_23MLD,
        FlightType.BARCAP,
        2,
        loadout(("R-24R", 2), ("R-60M", 2)),
        point(95, 10),
        altitude_m=5000,
    )
    s.air_combat([eagles, fulcrums, floggers])
    return _with_stats(s, Outcome(s.losses(Player.BLUE), s.losses(Player.RED)), 4)


HISTORICAL = [
    HistoricalCheck(
        "Desert Storm: package vs intact Iraqi IADS",
        desert_storm_strike,
        "first week ~0.1% per sortie theatre-wide (with massed SEAD and decoys; this "
        "is one package through an untouched sector, so allow up to 1.5%); radar "
        "SAMs a few % per missile at most",
        lambda r: r.loss_per_sortie <= 0.015 and r.sam_pk <= 0.03,
    ),
    HistoricalCheck(
        "Allied Force: NATO vs ARM-fearing SA-3/SA-6",
        allied_force,
        "2 losses in 38,000 sorties; ~700 SAMs for 2 kills (~0.3%/missile)",
        lambda r: r.loss_per_sortie <= 0.01 and r.sam_pk <= 0.015,
    ),
    HistoricalCheck(
        "Linebacker II: B-52 cell vs SA-2 belt",
        linebacker,
        "15 of 741 B-52 sorties (2%); ~1% per SA-2",
        lambda r: 0.005 <= r.loss_per_sortie <= 0.08 and 0.003 <= r.sam_pk <= 0.04,
    ),
    HistoricalCheck(
        "Yom Kippur: F-4E low vs intact SA-6/ZSU belt",
        yom_kippur,
        "~1% per sortie over the war, several % early against intact belts",
        lambda r: 0.02 <= r.loss_per_sortie <= 0.2,
    ),
    HistoricalCheck(
        "Desert Storm air-to-air: F-15C + AWACS vs Iraqi MiGs",
        desert_storm_air,
        "33+ kills for 1 loss; AIM-7 ~34% per launch",
        lambda r: r.red >= 10 * max(r.blue, 0.02) and 0.2 <= r.a2a_pk <= 0.55,
    ),
]


OVERCAST_LOW = CombatEnvironment(TimeOfDay.Day, 15, 800, 2500, 0.95, False, False)
NIGHT = CombatEnvironment(TimeOfDay.Night, 15, None, None, 0, False, False)

CHECKS = [
    Check(
        "4 F-15C (AIM-120) vs 4 MiG-21",
        eagles_vs_fishbeds,
        "blue nearly untouched, red loses about 1.5+",
        lambda b, r, e: b < 0.3 and r > 1.2,
    ),
    Check(
        "4 F-16C vs 4 F-16C (mirror)",
        vipers_mirror,
        "even exchange (ratio within 0.7 - 1.4)",
        lambda b, r, e: 0.7 <= (b + 0.01) / (r + 0.01) <= 1.4,
    ),
    Check(
        "4 F-15C (AIM-7M) vs 4 Su-27 (R-27ER)",
        flankers_vs_eagles_sparrows,
        "competitive, roughly even (ratio 0.5 - 2.0)",
        lambda b, r, e: 0.5 <= (b + 0.01) / (r + 0.01) <= 2.0,
    ),
    Check(
        "Excellent vs Average pilots, same jets",
        skill_gap,
        "skilled side wins clearly (exchange about 2:1 or better)",
        lambda b, r, e: r >= 1.8 * b,
    ),
    Check(
        "Escorted strike vs 4 MiG-29S",
        escorted_strike,
        "escorts trade with the MiGs; strikers lose < 1 on average",
        lambda b, r, e: e < 1.0 and r > 0.8,
    ),
    Check(
        "4 F-16 in modern SA-10 coverage (3 min), no SEAD",
        lambda s: strike_through_sa10(s, False),
        "the most dangerous radar SAM case (>= 0.15 per 4-ship)",
        lambda b, r, e: b >= 0.15,
    ),
    Check(
        "4 F-16 transit SA-10 (3 min), with SEAD",
        lambda s: strike_through_sa10(s, True),
        "SEAD all but eliminates the threat (< 0.05)",
        lambda b, r, e: b < 0.05,
    ),
    Check(
        "4 A-10 low (300 m) over MANPADS/Shilka",
        lambda s: low_level_vs_manpads(s, 300),
        "the most dangerous place to be (>= 0.3 per 4-ship)",
        lambda b, r, e: b >= 0.3,
    ),
    Check(
        "4 A-10 high (5000 m) over MANPADS/Shilka",
        lambda s: low_level_vs_manpads(s, 5000),
        "immune (no losses)",
        lambda b, r, e: b == 0,
    ),
    Check(
        "4 F-16 GBU-12 + TGP vs 6 buildings, clear",
        lambda s: factory_strike(s, "GBU-12"),
        "most of the target destroyed (>= 4)",
        lambda b, r, e: e >= 4,
    ),
    Check(
        "Same strike under 800 m overcast",
        lambda s: factory_strike(s, "GBU-12", OVERCAST_LOW),
        "lasers blocked by cloud (<= 1.5 destroyed)",
        lambda b, r, e: e <= 1.5,
    ),
    Check(
        "GBU-38 (JDAM) under 800 m overcast",
        lambda s: factory_strike(s, "GBU-38", OVERCAST_LOW),
        "GPS ignores the weather (>= 4)",
        lambda b, r, e: e >= 4,
    ),
    Check(
        "F-4E with Mk-82 at night, no pod",
        lambda s: factory_strike(s, "Mk 82", NIGHT, planes.F_4E_45MC, False),
        "dumb bombs at night are poor (<= 2.5)",
        lambda b, r, e: e <= 2.5,
    ),
    Check(
        "Ground: 60 tanks attack 20 dug in",
        lambda s: ground_war(
            s, 60, 20, CombatStance.AGGRESSIVE, CombatStance.DEFENSIVE
        ),
        "3:1 attack breaks the defense (> 50%) for < 15% losses",
        lambda b, r, e: e > 0.5 and b < 0.15 * 60,
    ),
    Check(
        "Ground: 20 tanks attack 20 dug in",
        lambda s: ground_war(
            s, 20, 20, CombatStance.AGGRESSIVE, CombatStance.DEFENSIVE
        ),
        "1:1 attack bleeds the attacker: 10-30% a turn, > defender",
        lambda b, r, e: b > r * 1.3 and 0.1 * 20 <= b <= 0.3 * 20,
    ),
    Check(
        "Ground: 20 v 20 meeting engagement",
        lambda s: ground_war(
            s, 20, 20, CombatStance.AGGRESSIVE, CombatStance.AGGRESSIVE
        ),
        "even fight, 10-35% each; nobody is wiped out in a turn",
        lambda b, r, e: all(0.1 * 20 <= x <= 0.35 * 20 for x in (b, r)),
    ),
    Check(
        "Ground: 20 v 20 both defensive",
        lambda s: ground_war(s, 20, 20, CombatStance.DEFENSIVE, CombatStance.DEFENSIVE),
        "standoff: patrols and artillery only (< 10% each)",
        lambda b, r, e: b < 0.1 * 20 and r < 0.1 * 20,
    ),
    Check(
        "2v2 F-86 vs MiG-15 guns: night (blue) vs day (extra)",
        night_dogfight,
        "clearly fewer kills at night than by day",
        lambda b, r, e: b < 0.75 * e,
    ),
]


def main() -> None:
    logging.disable(logging.WARNING)
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    failed = 0
    for check in CHECKS:
        outcomes = [check.run(seed) for seed in range(runs)]
        blue = statistics.mean(o.blue_losses for o in outcomes)
        red = statistics.mean(o.red_losses for o in outcomes)
        extra = statistics.mean(o.extra for o in outcomes)
        ok = check.passes(blue, red, extra)
        failed += not ok
        print(
            f"{'PASS' if ok else 'FAIL'}  {check.name:45s} blue {blue:4.2f}  red {red:4.2f}"
            f"  extra {extra:5.2f}   expect: {check.expectation}"
        )
    print("\nHistorical validation")
    for historical in HISTORICAL:
        summary = summarize([historical.run(seed) for seed in range(runs)])
        ok = historical.passes(summary)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {historical.name:52s} {summary.describe()}")
        print(f"      record: {historical.record}")
    total = len(CHECKS) + len(HISTORICAL)
    print(f"\n{total - failed}/{total} checks in band ({runs} runs each)")


if __name__ == "__main__":
    main()
