"""Classify mission targets into target systems and classes (JIPTL vocabulary)."""

from __future__ import annotations

from typing import Optional, TYPE_CHECKING

from .profile import TargetSystem

if TYPE_CHECKING:
    from game.theater import MissionTarget
    from game.theater.theatergroundobject import TheaterGroundObject

#: Target class -> hardness used by weaponeering.
HARDNESS = {
    "sam_lorad": "medium",
    "sam_merad": "medium",
    "sam_shorad": "soft",
    "ewr": "soft",
    "c2_node": "hard",
    "power": "medium",
    "factory": "area",
    "ammo": "area",
    "fuel": "area",
    "bridge": "hard",
    "building": "medium",
    "armor": "medium",
    "convoy": "soft",
    "ship": "hard",
    "motorpool": "area",
    "runway": "hard",
    "airfield": "hard",
}

#: Target classes that move and whose intel goes stale.
MOBILE_CLASSES = {"sam_shorad", "armor", "convoy", "ship"}


def classify_tgo(tgo: TheaterGroundObject) -> tuple[TargetSystem, str]:
    from game.data.groups import GroupTask
    from game.theater.theatergroundobject import (
        BuildingGroundObject,
        EwrGroundObject,
        IadsBuildingGroundObject,
        MotorpoolGroundObject,
        NavalGroundObject,
        SamGroundObject,
        VehicleGroupGroundObject,
    )

    if isinstance(tgo, SamGroundObject):
        if tgo.task is GroupTask.LORAD:
            return TargetSystem.IADS, "sam_lorad"
        if tgo.task is GroupTask.MERAD:
            return TargetSystem.IADS, "sam_merad"
        return TargetSystem.IADS, "sam_shorad"
    if isinstance(tgo, EwrGroundObject):
        return TargetSystem.IADS, "ewr"
    if isinstance(tgo, IadsBuildingGroundObject):
        if tgo.category == "power":
            return TargetSystem.C2, "power"
        return TargetSystem.C2, "c2_node"
    if isinstance(tgo, NavalGroundObject):
        return TargetSystem.NAVAL, "ship"
    if isinstance(tgo, MotorpoolGroundObject):
        return TargetSystem.FIELDED, "motorpool"
    if isinstance(tgo, VehicleGroupGroundObject):
        return TargetSystem.FIELDED, "armor"
    if isinstance(tgo, BuildingGroundObject):
        category = tgo.category
        if category in ("commandcenter", "comms"):
            return TargetSystem.C2, "c2_node"
        if category == "power":
            return TargetSystem.C2, "power"
        if category in ("fuel", "oil", "derrick"):
            return TargetSystem.POL, "fuel"
        if category == "ammo":
            return TargetSystem.POL, "ammo"
        if category == "factory":
            return TargetSystem.POL, "factory"
        if category == "bridge" or "bridge" in tgo.name.lower():
            return TargetSystem.LOC, "bridge"
        if category == "ware":
            return TargetSystem.LOC, "building"
        return TargetSystem.POL, "building"
    return TargetSystem.FIELDED, "building"


def classify(target: MissionTarget) -> tuple[TargetSystem, str]:
    from game.theater import ControlPoint
    from game.theater.theatergroundobject import TheaterGroundObject
    from game.transfers import CargoShip, Convoy

    if isinstance(target, TheaterGroundObject):
        return classify_tgo(target)
    if isinstance(target, ControlPoint):
        return TargetSystem.AIR, "airfield"
    if isinstance(target, Convoy):
        return TargetSystem.LOC, "convoy"
    if isinstance(target, CargoShip):
        return TargetSystem.LOC, "ship"
    return TargetSystem.FIELDED, "armor"


def target_key(target: MissionTarget) -> str:
    """A key that is stable across turns for the same target."""
    target_id: Optional[object] = getattr(target, "id", None)
    if target_id is not None:
        return f"{type(target).__name__}:{target_id}"
    return f"{type(target).__name__}:{target.name}"


def sam_weight(
    tgo: TheaterGroundObject,
    medium_altitude: bool = True,
    live: Optional[bool] = None,
) -> float:
    """Threat weight of an air defense site for package sizing and risk.

    Packages that fly medium altitude (Western doctrine) sit above most of
    the short-range radar SAM envelope, so SHORAD counts half. ``live`` is
    whether the planning side believes the radar works (intelview); by
    default the site's true state.
    """
    from game.data.groups import GroupTask

    from game.theater.theatergroundobject import NavalGroundObject

    if isinstance(tgo, NavalGroundObject):
        # Ships have no LORAD/MERAD task: weigh them by their reach like the
        # land sites (S-300F class, SA-N-7/9 class, SA-N-4 and guns).
        reach = tgo.max_threat_range().meters
        if live is False or reach <= 0:
            return 0
        if reach >= 40_000:
            return 3
        if reach >= 20_000:
            return 2
        if reach >= 8_000:
            return 1 if medium_altitude else 1.5
        return 0
    if not (tgo.has_live_radar_sam if live is None else live):
        return 0
    if tgo.task is GroupTask.LORAD:
        return 3
    if tgo.task is GroupTask.MERAD:
        return 2
    return 0.5 if medium_altitude else 1
