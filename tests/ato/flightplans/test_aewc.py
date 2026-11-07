from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional, cast

from dcs import Point
from dcs.terrain import PersianGulf
from shapely.geometry import Point as ShapelyPoint, box

from game.ato.flight import Flight
from game.ato.flightplans.aewc import Builder
from game.utils import Heading, nautical_miles


class _BoxNavMesh:
    """A navmesh that is a single square, centred on the origin."""

    def __init__(self, half_size_nm: float) -> None:
        half = nautical_miles(half_size_nm).meters
        self.poly = box(-half, -half, half, half)

    def localize(self, point: Point) -> Optional[Any]:
        if self.poly.intersects(ShapelyPoint(point.x, point.y)):
            return self.poly
        return None


def _builder(navmesh: _BoxNavMesh) -> Builder:
    flight = SimpleNamespace(
        coalition=SimpleNamespace(nav_mesh=navmesh),
        package=SimpleNamespace(target="Test Base"),
    )
    builder = Builder.__new__(Builder)
    builder.flight = cast(Flight, flight)
    return builder


def _racetrack(navmesh: _BoxNavMesh, orbit_nm: float) -> tuple[Point, Point]:
    return _builder(navmesh)._racetrack_on_navmesh(
        Point(0, 0, PersianGulf()),
        Heading.from_degrees(0),
        nautical_miles(orbit_nm),
        nautical_miles(30).meters,
    )


def test_orbit_that_fits_is_unchanged() -> None:
    start, end = _racetrack(_BoxNavMesh(200), orbit_nm=100)
    # Heading north, the racetrack is centred 100nm north of the target.
    assert round(start.x) == round(end.x) == round(nautical_miles(100).meters)


def test_orbit_off_the_navmesh_is_pulled_back_onto_it() -> None:
    # Regression test: a target deep inside the enemy threat zone put the orbit
    # 250nm out, past the edge of the navmesh ("Destination point ... is outside
    # the navmesh"), which aborted the turn.
    navmesh = _BoxNavMesh(200)
    start, end = _racetrack(navmesh, orbit_nm=250)
    assert navmesh.localize(start) is not None
    assert navmesh.localize(end) is not None
    assert start.x <= nautical_miles(200).meters


def test_orbit_with_no_valid_position_is_left_alone() -> None:
    # The racetrack is wider than the navmesh, so nothing fits. The ideal orbit
    # is kept and routing fails as before (the package is then scrubbed).
    start, end = _racetrack(_BoxNavMesh(10), orbit_nm=100)
    assert round(start.x) == round(nautical_miles(100).meters)
