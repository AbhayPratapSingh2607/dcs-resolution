"""Boom and drogue tankers: which aircraft use which, and where the planner
puts each kind of tanker track (game/commander/jfacc/tankers.py)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator

import pytest
from dcs import planes

from game import persistency
from game.ato.flighttype import FlightType
from game.commander.jfacc.tankers import tanker_tracks
from game.dcs.aircrafttype import AircraftType
from game.sim.combat.model.fuel import (
    RefuelingSystem,
    receiver_system,
    tanker_system,
)

BOOM = RefuelingSystem.BOOM
DROGUE = RefuelingSystem.DROGUE


@pytest.fixture(autouse=True)
def _aircraft_data(tmp_path: Path) -> Iterator[None]:
    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16884)
    yield


def _type(dcs_type: Any) -> AircraftType:
    return next(AircraftType.for_dcs_type(dcs_type))


def test_tankers_by_system() -> None:
    assert tanker_system(_type(planes.KC_135)) is BOOM
    assert tanker_system(_type(planes.KC135MPRS)) is DROGUE
    assert tanker_system(_type(planes.KC130)) is DROGUE
    assert tanker_system(_type(planes.S_3B_Tanker)) is DROGUE
    assert tanker_system(_type(planes.IL_78M)) is DROGUE
    # Not a tanker.
    assert tanker_system(_type(planes.F_16C_50)) is None


def test_receivers_by_system() -> None:
    for boom in (planes.F_16C_50, planes.F_15E, planes.A_10C_2, planes.B_1B):
        assert receiver_system(_type(boom)) is BOOM, boom.id
    for probe in (planes.FA_18C_hornet, planes.F_14B, planes.AV8BNA, planes.Su_33):
        assert receiver_system(_type(probe)) is DROGUE, probe.id
    # No air-to-air refueling.
    assert receiver_system(_type(planes.MiG_29S)) is None


# ----------------------------------------------------------------- tracks


def _base(name: str, fleet: bool = False) -> Any:
    return SimpleNamespace(name=name, is_fleet=fleet)


def _squadron(dcs_type: Any, base: Any, owned: int = 12, tanker: bool = False) -> Any:
    tasks = {FlightType.REFUELING} if tanker else set()
    return SimpleNamespace(
        aircraft=_type(dcs_type),
        location=base,
        owned_aircraft=owned,
        can_auto_assign=lambda task: task in tasks,
    )


def _coalition(*squadrons: Any) -> Any:
    return SimpleNamespace(
        air_wing=SimpleNamespace(iter_squadrons=lambda: iter(squadrons))
    )


FRONT = _base("Front AB")
REAR = _base("Rear AB")
CARRIER = _base("CVN-72", fleet=True)


def _summary(tracks: list[Any]) -> list[tuple[str, Any, int]]:
    return [(t.anchor.name, t.system, t.receivers) for t in tracks]


def test_boom_track_ashore_and_drogue_track_off_the_carrier() -> None:
    coalition = _coalition(
        _squadron(planes.F_16C_50, REAR, 24),
        _squadron(planes.FA_18C_hornet, CARRIER, 12),
        _squadron(planes.F_14B, CARRIER, 10),
        _squadron(planes.KC_135, REAR, 4, tanker=True),
        _squadron(planes.S_3B_Tanker, CARRIER, 4, tanker=True),
    )
    assert _summary(tanker_tracks(coalition, FRONT)) == [
        ("Front AB", BOOM, 24),
        ("CVN-72", DROGUE, 22),
    ]


def test_probe_aircraft_ashore_get_a_drogue_track_off_the_front() -> None:
    coalition = _coalition(
        _squadron(planes.F_15E, REAR, 12),
        _squadron(planes.AV8BNA, FRONT, 8),
        _squadron(planes.KC_135, REAR, 2, tanker=True),
        _squadron(planes.KC130, REAR, 2, tanker=True),
    )
    assert _summary(tanker_tracks(coalition, FRONT)) == [
        ("Front AB", BOOM, 12),
        ("Front AB", DROGUE, 8),
    ]


def test_no_track_for_a_system_without_its_own_tankers() -> None:
    # Only drogue tankers: the F-16s can't use them, the Hornets can.
    coalition = _coalition(
        _squadron(planes.F_16C_50, REAR, 24),
        _squadron(planes.FA_18C_hornet, CARRIER, 12),
        _squadron(planes.S_3B_Tanker, CARRIER, 4, tanker=True),
    )
    assert _summary(tanker_tracks(coalition, FRONT)) == [("CVN-72", DROGUE, 12)]
    # No tankers at all: nothing.
    assert tanker_tracks(_coalition(_squadron(planes.F_16C_50, REAR)), FRONT) == []


def test_tanker_squadrons_with_refueling_off_dont_count() -> None:
    kc135 = _squadron(planes.KC_135, REAR, 4)
    coalition = _coalition(_squadron(planes.F_16C_50, REAR), kc135)
    assert tanker_tracks(coalition, FRONT) == []


def test_most_receivers_first_up_to_the_limit() -> None:
    carrier2 = _base("CVN-73", fleet=True)
    coalition = _coalition(
        _squadron(planes.F_16C_50, REAR, 6),
        _squadron(planes.FA_18C_hornet, CARRIER, 24),
        _squadron(planes.FA_18C_hornet, carrier2, 12),
        _squadron(planes.KC_135, REAR, 2, tanker=True),
        _squadron(planes.S_3B_Tanker, CARRIER, 2, tanker=True),
    )
    tracks = tanker_tracks(coalition, FRONT, max_tracks=2)
    assert _summary(tracks) == [("CVN-72", DROGUE, 24), ("CVN-73", DROGUE, 12)]


def test_without_receivers_the_old_single_track() -> None:
    coalition = _coalition(_squadron(planes.KC_135, REAR, 2, tanker=True))
    tracks = tanker_tracks(coalition, FRONT)
    assert _summary(tracks) == [("Front AB", None, 0)]
    assert tracks[0].reason == "Theater tanker track"
