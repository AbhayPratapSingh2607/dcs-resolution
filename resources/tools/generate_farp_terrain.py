"""Generates the terrain grids used to check player FARP sites.

For each theater this writes ``resources/theaters/<theater>/farpterrain.npz``, a
grid of 200m cells in DCS coordinates covering the theater's land. Each cell is
flagged as:

* steep: too uneven for a FARP,
* built_up: a town or other built-up area,
* arid: mostly bare ground or shrubland (desert scenery).

DCS maps follow real-world geography, so the grids are built from open
real-world data:

* Elevation: Copernicus DEM GLO-90. Produced using Copernicus WorldDEM-90
  (c) DLR e.V. 2010-2014 and (c) Airbus Defence and Space GmbH 2014-2018,
  provided under COPERNICUS by the European Union and ESA; all rights reserved.
* Land cover: ESA WorldCover 10m 2021 v200 (c) ESA WorldCover project 2021,
  contains modified Copernicus Sentinel data (2021) processed by the ESA
  WorldCover consortium. Licensed under CC BY 4.0.

DCS terrain doesn't match the real world exactly, so the grids are an
approximation.

The data is read from the public AWS buckets of both datasets and cached on
disk, so re-running (for example to tune the thresholds) doesn't download it
again. This is a development tool; it needs rasterio, which is not a runtime
dependency:

    pip install rasterio
    python resources/tools/generate_farp_terrain.py [--jobs N] [theater ...]

With no theater names, every theater in resources/theaters is generated.
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import tempfile
import time
from collections import OrderedDict
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import rasterio
import shapely
from pyproj import Transformer
from rasterio.errors import RasterioIOError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from game.theater.farpterrain import (  # noqa: E402
    FARP_TERRAIN_CELL_SIZE,
    FARP_TERRAIN_FILE,
    FarpTerrain,
)
from game.theater.theaterloader import TheaterLoader  # noqa: E402

THEATERS_DIR = Path("resources/theaters")
DEFAULT_CACHE_DIR = Path(tempfile.gettempdir()) / "retribution_farp_terrain"

DEM_URL = (
    "https://copernicus-dem-90m.s3.amazonaws.com/"
    "Copernicus_DSM_COG_30_{lat}_00_{lon}_00_DEM/"
    "Copernicus_DSM_COG_30_{lat}_00_{lon}_00_DEM.tif"
)
#: Degrees covered by each DEM tile.
DEM_TILE = 1
WORLDCOVER_URL = (
    "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
    "ESA_WorldCover_10m_2021_v200_{lat}{lon}_Map.tif"
)
#: Degrees covered by each WorldCover tile.
WORLDCOVER_TILE = 3
#: WorldCover overview level to read: 1 is a quarter of the 10m resolution
#: (about 37m), plenty for 200m cells and much smaller to download.
WORLDCOVER_OVERVIEW_LEVEL = 1

WORLDCOVER_SHRUBLAND = 20
WORLDCOVER_BUILT_UP = 50
WORLDCOVER_BARE = 60

#: Each cell is sampled on a SUBSAMPLES x SUBSAMPLES grid (40m apart).
SUBSAMPLES = 5

#: A sample is steep when the slope there is above this many degrees.
STEEP_SLOPE_DEGREES = 8.0
#: A cell is steep when more than this share of its samples are steep...
STEEP_SAMPLE_SHARE = 0.2
#: ...or its elevation varies by more than this many meters.
STEEP_ELEVATION_RANGE = 20.0
#: A cell is built up when more than this share of it is built-up land.
BUILT_UP_SHARE = 0.1

#: Rows of cells processed at once. The grid is processed south to north in
#: bands this many cells (here 12.8km) tall, so each band needs few tiles.
ROW_CHUNK = 64

#: Tiles kept in memory. A band crosses at most one row of tiles, and the next
#: band mostly needs the same ones.
DEM_TILES_IN_MEMORY = 40
WORLDCOVER_TILES_IN_MEMORY = 8


def lat_name(lat: int) -> str:
    return f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}"


def lon_name(lon: int) -> str:
    return f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}"


@dataclass
class Raster:
    """A geographic (EPSG:4326) raster held in memory."""

    data: np.ndarray
    west: float
    north: float
    res_lon: float
    res_lat: float

    def sample(self, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
        """Values at points inside the raster (edges are clamped)."""
        rows, cols = self.data.shape
        col = np.clip(((lon - self.west) / self.res_lon).astype(np.int64), 0, cols - 1)
        row = np.clip(((self.north - lat) / self.res_lat).astype(np.int64), 0, rows - 1)
        return self.data[row, col]

    def save(self, path: Path) -> None:
        np.savez_compressed(
            path,
            data=self.data,
            geo=np.array([self.west, self.north, self.res_lon, self.res_lat]),
        )

    @staticmethod
    def load(path: Path) -> Raster:
        with np.load(path) as f:
            west, north, res_lon, res_lat = (float(v) for v in f["geo"])
            return Raster(f["data"], west, north, res_lon, res_lat)


def fetch_raster(
    url: str, cache_path: Path, overview_level: Optional[int] = None
) -> Optional[Raster]:
    """Reads a raster, from the disk cache when possible.

    Returns None for tiles that don't exist (those entirely over sea).
    """
    missing = cache_path.with_suffix(".missing")
    if cache_path.exists():
        return Raster.load(cache_path)
    if missing.exists():
        return None
    kwargs = {} if overview_level is None else {"overview_level": overview_level}
    try:
        with rasterio.open(url, **kwargs) as src:
            data = src.read(1)
            transform = src.transform
    except RasterioIOError:
        missing.touch()
        return None
    raster = Raster(data, transform.c, transform.f, transform.a, -transform.e)
    # Write then rename, as other processes may be fetching the same tile.
    partial = cache_path.with_name(f"{cache_path.stem}.{os.getpid()}.partial.npz")
    raster.save(partial)
    os.replace(partial, cache_path)
    return raster


def slope_degrees(dem: Raster) -> np.ndarray:
    """Slope of a geographic DEM, in degrees."""
    elevation = dem.data.astype(np.float32)
    rows = elevation.shape[0]
    lats = dem.north - (np.arange(rows) + 0.5) * dem.res_lat
    dy = dem.res_lat * 111_320.0
    dx = (dem.res_lon * 111_320.0 * np.cos(np.radians(lats)))[:, np.newaxis]
    grad_y, grad_x = np.gradient(elevation)
    gradient = np.hypot(grad_x / dx, grad_y / dy)
    return np.degrees(np.arctan(gradient)).astype(np.float32)


@dataclass
class DemTile:
    elevation: Raster
    slope: Raster


class TileCache:
    """Least recently used tiles, loaded on demand."""

    def __init__(
        self, load: Callable[[int, int], Optional[object]], capacity: int
    ) -> None:
        self.load = load
        self.capacity = capacity
        self.tiles: OrderedDict[tuple[int, int], Optional[object]] = OrderedDict()

    def get(self, lat: int, lon: int) -> Optional[object]:
        key = (lat, lon)
        if key in self.tiles:
            self.tiles.move_to_end(key)
            return self.tiles[key]
        tile = self.load(lat, lon)
        self.tiles[key] = tile
        if len(self.tiles) > self.capacity:
            self.tiles.popitem(last=False)
        return tile


def tile_groups(lat: np.ndarray, lon: np.ndarray, size: int) -> list[tuple[int, int]]:
    """South-west corners of the tiles of the given size that the points fall in."""
    tile_lat = np.floor(lat.ravel() / size).astype(np.int64)
    tile_lon = np.floor(lon.ravel() / size).astype(np.int64)
    # One integer per tile; a 1D unique is far faster than a row-wise one.
    keys = np.unique((tile_lat + 1000) * 10_000 + (tile_lon + 1000))
    return [
        (int(key // 10_000 - 1000) * size, int(key % 10_000 - 1000) * size)
        for key in keys
    ]


def generate(name: str, cache_dir: Path) -> str:
    started = time.time()
    theater = TheaterLoader(name).load()
    landmap = theater.landmap
    if landmap is None:
        raise RuntimeError(f"{name} has no landmap")
    land = landmap.inclusion_zones
    sea = landmap.sea_zones
    shapely.prepare(land)
    shapely.prepare(sea)
    to_latlon = Transformer.from_crs(
        theater.terrain.projection_parameters.to_crs(), "EPSG:4326"
    )

    cell = FARP_TERRAIN_CELL_SIZE
    min_x, min_y, max_x, max_y = land.bounds
    origin_x = math.floor(min_x / cell) * cell
    origin_y = math.floor(min_y / cell) * cell
    rows = math.ceil((max_x - origin_x) / cell)
    cols = math.ceil((max_y - origin_y) / cell)

    dem_dir = cache_dir / "dem"
    cover_dir = cache_dir / "worldcover"
    dem_dir.mkdir(parents=True, exist_ok=True)
    cover_dir.mkdir(parents=True, exist_ok=True)

    def load_dem(lat: int, lon: int) -> Optional[DemTile]:
        tile = f"{lat_name(lat)}_{lon_name(lon)}"
        raster = fetch_raster(
            DEM_URL.format(lat=lat_name(lat), lon=lon_name(lon)),
            dem_dir / f"{tile}.npz",
        )
        if raster is None:
            return None
        slope = Raster(
            slope_degrees(raster),
            raster.west,
            raster.north,
            raster.res_lon,
            raster.res_lat,
        )
        return DemTile(raster, slope)

    def load_cover(lat: int, lon: int) -> Optional[Raster]:
        tile = f"{lat_name(lat)}{lon_name(lon)}"
        return fetch_raster(
            WORLDCOVER_URL.format(lat=lat_name(lat), lon=lon_name(lon)),
            cover_dir / f"{tile}.npz",
            WORLDCOVER_OVERVIEW_LEVEL,
        )

    dem_tiles = TileCache(load_dem, DEM_TILES_IN_MEMORY)
    cover_tiles = TileCache(load_cover, WORLDCOVER_TILES_IN_MEMORY)

    land_mask = np.zeros((rows, cols), dtype=bool)
    steep = np.zeros((rows, cols), dtype=bool)
    built_up = np.zeros((rows, cols), dtype=bool)
    arid = np.zeros((rows, cols), dtype=bool)

    offsets = (np.arange(SUBSAMPLES) + 0.5) / SUBSAMPLES * cell
    off_x, off_y = (o.ravel() for o in np.meshgrid(offsets, offsets, indexing="ij"))
    col_centres = origin_y + (np.arange(cols) + 0.5) * cell

    for start in range(0, rows, ROW_CHUNK):
        stop = min(start + ROW_CHUNK, rows)
        # Which cells of the band are on land.
        band_x = origin_x + (np.arange(start, stop) + 0.5) * cell
        xx = np.repeat(band_x, cols)
        yy = np.tile(col_centres, stop - start)
        on_land = shapely.contains_xy(land, xx, yy) & ~shapely.contains_xy(sea, xx, yy)
        on_land = on_land.reshape(stop - start, cols)
        land_mask[start:stop] = on_land
        cell_rows, cell_cols = np.nonzero(on_land)
        if cell_rows.size == 0:
            continue
        cell_rows += start

        # Samples of every land cell in the band, (cells, samples).
        sx = (origin_x + cell_rows * cell)[:, np.newaxis] + off_x
        sy = (origin_y + cell_cols * cell)[:, np.newaxis] + off_y
        lat, lon = to_latlon.transform(sx, sy)
        lat = np.asarray(lat)
        lon = np.asarray(lon)

        elevation = np.full(lat.shape, np.nan, dtype=np.float32)
        slope = np.full(lat.shape, np.nan, dtype=np.float32)
        for tile_lat, tile_lon in tile_groups(lat, lon, DEM_TILE):
            dem = dem_tiles.get(tile_lat, tile_lon)
            if not isinstance(dem, DemTile):
                continue
            inside = (
                (lat >= tile_lat)
                & (lat < tile_lat + DEM_TILE)
                & (lon >= tile_lon)
                & (lon < tile_lon + DEM_TILE)
            )
            elevation[inside] = dem.elevation.sample(lat[inside], lon[inside])
            slope[inside] = dem.slope.sample(lat[inside], lon[inside])

        cover = np.zeros(lat.shape, dtype=np.uint8)
        for tile_lat, tile_lon in tile_groups(lat, lon, WORLDCOVER_TILE):
            raster = cover_tiles.get(tile_lat, tile_lon)
            if not isinstance(raster, Raster):
                continue
            inside = (
                (lat >= tile_lat)
                & (lat < tile_lat + WORLDCOVER_TILE)
                & (lon >= tile_lon)
                & (lon < tile_lon + WORLDCOVER_TILE)
            )
            cover[inside] = raster.sample(lat[inside], lon[inside])

        # Reduce each cell's samples.
        has_dem = ~np.isnan(elevation)
        dem_count = has_dem.sum(axis=1)
        known = dem_count > 0
        steep_share = (np.nan_to_num(slope) > STEEP_SLOPE_DEGREES).sum(
            axis=1
        ) / np.maximum(dem_count, 1)
        high = np.where(has_dem, elevation, -np.inf).max(axis=1)
        low = np.where(has_dem, elevation, np.inf).min(axis=1)
        elevation_range = np.where(known, high - low, 0)
        steep[cell_rows, cell_cols] = known & (
            (steep_share > STEEP_SAMPLE_SHARE)
            | (elevation_range > STEEP_ELEVATION_RANGE)
        )

        has_cover = cover != 0
        cover_count = np.maximum(has_cover.sum(axis=1), 1)
        built_up[cell_rows, cell_cols] = (cover == WORLDCOVER_BUILT_UP).sum(
            axis=1
        ) / cover_count > BUILT_UP_SHARE
        arid[cell_rows, cell_cols] = (
            (cover == WORLDCOVER_BARE) | (cover == WORLDCOVER_SHRUBLAND)
        ).sum(axis=1) / cover_count > 0.5

    result = FarpTerrain(origin_x, origin_y, cell, steep, built_up, arid)
    path = THEATERS_DIR / name / FARP_TERRAIN_FILE
    result.save(path)
    land_cells = max(int(land_mask.sum()), 1)
    return (
        f"{name}: {rows}x{cols} cells, wrote {path} "
        f"({path.stat().st_size / 1024:.0f} KB) in {time.time() - started:.0f}s: "
        f"steep {100 * int(steep.sum()) / land_cells:.0f}%, "
        f"built up {100 * int(built_up.sum()) / land_cells:.1f}%, "
        f"arid {100 * int(arid.sum()) / land_cells:.0f}% of land"
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("theaters", nargs="*", help="Theater directory names.")
    parser.add_argument(
        "--jobs", type=int, default=3, help="Theaters to generate in parallel."
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE_DIR,
        help="Where downloaded tiles are kept.",
    )
    args = parser.parse_args()
    names = args.theaters or sorted(p.name for p in THEATERS_DIR.iterdir())
    if args.jobs <= 1:
        for name in names:
            logging.info(generate(name, args.cache_dir))
        return
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {pool.submit(generate, name, args.cache_dir): name for name in names}
        for future in as_completed(futures):
            try:
                logging.info(future.result())
            except Exception:
                logging.exception(f"{futures[future]} failed")


if __name__ == "__main__":
    main()
