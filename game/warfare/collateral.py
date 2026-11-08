"""Rules of engagement and collateral damage.

Targets in or next to built-up areas risk civilian casualties when weapons go
astray or are inherently imprecise (dumb bombs, cluster munitions, rockets).
Each incident costs the striking side national resolve (more so for nations
whose public is sensitive to it) and hands the enemy a propaganda boost.

Under restrictive rules of engagement the AI won't plan strikes against
high-risk targets and pilots release unguided weapons more cautiously.

Built-up areas come from the theater's terrain grid (ESA WorldCover, see
game.theater.farpterrain). Theaters without one fall back to a heuristic by
target type and distance to towns (control points).
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional, TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from dcs import Point

    from game import Game
    from game.theater import TheaterGroundObject
    from game.theater.player import Player

#: Radius around the aim point that counts for collateral risk.
RISK_RADIUS_M = 1000.0

#: Target categories that are usually in or near towns (dual-use).
URBAN_CATEGORIES = {
    "power",
    "oil",
    "comms",
    "factory",
    "commandcenter",
    "ware",
    "fuel",
    "village",
    "ammo",
}


class RoeSetting(Enum):
    DOCTRINE = "Doctrine"
    PERMISSIVE = "Permissive"
    RESTRICTIVE = "Restrictive"


def enabled(game: Game) -> bool:
    return bool(getattr(game.settings, "collateral_damage_enabled", True))


def built_up_fraction(
    game: Game, point: Point, radius: float = RISK_RADIUS_M
) -> Optional[float]:
    terrain = getattr(game.theater, "farp_terrain", None)
    if terrain is None:
        return None
    rows, cols = terrain.shape
    row_lo = max(0, math.floor((point.x - radius - terrain.origin_x) / terrain.cell))
    row_hi = min(
        rows - 1, math.floor((point.x + radius - terrain.origin_x) / terrain.cell)
    )
    col_lo = max(0, math.floor((point.y - radius - terrain.origin_y) / terrain.cell))
    col_hi = min(
        cols - 1, math.floor((point.y + radius - terrain.origin_y) / terrain.cell)
    )
    if row_lo > row_hi or col_lo > col_hi:
        return None
    rows_idx = np.arange(row_lo, row_hi + 1)
    cols_idx = np.arange(col_lo, col_hi + 1)
    cx = terrain.origin_x + (rows_idx + 0.5) * terrain.cell
    cy = terrain.origin_y + (cols_idx + 0.5) * terrain.cell
    dist = np.hypot((cx - point.x)[:, np.newaxis], (cy - point.y)[np.newaxis, :])
    near = dist <= radius
    if not near.any():
        return None
    window = terrain.built_up[row_lo : row_hi + 1, col_lo : col_hi + 1]
    return float(window[near].mean())


def risk_at(game: Game, point: Point, category: str = "") -> float:
    """Collateral risk of an attack at this point, 0..1."""
    fraction = built_up_fraction(game, point)
    if fraction is not None:
        # Even a modest share of buildings within a kilometre is a real risk.
        return min(1.0, fraction * 2.5)
    risk = 0.4 if category in URBAN_CATEGORIES else 0.05
    try:
        nearest = min(
            cp.position.distance_to_point(point) for cp in game.theater.controlpoints
        )
        if nearest < 5000:
            risk += 0.2
    except ValueError:
        pass
    return min(1.0, risk)


def tgo_risk(game: Game, tgo: TheaterGroundObject) -> float:
    return risk_at(game, tgo.position, getattr(tgo, "category", ""))


def describe(risk: float) -> str:
    if risk >= 0.5:
        return "high"
    if risk >= 0.2:
        return "medium"
    return "low"


def restrictive(game: Game, player: Player) -> bool:
    setting = getattr(game.settings, "roe_strictness", RoeSetting.DOCTRINE)
    if setting is RoeSetting.PERMISSIVE:
        return False
    if setting is RoeSetting.RESTRICTIVE:
        return True
    from game.warfare.doctrine import for_faction_obj

    return for_faction_obj(game.coalition_for(player).faction).roe_restrictive


#: Chance per weapon that misses (or for area weapons, any weapon) causes a
#: civilian casualty incident at full risk.
WEAPON_SPREAD = {
    "cluster": 0.5,
    "unguided": 0.35,
    "rocket": 0.3,
    "runway": 0.3,
    "gun": 0.08,
    "laser": 0.08,
    "gps": 0.06,
    "tv": 0.08,
    "iir": 0.08,
    "beam": 0.15,
    "atgm": 0.04,
    "antiship": 0.02,
    "anti_radiation": 0.04,
}
AREA_WEAPONS = {"cluster", "unguided", "rocket", "runway"}
