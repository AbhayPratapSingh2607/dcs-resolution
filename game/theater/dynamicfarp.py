"""Player-established forward arming and refuelling points.

Unlike campaign-defined FOBs, these control points are created (and dismantled)
during the campaign. They have no supply routes or front lines, cannot be
captured, and only host helicopter *detachments* split from existing squadrons.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, TYPE_CHECKING

from dcs.mapping import Point

from game.point_with_heading import PointWithHeading
from game.sidc import Entity, LandInstallationEntity, SymbolSet
from game.utils import Heading
from .controlpoint import ControlPointType, Fob
from .player import Player

if TYPE_CHECKING:
    from game.runways import RunwayData
    from game.weather.conditions import Conditions
    from .conflicttheater import ConflictTheater


class FarpKind(Enum):
    """The two FARP types. They follow the same rules and differ only in how many
    helicopters they can hold, what they cost, and how they look.

    The values are kept from the original "frontline"/"covert" names so existing
    saves keep loading.
    """

    #: "Wet Wing": the larger FARP, set up by a C-130.
    WET_WING = "frontline"
    #: "Fat Cow": the smaller FARP, set up by a CH-47.
    FAT_COW = "covert"

    @property
    def display_name(self) -> str:
        return "Wet Wing" if self is FarpKind.WET_WING else "Fat Cow"


#: Spacing in meters between the individual pads of a dynamic FARP.
PAD_SPACING = 60

#: Number of helicopter slots provided by a Fat Cow FARP (its layout has 2 pads).
FAT_COW_CAPACITY = 2


@dataclass(frozen=True)
class LayoutObject:
    """One visible object of a FARP layout.

    Offsets are relative to the FARP position and heading: ``forward`` along the
    FARP heading (negative is aft), ``right`` to its right.
    """

    key: str
    role: str
    forward: float
    right: float
    heading_offset: float = 0.0


#: How far ahead of each pad its fire extinguisher and crew stand, in meters.
#: Clears the front rotor of a CH-47 on the pad by about 10m.
PAD_EXTINGUISHER_DISTANCE = 25.0


def pad_fire_crew(index: int, forward: float, right: float) -> list[LayoutObject]:
    """A fire extinguisher just ahead of a pad, with two crew facing the pad.

    ``forward`` and ``right`` are the pad's own offsets in the layout frame.
    """
    ahead = forward + PAD_EXTINGUISHER_DISTANCE
    return [
        LayoutObject(f"extinguisher_{index}", "extinguisher", ahead, right),
        LayoutObject(f"crew_{index}_1", "soldier", ahead, right - 2, 180),
        LayoutObject(f"crew_{index}_2", "soldier", ahead, right + 2, 180),
    ]


def guard_ring(
    center: tuple[float, float], front_back: float, side: float
) -> list[LayoutObject]:
    """Six guards around a parked aircraft, facing outward: two ahead of the nose,
    two behind the tail/ramp and one on each side."""
    forward, right = center
    return [
        LayoutObject("guard_1", "soldier", forward + front_back, right - 8, 0),
        LayoutObject("guard_2", "soldier", forward + front_back, right + 8, 0),
        LayoutObject("guard_3", "soldier", forward - front_back, right - 8, 180),
        LayoutObject("guard_4", "soldier", forward - front_back, right + 8, 180),
        LayoutObject("guard_5", "soldier", forward, right - side, 270),
        LayoutObject("guard_6", "soldier", forward, right + side, 90),
    ]


# Fat Cow (the smaller FARP, set up by a CH-47)

#: Fat Cow landing spots, (forward, right) in meters. The visible layout is based
#: on the CG FATCOW script (Don Rudi / C. Gurk). The two pads sit side by side,
#: 100m aft and 70m apart, with the fuel between them.
FATCOW_PADS: list[tuple[float, float]] = [(-100, -35), (-100, 35)]

#: Where the CH-47 that set up the FARP is parked: just ahead of the generator
#: (50m aft), its ramp about 20m from it.
CHINOOK_POSITION = (-15.0, 0.0)

#: The visible ground layout of the Fat Cow FARP. Roles are mapped to DCS types by
#: the mission generator ("soldier" and "manpad" depend on the coalition).
FATCOW_LAYOUT: list[LayoutObject] = [
    # The CH-47 that flew in and set up the FARP, facing the front line with its
    # ramp toward the generator and helipads.
    LayoutObject("chinook", "fatcow_helicopter", *CHINOOK_POSITION),
    # Fuel between the two pads.
    LayoutObject("apfc_fuel", "apfc_fuel", -100, -10),
    LayoutObject("fuel", "fuel_depot", -100, 10),
    # Ammo just behind the fuel, so the Fat Cow can rearm like the Wet Wing.
    LayoutObject("ammo", "ammo", -115, 0),
    LayoutObject("generator", "generator", -50, 0),
    # Guards clear of the CH-47's rotors.
    *guard_ring(CHINOOK_POSITION, front_back=20, side=16),
    # Stinger team 50m ahead of the CH-47's nose.
    LayoutObject("manpad", "manpad", CHINOOK_POSITION[0] + 50, CHINOOK_POSITION[1]),
    *[
        obj
        for i, (forward, right) in enumerate(FATCOW_PADS)
        for obj in pad_fire_crew(i, forward, right)
    ],
]

#: Layout objects that hold the FARP's fuel. Destroying all of them destroys the
#: FARP.
FATCOW_FUEL_KEYS = ("apfc_fuel", "fuel")


# Wet Wing (the larger FARP, set up by a C-130)

#: Where the C-130 that set up the FARP is parked.
C130_POSITION = (100.0, 30.0)

#: Wet Wing dressing: the C-130 that landed at the austere site to set up the
#: FARP, parked 100m ahead and 30m right of the FARP point facing the front line,
#: with its ramp toward the helipads. The Wet Wing's fuel, ammo and windsock and
#: each pad's fire crew are placed by the mission generator.
WET_WING_LAYOUT: list[LayoutObject] = [
    LayoutObject("c130", "transport_plane", *C130_POSITION),
    # Guards clear of the C-130's nose, ramp and 40m wingspan.
    *guard_ring(C130_POSITION, front_back=22, side=26),
    LayoutObject("generator", "generator", 35, -15),
    # Stinger team ahead of the C-130's nose.
    LayoutObject("manpad", "manpad", C130_POSITION[0] + 50, C130_POSITION[1]),
]

#: DCS livery of the Wet Wing's C-130.
C130_LIVERY = "us air force"


def layout_point(
    origin: Point, heading: Heading, forward: float, right: float
) -> Point:
    return origin.point_from_heading(heading.degrees, forward).point_from_heading(
        heading.right.degrees, right
    )


def fatcow_object_name(farp_name: str, key: str) -> str:
    """Static group name of a Fat Cow layout object."""
    return f"{farp_name} fatcow {key}"


FARP_CALLSIGNS = [
    "Anvil",
    "Badger",
    "Bandit",
    "Cobra",
    "Coyote",
    "Dagger",
    "Falcon",
    "Granite",
    "Hammer",
    "Hornet",
    "Jackal",
    "Lancer",
    "Mongoose",
    "Nomad",
    "Outlaw",
    "Raven",
    "Saber",
    "Scorpion",
    "Spartan",
    "Talon",
    "Thunder",
    "Viper",
    "Warhorse",
    "Wolfpack",
]


class DynamicFarp(Fob):
    def __init__(
        self,
        name: str,
        at: Point,
        heading: Heading,
        theater: ConflictTheater,
        owner: Player,
        kind: FarpKind,
        capacity: int,
        established_turn: int,
    ) -> None:
        super().__init__(name, at, theater, owner)
        self.cptype = ControlPointType.FARP
        self.kind = kind
        self.farp_heading = heading
        self.established_turn = established_turn
        self.capacity = capacity
        self._layout_pads(capacity)

    def __setstate__(self, state: dict[str, Any]) -> None:
        # Fat Cows no longer expire.
        state.pop("expires_on_turn", None)
        self.__dict__.update(state)
        if "capacity" not in state:
            self.capacity = (
                len(self.helipads)
                + 4 * len(self.helipads_quad)
                + len(self.helipads_invisible)
            )
        # Pad positions are derived from the layout data, which may have changed
        # since the FARP was established. Re-derive them on load so the pads always
        # line up with the props, which are placed from the current layout when the
        # mission is generated.
        self.helipads = []
        self.helipads_quad = []
        self.helipads_invisible = []
        self._layout_pads(self.capacity)

    def _layout_pads(self, capacity: int) -> None:
        """Generates the helipad layout for this FARP.

        A Wet Wing gets a 4-pad FARP plus single pads for any additional capacity.
        A Fat Cow uses its layout's two pads.
        """
        heading = self.farp_heading
        if self.is_fat_cow:
            for forward, right in FATCOW_PADS:
                pos = layout_point(self.position, heading, forward, right)
                self.helipads_invisible.append(
                    PointWithHeading.from_point(pos, heading)
                )
            return
        remaining = capacity
        if remaining >= 4:
            self.helipads_quad.append(
                PointWithHeading.from_point(self.position, heading)
            )
            remaining -= 4
        # Lay out extra single pads in a line perpendicular to the FARP heading,
        # starting far enough out to clear the quad FARP footprint.
        offset = PAD_SPACING * 2 if self.helipads_quad else 0
        side = heading.right
        for i in range(remaining):
            pos = self.position.point_from_heading(
                side.degrees, offset + i * PAD_SPACING
            )
            self.helipads_invisible.append(PointWithHeading.from_point(pos, heading))

    @property
    def is_dynamic_farp(self) -> bool:
        return True

    @property
    def is_fat_cow(self) -> bool:
        """Whether this FARP uses the Fat Cow (CH-47) layout."""
        return self.kind is FarpKind.FAT_COW

    @property
    def upkeep_per_turn(self) -> int:
        settings = self.coalition.game.settings
        if self.is_fat_cow:
            return settings.fat_cow_farp_upkeep
        return settings.wet_wing_farp_upkeep

    def active_runway(
        self,
        theater: ConflictTheater,
        conditions: Conditions,
        dynamic_runways: dict[str, RunwayData],
    ) -> RunwayData:
        """The FARP's briefing entry (name and ATC frequency), registered by the
        mission generator like a carrier's."""
        runway = dynamic_runways.get(self.full_name)
        if runway is not None:
            return runway
        return self.stub_runway_data()

    @property
    def symbol_set_and_entity(self) -> tuple[SymbolSet, Entity]:
        return (
            SymbolSet.LAND_INSTALLATIONS,
            LandInstallationEntity.HELICOPTER_LANDING_SITE,
        )

    @property
    def can_deploy_ground_units(self) -> bool:
        return False

    @property
    def income_per_turn(self) -> int:
        return 0

    @property
    def category(self) -> str:
        return "farp"
