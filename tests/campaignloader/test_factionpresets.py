"""Presets made from a faction's own aircraft, by base kind and band."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.campaignloader.airwingpreset import Band, BaseKind, RankedBase
from game.campaignloader.factionpresets import (
    BOMBERS,
    faction_presets,
    family,
    presets_for_base,
)
from game.dcs.aircrafttype import AircraftType

NAMES = [
    "F/A-18C Hornet (Lot 20)",
    "F-14B Tomcat",
    "E-2C Hawkeye",
    "AV-8B Harrier II Night Attack",
    "F-15C Eagle",
    "F-16CM Fighting Falcon (Block 50)",
    "A-10C Thunderbolt II (Suite 7)",
    "AH-64D Apache Longbow",
    "CH-47F Block I",
    "KC-135 Stratotanker",
    "E-3A",
    "B-52H Stratofortress",
]


@pytest.fixture(scope="module")
def faction(tmp_path_factory: pytest.TempPathFactory) -> Any:
    from game import persistency

    persistency.setup(
        str(tmp_path_factory.mktemp("saved")),
        prefer_liberation_payloads=False,
        port=16885,
    )
    try:
        aircraft = [AircraftType.named(n) for n in NAMES]
    except KeyError as ex:  # pragma: no cover - data missing
        pytest.skip(f"aircraft data missing: {ex}")
    return SimpleNamespace(name="Test", all_aircrafts=aircraft)


def _by_name(faction: Any) -> dict[str, Any]:
    return {p.name: p.groups[0] for p in faction_presets(faction)}


def test_carrier_wings_fly_carrier_jets_only(faction: Any) -> None:
    group = _by_name(faction)["Carrier air wing"]
    assert group.base is BaseKind.CARRIER
    types = [AircraftType.named(s.aircraft[0]) for s in group.squadrons]
    assert all(t.carrier_capable for t in types)
    # STOVL jets go to the LHA while carrier jets can fill the slot.
    assert "AV-8B Harrier II Night Attack" not in {t.variant_id for t in types}
    assert "E-2C Hawkeye" in {t.variant_id for t in types}
    # Under the 90 spots of the deck.
    assert sum(s.max_size for s in group.squadrons) <= 90


def test_bombers_only_fill_bomber_slots(faction: Any) -> None:
    presets = _by_name(faction)
    for name, group in presets.items():
        for config in group.squadrons:
            if config.aircraft[0] in BOMBERS:
                assert name in ("Heavy strike", "Strategic bombers"), name


def test_a_second_slot_takes_another_airframe(faction: Any) -> None:
    group = _by_name(faction)["Rear air defense"]
    fighters = [s.aircraft[0] for s in group.squadrons[:2]]
    assert len(set(fighters)) > 1


def test_family_groups_variants_and_ai_copies() -> None:
    def f(name: str) -> str:
        return family(SimpleNamespace(variant_id=name))  # type: ignore[arg-type]

    assert f("AH-64D Apache Longbow (AI)") == f("AH-64D Apache Longbow") == "AH-64"
    assert f("F-14B(U) Tomcat") == "F-14"
    assert f("[CH] Tu-160M2") == "Tu-160"


def _ranked(kind: BaseKind, band: Any = None, operates: Any = None) -> RankedBase:
    base = SimpleNamespace(name="Base", can_operate=operates or (lambda aircraft: True))
    return RankedBase(base, kind, 50.0, 1 if band else None, band)  # type: ignore[arg-type]


def test_each_base_is_offered_presets_for_it(faction: Any) -> None:
    front = [
        c.base_preset.preset.name
        for c in presets_for_base(faction, _ranked(BaseKind.AIRFIELD, Band.FRONT), 2005)
    ]
    rear = [
        c.base_preset.preset.name
        for c in presets_for_base(faction, _ranked(BaseKind.AIRFIELD, Band.REAR), 2005)
    ]
    assert front[0] == "Close air support" and "Support" not in front
    assert rear[0] in ("Support", "Heavy strike", "Rear air defense")
    assert "Close air support" not in rear


def test_a_helicopter_only_base_gets_helicopter_presets(faction: Any) -> None:
    helipad = _ranked(BaseKind.AIRFIELD, Band.FRONT, lambda a: a.helicopter)
    names = [
        c.base_preset.preset.name for c in presets_for_base(faction, helipad, 2005)
    ]
    assert names == ["Helicopter base"]
