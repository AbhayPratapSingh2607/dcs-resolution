"""Terrain grids for checking player FARP sites.

Each theater may have a ``farpterrain.npz`` grid of 200m cells, in DCS
coordinates, that flags uneven terrain, built-up areas and arid (desert) land.
The grids are generated from open real-world data by
``resources/tools/generate_farp_terrain.py``. Theaters without one skip the
terrain checks.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import numpy.typing as npt
from dcs.mapping import Point

FARP_TERRAIN_FILE = "farpterrain.npz"
FARP_TERRAIN_CELL_SIZE = 200


@dataclass(frozen=True)
class SiteTerrain:
    """What the terrain grid says about the area a FARP would cover."""

    #: Whether there is grid data for the area at all.
    known: bool
    steep: bool
    built_up: bool
    #: Whether most of the area is bare ground or shrubland.
    arid: bool


UNKNOWN_SITE = SiteTerrain(known=False, steep=False, built_up=False, arid=False)


@dataclass(frozen=True)
class FarpTerrain:
    #: DCS x (north) and y (east) of the grid's south-west corner.
    origin_x: float
    origin_y: float
    cell: float
    #: Boolean grids indexed [row along x, column along y].
    steep: npt.NDArray[np.bool_]
    built_up: npt.NDArray[np.bool_]
    arid: npt.NDArray[np.bool_]

    @property
    def shape(self) -> tuple[int, int]:
        return self.steep.shape  # type: ignore[return-value]

    def survey(self, point: Point, radius: float) -> SiteTerrain:
        """Summarizes the cells within radius of point.

        A cell counts if any part of it may be within the radius, so the check
        errs on the side of rejecting a site.
        """
        rows, cols = self.shape
        reach = radius + self.cell * math.sqrt(2) / 2
        row_lo = max(0, math.floor((point.x - reach - self.origin_x) / self.cell))
        row_hi = min(
            rows - 1, math.floor((point.x + reach - self.origin_x) / self.cell)
        )
        col_lo = max(0, math.floor((point.y - reach - self.origin_y) / self.cell))
        col_hi = min(
            cols - 1, math.floor((point.y + reach - self.origin_y) / self.cell)
        )
        if row_lo > row_hi or col_lo > col_hi:
            return UNKNOWN_SITE
        row_idx = np.arange(row_lo, row_hi + 1)
        col_idx = np.arange(col_lo, col_hi + 1)
        centre_x = self.origin_x + (row_idx + 0.5) * self.cell
        centre_y = self.origin_y + (col_idx + 0.5) * self.cell
        dist = np.hypot(
            (centre_x - point.x)[:, np.newaxis], (centre_y - point.y)[np.newaxis, :]
        )
        near = dist <= reach
        if not near.any():
            return UNKNOWN_SITE
        window = (slice(row_lo, row_hi + 1), slice(col_lo, col_hi + 1))
        return SiteTerrain(
            known=True,
            steep=bool(self.steep[window][near].any()),
            built_up=bool(self.built_up[window][near].any()),
            arid=bool(self.arid[window][near].mean() > 0.5),
        )

    def save(self, path: Path) -> None:
        rows, cols = self.shape
        np.savez_compressed(
            path,
            origin=np.array([self.origin_x, self.origin_y, self.cell]),
            shape=np.array([rows, cols]),
            steep=np.packbits(self.steep.ravel()),
            built_up=np.packbits(self.built_up.ravel()),
            arid=np.packbits(self.arid.ravel()),
        )

    @staticmethod
    def load(path: Path) -> Optional[FarpTerrain]:
        if not path.exists():
            return None
        try:
            with np.load(path) as data:
                origin_x, origin_y, cell = (float(v) for v in data["origin"])
                rows, cols = (int(v) for v in data["shape"])

                def grid(name: str) -> npt.NDArray[np.bool_]:
                    bits = np.unpackbits(data[name], count=rows * cols)
                    return bits.astype(bool).reshape(rows, cols)

                return FarpTerrain(
                    origin_x,
                    origin_y,
                    cell,
                    grid("steep"),
                    grid("built_up"),
                    grid("arid"),
                )
        except Exception:
            logging.exception(f"Failed to load FARP terrain grid {path}")
            return None
