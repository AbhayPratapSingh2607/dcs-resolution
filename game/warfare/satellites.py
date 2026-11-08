"""Imaging satellites.

Nations with a space programme get a number of imaging passes per turn,
tasked automatically on the areas that matter most: the fronts, sites known
only vaguely, enemy airbases, and places nobody has looked at yet.

Balance:

* Optical satellites see best but need daylight and clear skies; under
  overcast or at night a pass is wasted. Radar (SAR) satellites see through
  weather and darkness but identify less.
* Each pass covers one swath (about 100 km across), so a side can only look at
  a few places per turn.
* Imagery is old by the time it is analysed: mobile units may have moved, so
  their positions carry extra error.
* Camouflage hides mobile units, and decoys fool imagery easily.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

from .deception import maybe_fooled
from .intel import IntelPicture, IntelSource, enemy_ground_objects, is_mobile

if TYPE_CHECKING:
    from dcs import Point

    from game import Game
    from game.sim.combat.model.environment import CombatEnvironment
    from game.theater.player import Player
    from .warstate import WarState

SWATH_RADIUS_M = 50_000


@dataclass(frozen=True)
class PassReport:
    optical: bool
    blocked: bool
    located: int
    cleared_phantoms: int


def strength(game: Game) -> float:
    return float(getattr(game.settings, "intel_source_strength", 1.0))


def run_satellites(
    game: Game,
    war_state: WarState,
    viewer: Player,
    rng: random.Random,
    env: Optional[CombatEnvironment] = None,
) -> list[PassReport]:
    from game.sim.combat.model.environment import CombatEnvironment
    from game.timeofday import TimeOfDay

    doctrine = war_state.doctrine(game, viewer)
    optical_passes = [True] * doctrine.sat_optical_passes
    sar_passes = [False] * doctrine.sat_sar_passes
    if not optical_passes and not sar_passes:
        return []
    picture = war_state.picture(game, viewer)
    if env is None:
        try:
            env = CombatEnvironment.from_conditions(game.conditions)
        except Exception:
            env = CombatEnvironment.clear_day()
    daylight = env.time_of_day is not TimeOfDay.Night
    enemy_deception = war_state.doctrine(game, viewer.opponent).deception

    # Planners know the forecast: in bad weather or darkness the radar
    # satellites get the most important swaths.
    forecast = (1.0 - env.cloud_cover) if daylight else 0.0
    if forecast < 0.5:
        passes = sar_passes + optical_passes
    else:
        passes = optical_passes + sar_passes
    swaths = _task_swaths(game, picture, viewer, len(passes))
    if not swaths:
        return []
    # With fewer worthwhile areas than passes, revisit the best ones.
    swaths = [swaths[i % len(swaths)] for i in range(len(passes))]

    reports = []
    for centre, optical in zip(swaths, passes):
        if optical:
            # Each optical pass gets its own look at the weather.
            visibility = (1.0 - env.cloud_cover) if daylight else 0.0
            if rng.random() > visibility:
                reports.append(PassReport(True, True, 0, 0))
                continue
            quality = doctrine.sat_quality
        else:
            quality = doctrine.sat_quality * 0.75
        quality *= strength(game)
        located = 0
        for tgo in enemy_ground_objects(game, viewer):
            if tgo.is_dead or tgo.position.distance_to_point(centre) > SWATH_RADIUS_M:
                continue
            if is_mobile(tgo):
                p = quality * 0.45 * (1 - 0.4 * enemy_deception)
                if not optical:
                    p *= 0.8
            else:
                p = quality * (0.9 if optical else 0.7)
            if rng.random() >= p:
                continue
            located += 1
            picture.observe(
                tgo,
                min(0.95, 0.35 + quality * 0.6),
                IntelSource.SATELLITE,
                game.turn,
                rng,
            )
            if maybe_fooled(game, war_state, picture, tgo, IntelSource.SATELLITE, rng):
                continue
            if is_mobile(tgo):
                # The imagery is hours old by the time anyone acts on it.
                contact = picture.contact(tgo)
                if contact is not None:
                    contact.error_m += rng.uniform(1000, 3000)
        for cp in game.theater.control_points_for(viewer.opponent):
            if cp.position.distance_to_point(centre) <= SWATH_RADIUS_M:
                previous = picture.airbase_quality.get(cp.id, 0.0)
                picture.airbase_quality[cp.id] = max(previous, min(0.95, quality))
        cleared = picture.clear_phantoms_near(
            centre.x, centre.y, SWATH_RADIUS_M, quality * (0.9 if optical else 0.6), rng
        )
        reports.append(PassReport(optical, False, located, cleared))
    return reports


def _task_swaths(
    game: Game, picture: IntelPicture, viewer: Player, count: int
) -> list[Point]:
    """Picks swath centres, most valuable first, without overlapping."""
    candidates: list[tuple[float, Point]] = []
    for front_line in game.theater.conflicts():
        enemy_cp = front_line.red_cp if viewer.is_blue else front_line.blue_cp
        # Look behind the enemy's side of the front.
        midpoint = front_line.position
        towards = midpoint.heading_between_point(enemy_cp.position)
        candidates.append((4.0, midpoint.point_from_heading(towards, 25_000)))
    for tgo in enemy_ground_objects(game, viewer):
        contact = picture.contact(tgo)
        if contact is None or tgo.is_dead or not contact.known or contact.confirmed:
            continue
        value = 2.0 + (1.0 - contact.confidence)
        candidates.append((value, picture.estimated_position(tgo)))
    for cp in game.theater.control_points_for(viewer.opponent):
        unknown = sum(
            1 for tgo in cp.ground_objects if not tgo.is_dead and not picture.knows(tgo)
        )
        candidates.append(
            (1.5 + 0.1 * unknown - picture.airbase_quality.get(cp.id, 0), cp.position)
        )
    candidates.sort(key=lambda c: -c[0])
    chosen: list[Point] = []
    for _, point in candidates:
        if all(point.distance_to_point(p) > SWATH_RADIUS_M * 1.5 for p in chosen):
            chosen.append(point)
        if len(chosen) >= count:
            break
    return chosen


def summarize(reports: list[PassReport]) -> str:
    blocked = sum(1 for r in reports if r.blocked)
    located = sum(r.located for r in reports)
    cleared = sum(r.cleared_phantoms for r in reports)
    text = f"{len(reports)} imaging passes"
    if blocked:
        text += f" ({blocked} lost to weather or darkness)"
    text += f", {located} sites imaged"
    if cleared:
        text += f", {cleared} false reports discounted"
    return text
