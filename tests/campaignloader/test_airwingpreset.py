"""Air wing presets: parsing, base placement and turn-0 purchasing."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from game import persistency
from game.ato.flighttype import FlightType
from game.campaignloader import airwingpreset
from game.campaignloader.airwingpreset import (
    AirWingPreset,
    AirWingPresetLoader,
    BUILTIN_PRESET_DIR,
    BaseKind,
    Placement,
    PresetPlacer,
    deployed_at_start,
)
from game.dcs.countries import country_with_name
from game.theater.controlpoint import ControlPointType
from game.theater.player import Player

# --- Fakes -----------------------------------------------------------------------


class _Aircraft:
    def __init__(self, name: str, carrier: bool = False, price: int = 10) -> None:
        self.variant_id = name
        self.carrier_capable = carrier
        self.lha_capable = False
        self.helicopter = False
        self.flyable = False
        self.price = price

    def __str__(self) -> str:
        return self.variant_id


HORNET = _Aircraft("Hornet", carrier=True)
EAGLE = _Aircraft("Eagle")
TANKER = _Aircraft("Tanker")
AIRCRAFT = {a.variant_id: a for a in (HORNET, EAGLE, TANKER)}


class _FakeAircraftType:
    @staticmethod
    def named(name: str) -> Any:
        return AIRCRAFT[name]


class _Position:
    def __init__(self, x: float) -> None:
        self.x = x

    def distance_to_point(self, other: _Position) -> float:
        return abs(self.x - other.x)


class _Base:
    def __init__(
        self,
        name: str,
        x: float,
        owner: Player,
        carrier: bool = False,
        parking: int = 100,
    ) -> None:
        self.name = name
        self.position = _Position(x)
        self.captured = owner
        self.is_carrier = carrier
        self.is_lha = False
        self.is_fleet = carrier
        self.cptype = (
            ControlPointType.AIRCRAFT_CARRIER_GROUP
            if carrier
            else ControlPointType.AIRBASE
        )
        self.parking = parking

    def can_operate(self, aircraft: Any) -> bool:
        return bool(aircraft.carrier_capable == self.is_carrier)

    def total_aircraft_parking(self, parking_type: Any) -> int:
        return self.parking

    def __str__(self) -> str:
        return self.name


_base = _Base


def _game_and_coalition(
    bases: list[Any], faction_aircraft: list[Any]
) -> tuple[Any, Any]:
    theater = SimpleNamespace(
        control_points_for=lambda player: [b for b in bases if b.captured is player]
    )
    game = SimpleNamespace(
        theater=theater, settings=SimpleNamespace(ground_start_ai_planes=False)
    )
    coalition = SimpleNamespace(
        player=Player.BLUE,
        faction=SimpleNamespace(all_aircrafts=faction_aircraft),
        air_wing=SimpleNamespace(iter_squadrons=lambda: []),
    )
    return game, coalition


def _placer(
    bases: list[Any], faction_aircraft: list[Any], add_missing: bool = False
) -> PresetPlacer:
    game, coalition = _game_and_coalition(bases, faction_aircraft)
    return PresetPlacer(
        cast(Any, game), cast(Any, coalition), add_missing_aircraft=add_missing
    )


def _preset(groups: list[dict[str, Any]]) -> AirWingPreset:
    return AirWingPreset.from_data({"name": "Test", "groups": groups})


@pytest.fixture(autouse=True)
def _fake_aircraft(monkeypatch: pytest.MonkeyPatch, request: Any) -> None:
    # The builtin-preset test checks names against the real aircraft registry.
    if "builtin" not in request.node.name:
        monkeypatch.setattr(airwingpreset, "AircraftType", _FakeAircraftType)


# --- Parsing ---------------------------------------------------------------------


def test_parse_defaults() -> None:
    preset = _preset(
        [
            {
                "base": "carrier",
                "squadrons": [{"aircraft": "Hornet", "primary": "BARCAP"}],
            },
            {"squadrons": [{"aircraft": ["Eagle"], "primary": "Strike", "buy": 40}]},
        ]
    )
    carrier, airfield = preset.groups
    assert carrier.base is BaseKind.CARRIER and carrier.count == 1
    assert airfield.base is BaseKind.AIRFIELD and airfield.count is None
    assert airfield.placement is Placement.ANY
    hornet = carrier.squadrons[0]
    assert hornet.aircraft == ["Hornet"]
    assert hornet.primary is FlightType.BARCAP
    # buy defaults to the squadron size, and can't exceed it.
    assert hornet.aircraft_to_buy == 12
    assert airfield.squadrons[0].aircraft_to_buy == 12


def test_builtin_presets_use_known_aircraft_and_countries(tmp_path: Path) -> None:
    from game.dcs.aircrafttype import AircraftType

    persistency.setup(str(tmp_path), prefer_liberation_payloads=False, port=16885)
    presets = list(AirWingPresetLoader.load_from(BUILTIN_PRESET_DIR))
    assert len(presets) == len(list(BUILTIN_PRESET_DIR.glob("*.yaml")))
    for preset in presets:
        for group in preset.groups:
            for squadron in group.squadrons:
                for name in squadron.aircraft:
                    AircraftType.named(name)  # raises KeyError on a typo
                if squadron.country is not None:
                    country_with_name(squadron.country)


# --- Placement -------------------------------------------------------------------


def test_carrier_and_airfield_placement() -> None:
    carrier = _base("CVN", 0, Player.BLUE, carrier=True)
    near = _base("Near", 90, Player.BLUE)
    far = _base("Far", 10, Player.BLUE)
    enemy = _base("Enemy", 100, Player.RED)
    placer = _placer([carrier, near, far, enemy], [HORNET, EAGLE, TANKER])
    plan = placer.resolve(
        _preset(
            [
                {
                    "base": "carrier",
                    "squadrons": [{"aircraft": ["Hornet"], "primary": "BARCAP"}],
                },
                {
                    "base": "airfield",
                    "placement": "front",
                    "squadrons": [{"aircraft": ["Eagle"], "primary": "CAS"}],
                },
                {
                    "base": "airfield",
                    "placement": "rear",
                    "squadrons": [{"aircraft": ["Tanker"], "primary": "Refueling"}],
                },
            ]
        )
    )
    assert plan.warnings == []
    assert [(p.aircraft, p.base) for p in plan.placements] == [
        (HORNET, carrier),
        (EAGLE, near),
        (TANKER, far),
    ]
    assert plan.total_cost == 3 * 12 * 10


def test_front_placement_overflows_to_next_base() -> None:
    near = _base("Near", 90, Player.BLUE, parking=12)
    far = _base("Far", 10, Player.BLUE, parking=100)
    enemy = _base("Enemy", 100, Player.RED)
    plan = _placer([near, far, enemy], [EAGLE]).resolve(
        _preset(
            [
                {
                    "placement": "front",
                    "squadrons": [
                        {"aircraft": ["Eagle"], "primary": "CAS"},
                        {"aircraft": ["Eagle"], "primary": "CAS"},
                    ],
                }
            ]
        )
    )
    assert [p.base for p in plan.placements] == [near, far]


def test_any_placement_spreads_over_bases() -> None:
    small = _base("Small", 0, Player.BLUE, parking=30)
    big = _base("Big", 50, Player.BLUE, parking=200)
    plan = _placer([small, big], [EAGLE]).resolve(
        _preset([{"squadrons": [{"aircraft": ["Eagle"], "primary": "CAS"}] * 4}])
    )
    # Alternates between bases while both have room; the small base fills at 2.
    assert [p.base.name for p in plan.placements] == ["Big", "Small", "Big", "Small"]


def test_missing_carrier_is_a_warning() -> None:
    plan = _placer([_base("Airfield", 0, Player.BLUE)], [HORNET]).resolve(
        _preset(
            [
                {
                    "base": "carrier",
                    "squadrons": [{"aircraft": ["Hornet"], "primary": "BARCAP"}],
                }
            ]
        )
    )
    assert plan.placements == []
    assert "No carrier" in plan.warnings[0]


def test_aircraft_missing_from_faction() -> None:
    bases = [_base("Airfield", 0, Player.BLUE)]
    preset = _preset([{"squadrons": [{"aircraft": ["Eagle"], "primary": "CAS"}]}])

    skipped = _placer(bases, [TANKER]).resolve(preset)
    assert skipped.placements == [] and len(skipped.warnings) == 1

    added = _placer(bases, [TANKER], add_missing=True).resolve(preset)
    assert [p.aircraft for p in added.placements] == [EAGLE]
    assert added.missing_aircraft == {EAGLE}


def test_mod_aircraft_are_never_added_to_the_faction() -> None:
    class ModType:
        pass

    ModType.__module__ = "pydcs_extensions.somemod"
    mod = _Aircraft("Mod")
    mod.dcs_unit_type = ModType  # type: ignore[attr-defined]
    AIRCRAFT["Mod"] = mod
    try:
        plan = _placer(
            [_base("Airfield", 0, Player.BLUE)], [], add_missing=True
        ).resolve(
            _preset([{"squadrons": [{"aircraft": ["Mod", "Eagle"], "primary": "CAS"}]}])
        )
    finally:
        del AIRCRAFT["Mod"]
    # The mod aircraft is skipped and the next (stock) preference is added instead.
    assert [p.aircraft for p in plan.placements] == [EAGLE]


def test_skip_warning_explains_each_rejected_aircraft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ModType:
        pass

    ModType.__module__ = "pydcs_extensions.somemod"
    mod = _Aircraft("Mod")
    mod.dcs_unit_type = ModType  # type: ignore[attr-defined]
    AIRCRAFT["Mod"] = mod
    monkeypatch.setattr(PresetPlacer, "squadron_def_aircraft", lambda self, n: None)
    try:
        placer = _placer([_base("Airfield", 0, Player.BLUE)], [HORNET])
        plan = placer.resolve(
            _preset(
                [
                    {
                        "squadrons": [
                            {
                                "aircraft": ["Mod", "Eagle", "Hornet", "Typo"],
                                "primary": "CAS",
                            }
                        ]
                    }
                ]
            )
        )
    finally:
        del AIRCRAFT["Mod"]
    assert plan.placements == []
    (warning,) = plan.warnings
    assert warning.startswith("Skipped Mod / Eagle / Hornet / Typo (airfield): ")
    assert "Mod: modded aircraft not selected" in warning
    assert "Eagle: aircraft not available to faction" in warning
    assert "Hornet: cannot operate from any owned airfield" in warning
    assert "Typo: unknown aircraft" in warning


def test_falls_back_to_next_preferred_aircraft() -> None:
    plan = _placer([_base("Airfield", 0, Player.BLUE)], [TANKER]).resolve(
        _preset([{"squadrons": [{"aircraft": ["Eagle", "Tanker"], "primary": "CAS"}]}])
    )
    assert [p.aircraft for p in plan.placements] == [TANKER]


# --- Deployed at the start (T2) ------------------------------------------------


def test_presets_deploy_their_number_and_nothing_is_bought() -> None:
    # A detachment deploys a few, a squadron its size, capped by size and parking.
    assert (
        deployed_at_start(4, squadrons_start_full=False, max_size=12, free_parking=100)
        == 4
    )
    assert (
        deployed_at_start(4, squadrons_start_full=True, max_size=12, free_parking=100)
        == 4
    )
    assert (
        deployed_at_start(20, squadrons_start_full=True, max_size=12, free_parking=100)
        == 12
    )
    assert (
        deployed_at_start(8, squadrons_start_full=True, max_size=12, free_parking=3)
        == 3
    )
    # Without a preset number: full when squadrons start full, else none.
    assert (
        deployed_at_start(0, squadrons_start_full=True, max_size=12, free_parking=100)
        == 12
    )
    assert (
        deployed_at_start(0, squadrons_start_full=False, max_size=12, free_parking=100)
        == 0
    )


# --- Bomber detachments (T3) ---------------------------------------------------


def _off_map(name: str) -> Any:
    base = _base(name, 500, Player.BLUE)
    base.cptype = ControlPointType.OFF_MAP
    base.can_operate = lambda aircraft: True  # type: ignore[method-assign]
    return base


BOMBERS = {
    "base": "off-map",
    "squadrons": [{"aircraft": ["Eagle"], "primary": "Strike", "size": 6, "buy": 4}],
}


def test_bombers_go_only_to_an_off_map_base() -> None:
    airfield = _base("Airfield", 0, Player.BLUE)
    plan = _placer([airfield, _off_map("Edge")], [EAGLE]).resolve(_preset([BOMBERS]))
    assert [str(p.base) for p in plan.placements] == ["Edge"]
    assert plan.placements[0].config.aircraft_to_buy == 4
    # Never at an airfield in the theater, and no warning without an off-map base.
    plan = _placer([airfield], [EAGLE]).resolve(_preset([BOMBERS]))
    assert plan.placements == [] and plan.warnings == []
    # Off-map bases aren't airfields for the other groups.
    plan = _placer([_off_map("Edge")], [EAGLE]).resolve(
        _preset(
            [
                {
                    "base": "airfield",
                    "squadrons": [{"aircraft": ["Eagle"], "primary": "BARCAP"}],
                }
            ]
        )
    )
    assert plan.placements == []


def test_builtin_bomber_detachments_only_in_air_force_presets() -> None:
    from game.campaignloader.airwingpreset import BUILTIN_PRESET_DIR, BaseKind

    with_bombers = sorted(
        p.stem
        for p in BUILTIN_PRESET_DIR.glob("*.yaml")
        if any(g.base is BaseKind.OFF_MAP for g in AirWingPreset.from_yaml(p).groups)
    )
    assert with_bombers == [
        "nato_coalition_2010",
        "russian_vks_2015",
        "soviet_vvs_1985",
        "usaf_aef_1991",
        "usaf_aef_2005",
    ]


# --- By location -------------------------------------------------------------


def _located(bases: list[Any]) -> tuple[Any, Any]:
    game, coalition = _game_and_coalition(bases, [HORNET, EAGLE, TANKER])
    game.theater.conflicts = lambda: []  # no ground war: the enemy bases
    for base in bases:
        base.is_dynamic_farp = False
    return game, coalition


def test_bases_are_ranked_closest_to_farthest_from_the_battle() -> None:
    from game.campaignloader.airwingpreset import Band, BaseKind, ranked_bases

    carrier = _base("CVN", 0, Player.BLUE, carrier=True)
    airfields = [_base(f"AB{x}", x * 1000, Player.BLUE) for x in (10, 90, 50)]
    enemy = _base("Enemy", 100_000, Player.RED)
    game, coalition = _located([carrier, *airfields, enemy])
    ranked = ranked_bases(game, coalition)
    assert [r.base.name for r in ranked] == ["CVN", "AB90", "AB50", "AB10"]
    assert ranked[0].kind is BaseKind.CARRIER and ranked[0].rank is None
    assert [r.band for r in ranked[1:]] == [Band.FRONT, Band.MIDDLE, Band.REAR]
    assert ranked[1].label == "#1 Front · AB90 (10 km from the battle)"
    assert ranked[0].label.startswith("Carrier · CVN")


def test_a_base_is_offered_the_presets_made_for_it() -> None:
    from game.campaignloader.airwingpreset import (
        base_presets_for,
        ranked_bases,
    )

    carrier = _base("CVN", 0, Player.BLUE, carrier=True)
    front = _base("Front", 90_000, Player.BLUE)
    rear = _base("Rear", 0, Player.BLUE)
    enemy = _base("Enemy", 100_000, Player.RED)
    game, coalition = _located([carrier, front, rear, enemy])
    preset = _preset(
        [
            {
                "base": "carrier",
                "squadrons": [{"aircraft": ["Hornet"], "primary": "BARCAP"}],
            },
            {
                "base": "airfield",
                "placement": "front",
                "squadrons": [{"aircraft": ["Eagle"], "primary": "BARCAP"}],
            },
            {
                "base": "airfield",
                "placement": "rear",
                "squadrons": [{"aircraft": ["Tanker"], "primary": "BARCAP"}],
            },
        ]
    )
    by_name = {r.base.name: r for r in ranked_bases(game, coalition)}

    def offered(name: str) -> list[str]:
        return [
            b.group.squadrons[0].aircraft[0]
            for b in base_presets_for([preset], by_name[name], 2000)
        ]

    assert offered("CVN") == ["Hornet"]
    assert offered("Front") == ["Eagle"]
    assert offered("Rear") == ["Tanker"]


def test_a_base_preset_puts_every_squadron_on_that_base() -> None:
    from game.campaignloader.airwingpreset import (
        BasePresetPlacer,
        base_presets_for,
        ranked_bases,
    )

    near = _base("Near", 90_000, Player.BLUE)
    far = _base("Far", 0, Player.BLUE)
    middle = _base("Middle", 50_000, Player.BLUE)
    enemy = _base("Enemy", 100_000, Player.RED)
    game, coalition = _located([near, middle, far, enemy])
    coalition.air_wing.squadrons = {}
    preset = _preset(
        [
            {
                "base": "airfield",
                "placement": "any",
                "squadrons": [
                    {"aircraft": ["Eagle"], "primary": "BARCAP"},
                    {"aircraft": ["Tanker"], "primary": "BARCAP"},
                ],
            }
        ]
    )
    ranked = next(r for r in ranked_bases(game, coalition) if r.base is far)
    (base_preset,) = base_presets_for([preset], ranked, 2000)
    plan = BasePresetPlacer(game, coalition, far).resolve(base_preset.as_preset())
    assert plan.warnings == []
    assert [p.base for p in plan.placements] == [far, far]


def test_a_base_preset_is_trimmed_to_the_parking() -> None:
    from game.campaignloader.airwingpreset import BasePresetPlacer

    small = _base("Small", 90_000, Player.BLUE, parking=15)
    enemy = _base("Enemy", 100_000, Player.RED)
    game, coalition = _located([small, enemy])
    coalition.air_wing.squadrons = {}
    preset = _preset(
        [
            {
                "base": "airfield",
                "squadrons": [
                    {"aircraft": ["Eagle"], "primary": "BARCAP", "size": 12},
                    {"aircraft": ["Tanker"], "primary": "Refueling", "size": 12},
                    {"aircraft": ["Eagle"], "primary": "CAS", "size": 12},
                ],
            }
        ]
    )
    plan = BasePresetPlacer(game, coalition, small).resolve(preset)
    # 12 fit, the next is trimmed to the 3 spots left, the last is left out.
    assert [p.config.max_size for p in plan.placements] == [12, 3]
    assert plan.warnings == []
    assert len(plan.notes) == 2 and "trimmed to 3 of 12" in plan.notes[0]
