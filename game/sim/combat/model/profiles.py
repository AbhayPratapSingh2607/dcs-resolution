"""Combat profiles: what each aircraft, weapon, air defense and ground unit can do.

Hand-authored data lives in ``resources/combat/*.yaml``. Anything without an
entry is derived from data Retribution already has (year of introduction, unit
class, pydcs ranges, task priorities, weapon names) so modded units still take
part in the model sensibly.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from functools import cache
from pathlib import Path
from typing import Any, ClassVar, Optional, TYPE_CHECKING

import yaml

from game.data.units import UnitClass

if TYPE_CHECKING:
    from game.data.weapons import Weapon
    from game.dcs.aircrafttype import AircraftType
    from game.dcs.groundunittype import GroundUnitType
    from game.theater.theatergroup import TheaterUnit

RESOURCE_DIR = Path("resources/combat")
WEAPONS_DIR = Path("resources/weapons")


def _load_yaml(name: str) -> dict[str, Any]:
    path = RESOURCE_DIR / name
    if not path.exists():
        logging.warning(f"Combat model data file missing: {path}")
        return {}
    with path.open(encoding="utf-8") as data_file:
        data = yaml.safe_load(data_file)
    return data or {}


def parse_year(value: Any, default: int = 1980) -> int:
    if isinstance(value, int):
        return value
    match = re.search(r"(19|20)\d\d", str(value))
    if match is None:
        return default
    return int(match.group(0))


def generation_for_year(year: int) -> float:
    if year < 1955:
        return 1.5
    if year < 1965:
        return 2.0
    if year < 1978:
        return 3.0
    if year < 1992:
        return 4.0
    if year < 2008:
        return 4.5
    return 5.0


# ---------------------------------------------------------------------------
# Aircraft
# ---------------------------------------------------------------------------


class RadarType(Enum):
    NONE = "none"
    PULSE = "pulse"
    PULSE_DOPPLER = "pd"
    AESA = "aesa"


@dataclass(frozen=True)
class AircraftCombatProfile:
    name: str
    generation: float
    radar_km: float
    radar: RadarType
    rcs: float
    irst: bool
    hmcs: bool
    ecm: float
    rwr: float
    maws: bool
    agility: float
    datalink: bool
    awacs_km: float
    chaff: int
    flares: int
    helicopter: bool
    fighter: bool
    #: Towed radar decoy (ALE-50/55): diverts radar-guided missiles.
    towed_decoy: bool = False

    @property
    def look_down(self) -> bool:
        return self.radar in (RadarType.PULSE_DOPPLER, RadarType.AESA)

    def radar_detection_range_km(self, target_rcs: float) -> float:
        """Radar equation: detection range scales with the fourth root of RCS."""
        if self.radar_km <= 0:
            return 0.0
        return self.radar_km * (max(target_rcs, 1e-4) / 5.0) ** 0.25

    def awacs_detection_range_km(self, target_rcs: float) -> float:
        if self.awacs_km <= 0:
            return 0.0
        return self.awacs_km * (max(target_rcs, 1e-4) / 5.0) ** 0.25


def _derive_aircraft(aircraft: AircraftType) -> AircraftCombatProfile:
    from game.ato.flighttype import FlightType

    dcs = aircraft.dcs_unit_type
    year = parse_year(aircraft.year_introduced)
    gen = generation_for_year(year)
    helicopter = aircraft.helicopter
    fighter = aircraft.capable_of(FlightType.BARCAP) or aircraft.capable_of(
        FlightType.INTERCEPTION
    )
    awacs = aircraft.capable_of(FlightType.AEWC)
    heavy = (
        awacs
        or aircraft.capable_of(FlightType.REFUELING)
        or aircraft.capable_of(FlightType.TRANSPORT)
        or (dcs.fuel_max or 0) > 25000
    )

    if helicopter:
        radar_km = 0.0
    elif fighter:
        radar_km = {1.5: 0, 2.0: 15, 3.0: 40, 4.0: 75, 4.5: 95, 5.0: 120}[gen]
    elif heavy:
        radar_km = 0.0
    else:
        radar_km = 40.0 if gen >= 4 else 0.0

    if radar_km <= 0:
        radar = RadarType.NONE
    elif gen <= 3:
        radar = RadarType.PULSE
    elif gen >= 5:
        radar = RadarType.AESA
    else:
        radar = RadarType.PULSE_DOPPLER

    if helicopter:
        rcs = 5.0
    elif heavy:
        rcs = 60.0
    elif gen >= 5 and fighter:
        rcs = 0.05
    elif fighter:
        rcs = 5.0
    else:
        rcs = 8.0

    ecm = (
        0.25
        if aircraft.has_built_in_ecm
        else {1.5: 0.0, 2.0: 0.0, 3.0: 0.05, 4.0: 0.12, 4.5: 0.18, 5.0: 0.2}[gen]
    )
    rwr = {1.5: 0.0, 2.0: 0.2, 3.0: 0.55, 4.0: 0.75, 4.5: 0.85, 5.0: 0.9}[gen]

    if helicopter:
        agility = 0.5
    elif heavy:
        agility = 0.2
    elif fighter:
        agility = 1.05 if gen >= 4 else (0.9 if gen <= 2 else 0.95)
    else:
        agility = 0.7
    if aircraft.gunfighter:
        agility += 0.05

    return AircraftCombatProfile(
        name=dcs.id,
        generation=gen,
        radar_km=radar_km,
        radar=radar,
        rcs=rcs,
        irst=False,
        hmcs=fighter and gen >= 4.5,
        ecm=ecm,
        rwr=rwr,
        maws=helicopter and gen >= 4,
        agility=agility,
        datalink=gen >= 4.5 or bool(getattr(dcs, "eplrs", False)),
        awacs_km=300.0 if awacs else 0.0,
        chaff=int(getattr(dcs, "chaff", 0) or 0),
        flares=int(getattr(dcs, "flare", 0) or 0),
        helicopter=helicopter,
        fighter=fighter,
    )


def _apply_aircraft_overrides(
    profile: AircraftCombatProfile, data: dict[str, Any]
) -> AircraftCombatProfile:
    changes: dict[str, Any] = {}
    for key in ("radar_km", "rcs", "ecm", "rwr", "agility", "awacs_km"):
        if key in data:
            changes[key] = float(data[key])
    for key in ("irst", "hmcs", "maws", "datalink", "towed_decoy"):
        if key in data:
            changes[key] = bool(data[key])
    if "radar" in data:
        changes["radar"] = RadarType(data["radar"])
    profile = replace(profile, **changes)
    if profile.radar_km <= 0 and profile.radar is not RadarType.NONE:
        profile = replace(profile, radar=RadarType.NONE)
    return profile


# ---------------------------------------------------------------------------
# Weapons
# ---------------------------------------------------------------------------


class WeaponRole(Enum):
    A2A = "a2a"
    A2G = "a2g"
    ARM = "arm"
    ANTISHIP = "antiship"
    TGP = "tgp"
    JAMMER = "jammer"
    OFFENSIVE_JAMMER = "offensive_jammer"
    DECOY = "decoy"
    OTHER = "other"


class Guidance(Enum):
    ARH = "arh"
    SARH = "sarh"
    IR = "ir"
    BEAM = "beam"
    LASER = "laser"
    GPS = "gps"
    TV = "tv"
    IIR = "iir"
    UNGUIDED = "unguided"
    ROCKET = "rocket"
    CLUSTER = "cluster"
    RUNWAY = "runway"
    ATGM = "atgm"
    ANTI_RADIATION = "anti_radiation"
    ANTISHIP = "antiship"
    GUN = "gun"
    NONE = "none"


class Warhead(Enum):
    NONE = "none"
    LIGHT = "light"
    MEDIUM = "medium"
    HEAVY = "heavy"
    ANTITANK = "antitank"
    CLUSTER = "cluster"
    PENETRATOR = "penetrator"
    FRAGMENTATION = "fragmentation"
    ANTISHIP = "antiship"


@dataclass(frozen=True)
class WeaponCombatProfile:
    name: str
    role: WeaponRole
    guidance: Guidance
    #: Rounds of this weapon carried on one pylon.
    count: int = 1
    range_km: float = 0.0
    nez_km: float = 0.0
    pk: float = 0.0
    all_aspect: bool = False
    hobs: bool = False
    warhead: Warhead = Warhead.NONE
    #: For A2G: probability that a weapon lands close enough to its aim point to
    #: affect it, before weather, defenses and skill are applied.
    accuracy: float = 0.0

    @property
    def standoff(self) -> bool:
        """Released outside the reach of point defenses (MANPADS/AAA/SHORAD)."""
        return self.range_km >= 12

    @property
    def radar_guided(self) -> bool:
        return self.guidance in (Guidance.ARH, Guidance.SARH, Guidance.BEAM)


_A2G_ACCURACY = {
    Guidance.LASER: 0.85,
    Guidance.GPS: 0.9,
    Guidance.TV: 0.8,
    Guidance.IIR: 0.82,
    Guidance.BEAM: 0.5,
    Guidance.UNGUIDED: 0.3,
    Guidance.ROCKET: 0.3,
    Guidance.CLUSTER: 0.55,
    Guidance.RUNWAY: 0.5,
    Guidance.ATGM: 0.85,
    Guidance.ANTI_RADIATION: 0.65,
    Guidance.ANTISHIP: 0.75,
    Guidance.GUN: 0.3,
}


def _kw(text: str, *keywords: str) -> bool:
    return any(k in text for k in keywords)


_COUNT_PATTERNS = (
    re.compile(r"(\d+)\s*[x×]\s"),
    re.compile(r"^\s*(\d+)\s+(?=[A-Za-z])"),
    re.compile(r"\*\s*(\d+)"),
    re.compile(r"\s[x×](\d+)\b"),
)


def _count_from_name(name: str) -> int:
    for pattern in _COUNT_PATTERNS:
        if (match := pattern.search(name)) is not None:
            count = int(match.group(1))
            if 0 < count <= 60:
                return count
    return 1


def _classify_a2g(
    text: str, weight_per_item: float
) -> tuple[WeaponRole, Guidance, float, Warhead]:
    """Returns (role, guidance, range_km, warhead) from a weapon's name."""
    if weight_per_item < 120:
        size = Warhead.LIGHT
    elif weight_per_item < 330:
        size = Warhead.MEDIUM
    else:
        size = Warhead.HEAVY

    if _kw(
        text,
        "agm-88",
        "harm",
        "kh-58",
        "kh-31p",
        "kh-25mp",
        "alarm",
        "agm-45",
        "shrike",
        "agm-122",
        "sidearm",
        "agm-78",
        "kh-28",
        "martel",
        "ksr-2p",
        "ksr-5p",
        "kh-22p",
        "mar-1",
        "anti-radiation",
    ):
        rng = 100.0 if _kw(text, "agm-88", "harm", "kh-58", "kh-31p", "alarm") else 35.0
        return WeaponRole.ARM, Guidance.ANTI_RADIATION, rng, Warhead.FRAGMENTATION
    if _kw(
        text,
        "agm-84a",
        "agm-84d",
        "harpoon",
        "exocet",
        "am39",
        "kh-35",
        "kh-31a",
        "c-802",
        "cm-802",
        "yj-",
        "sea eagle",
        "kormoran",
        "rb 15",
        "rbs-15",
        "kh-22",
        "ksr-2",
        "ksr-5",
        "brahmos",
        "p-700",
        "kh-41",
        "sea skua",
        "penguin",
        "nsm",
        "agm-158c",
        "lrasm",
        "c-701",
        "c-704",
        "anti-ship",
        "rb-04",
        "rb 04",
        "kd-88",
        "rb-15",
    ):
        return WeaponRole.ANTISHIP, Guidance.ANTISHIP, 90.0, Warhead.ANTISHIP
    if _kw(
        text,
        "agm-154",
        "jsow",
        "agm-158",
        "jassm",
        "storm shadow",
        "scalp",
        "kh-59",
        "kh-101",
        "kh-555",
        "kh-65",
        "agm-86",
        "calcm",
        "taurus",
        "agm-84e",
        "agm-84h",
        "slam",
        "kd-20",
        "cm-400",
        "kh-36",
        "gb-6",
        "kd-63",
        "tomahawk",
        "kh-20",
        "kh-55",
    ):
        warhead = (
            Warhead.CLUSTER
            if _kw(text, "agm-154a", "agm-154b", "gb-6")
            else Warhead.HEAVY
        )
        return WeaponRole.A2G, Guidance.GPS, 100.0, warhead
    if _kw(text, "agm-130", "agm-142", "popeye"):
        return WeaponRole.A2G, Guidance.TV, 60.0, Warhead.HEAVY
    if _kw(
        text,
        "agm-114",
        "hellfire",
        "vikhr",
        "9m127",
        "ataka",
        "9m120",
        "shturm",
        "9m114",
        "bgm-71",
        "tow",
        "hot-",
        "hot3",
        "brimstone",
        "spike",
        "9m133",
        "akd-10",
        "ar-1",
        "mokopa",
        "ingwe",
    ):
        return WeaponRole.A2G, Guidance.ATGM, 8.0, Warhead.ANTITANK
    if _kw(
        text, "agm-65e", "agm-65l", "kh-29l", "kh-25ml", "kh-38ml", "s-25l", "agm-65e2"
    ):
        return WeaponRole.A2G, Guidance.LASER, 12.0, Warhead.MEDIUM
    if _kw(
        text,
        "agm-65d",
        "agm-65f",
        "agm-65g",
        "agm-65k",
        "agm-65h",
        "agm-65a",
        "agm-65b",
        "maverick",
        "kh-29t",
        "kh-29te",
        "kh-25mr",
    ):
        guidance = (
            Guidance.IIR if _kw(text, "agm-65d", "agm-65f", "agm-65g") else Guidance.TV
        )
        warhead = (
            Warhead.HEAVY
            if _kw(text, "agm-65f", "agm-65g", "agm-65k", "kh-29")
            else Warhead.MEDIUM
        )
        return WeaponRole.A2G, guidance, 14.0, warhead
    if _kw(text, "agm-62", "walleye"):
        return WeaponRole.A2G, Guidance.TV, 20.0, Warhead.HEAVY
    if _kw(text, "agm-12", "bullpup", "kh-23", "kh-66", "as-30", "rb-05"):
        return WeaponRole.A2G, Guidance.BEAM, 8.0, Warhead.MEDIUM
    if _kw(text, "apkws"):
        return WeaponRole.A2G, Guidance.ATGM, 5.0, Warhead.LIGHT
    if _kw(
        text,
        "gbu-31",
        "gbu-32",
        "gbu-38",
        "gbu-39",
        "gbu-53",
        "gbu-54",
        "gbu-55",
        "gbu-56",
        "gbu-62",
        "gbu-64",
        "jdam",
        "kab-500s",
        "ft-",
        "ls-6",
        "lj-7",
        "sdb",
        "aasm",
        "hammer",
        "spice",
        "gbu-105",
    ):
        rng = (
            60.0
            if _kw(text, "gbu-39", "gbu-53", "sdb", "ls-6", "aasm", "hammer", "spice")
            else 20.0
        )
        return WeaponRole.A2G, Guidance.GPS, rng, size
    if _kw(
        text, "kab-500kr", "kab-1500kr", "kab-500od", "kab-1500t", "gbu-8", "gbu-15"
    ):
        return WeaponRole.A2G, Guidance.TV, 15.0, Warhead.HEAVY
    if _kw(
        text,
        "gbu-",
        "kab-",
        "paveway",
        "bgl",
        "ls-",
        "lt-",
        "gb-250",
        "gb-500",
        "lgb",
        "laser",
    ):
        return WeaponRole.A2G, Guidance.LASER, 10.0, size
    if _kw(
        text,
        "betab",
        "durandal",
        "blu-107",
        "bap-100",
        "bap100",
        "concrete",
        "jp233",
        "sg-357",
    ):
        return WeaponRole.A2G, Guidance.RUNWAY, 0.0, Warhead.PENETRATOR
    if _kw(
        text,
        "cbu",
        "rbk",
        "bl755",
        "bl-755",
        "blu-",
        "rockeye",
        "mk-20",
        "mk20",
        "bkf",
        "kmgu",
        "cluster",
        "belouga",
        "submunition",
        "cb-",
        "ptab",
        "atacms",
    ):
        return WeaponRole.A2G, Guidance.CLUSTER, 0.0, Warhead.CLUSTER
    if _kw(
        text,
        "rocket",
        "rkts",
        "rkt",
        "hydra",
        "s-5",
        "s-8",
        "s-13",
        "s-24",
        "s-25",
        "zuni",
        "ffar",
        "b-8",
        "b-13",
        "ub-16",
        "ub-32",
        "m151",
        "m156",
        "m257",
        "m261",
        "m274",
        "m282",
        "mk151",
        "mk5",
        "snek",
        "sneb",
        "lau-",
        "agr-20",
        "hvar",
        "arak",
        "tiny tim",
        "r4m",
        "rp-3",
    ):
        return WeaponRole.A2G, Guidance.ROCKET, 5.0, Warhead.LIGHT
    if _kw(
        text,
        "gun",
        "gpu",
        "upk",
        "sppu",
        "gau",
        "cannon",
        "m134",
        "minigun",
        "m60",
        "m240",
        "browning",
        "mg-",
        "gsh",
        "pod - 7.62",
        "pod 12.7",
        "m3p",
        "fn hmp",
        "grenade launcher",
        "m621",
        "m-230",
        "pk-3",
        "hmp400",
    ):
        return WeaponRole.A2G, Guidance.GUN, 1.5, Warhead.LIGHT
    if _kw(
        text,
        "mk-8",
        "mk-82",
        "mk-83",
        "mk-84",
        "mk 82",
        "mk 83",
        "mk 84",
        "fab",
        "ofab",
        "an-m",
        "an/m",
        "m117",
        "sc ",
        "sc-",
        "sd ",
        "bdu",
        "matra 250",
        "saab",
        "snakeye",
        "ballute",
        "bomb",
        "bombe",
        "ab 250",
        "ab 500",
        "m-117",
        "type 200",
        "250-2",
        "500-2",
        "zab",
        "bin-",
        "bl-1",
        "mk-77",
        "mk-81",
        " lb mc",
        " lb gp",
        " lb sap",
        "lb s.a.p",
        "lb ac",
        "kg gp",
    ):
        if _kw(text, "bdu", "practice", "smoke"):
            return WeaponRole.OTHER, Guidance.NONE, 0.0, Warhead.NONE
        return WeaponRole.A2G, Guidance.UNGUIDED, 0.0, size
    return WeaponRole.OTHER, Guidance.NONE, 0.0, Warhead.NONE


def _classify_unknown_a2a(
    text: str,
) -> Optional[tuple[Guidance, float, float, float, bool, bool]]:
    """(guidance, range_km, nez_km, pk, all_aspect, hobs) for A2A missiles we have
    no data for, recognized by name."""
    if _kw(text, "meteor"):
        return Guidance.ARH, 150, 60, 0.72, False, False
    if _kw(text, "pl-15", "aim-260"):
        return Guidance.ARH, 150, 45, 0.7, False, False
    if _kw(
        text,
        "mica-em",
        "mica rf",
        "mica em",
        "pl-12",
        "sd-10",
        "derby",
        "r-77",
        "rvv-ae",
        "aim-120",
        "amraam",
        "astra",
        "i-derby",
        "active rdr",
        "k-77",
    ):
        return Guidance.ARH, 80, 25, 0.65, False, False
    if _kw(
        text,
        "mica-ir",
        "mica ir",
        "iris-t",
        "asraam",
        "python-5",
        "python 5",
        "aim-9x",
        "pl-10",
        "a-darter",
        "r-74",
    ):
        return Guidance.IR, 20, 6, 0.75, True, True
    if _kw(
        text,
        "python",
        "pl-8",
        "pl-5e",
        "magic",
        "aim-9",
        "sidewinder",
        "r-73",
        "r-60",
        "pl-5",
        "u-darter",
        "v3",
        "rvv-md",
        "archer",
        "r-98mt",
        "r-23t",
        "infra red",
    ):
        return Guidance.IR, 12, 4, 0.55, True, False
    if _kw(
        text,
        "aim-7",
        "sparrow",
        "skyflash",
        "aspide",
        "r-27",
        "super 530",
        "530d",
        "r-24r",
        "pl-11",
        "r-98",
        "r-23",
        "semi-active",
    ):
        return Guidance.SARH, 60, 18, 0.48, False, False
    if _kw(text, "aim-54", "phoenix", "r-33", "r-37"):
        return Guidance.ARH, 150, 40, 0.5, False, False
    return None


@cache
def _weapon_group_folders() -> dict[str, str]:
    folders: dict[str, str] = {}
    if not WEAPONS_DIR.exists():
        return folders
    for path in WEAPONS_DIR.glob("*/*.yaml"):
        try:
            with path.open(encoding="utf-8") as data_file:
                data = yaml.safe_load(data_file)
            folders[str(data["name"])] = path.parent.name
        except Exception:
            continue
    return folders


_SUFFIX_COUNT = re.compile(r"-(\d+)X$")
_PREFIX_COUNT = re.compile(r"^(\d+)\s*x\s*", re.IGNORECASE)
_TRAILING_COUNT = re.compile(r"\s+x\s*(\d+)$", re.IGNORECASE)


def normalize_weapon_name(name: str) -> tuple[str, int]:
    """Canonical key for weapon group lookups, plus any count encoded in the
    name ("2xAIM-9M", "R-60 x 2", "AIM-120C-2X")."""
    name = name.strip()
    count = 1
    for pattern in (_PREFIX_COUNT, _TRAILING_COUNT, _SUFFIX_COUNT):
        match = pattern.search(name)
        if match is not None:
            count = max(count, int(match.group(1)))
            name = (name[: match.start()] + name[match.end() :]).strip()
    name = name.split(" - ")[0]
    name = re.sub(r"\(.*?\)", "", name)
    return re.sub(r"[^A-Z0-9]", "", name.upper()), count


def _derive_weapon(
    group_name: str,
    weapon_name: str,
    weight_kg: float,
    group_type: str,
    a2a_data: dict[str, Any],
) -> WeaponCombatProfile:
    key, group_count = normalize_weapon_name(group_name)
    count = max(_count_from_name(weapon_name), group_count)

    if group_type == "TGP":
        return WeaponCombatProfile(group_name, WeaponRole.TGP, Guidance.NONE)
    if group_type == "JAMMER":
        return WeaponCombatProfile(group_name, WeaponRole.JAMMER, Guidance.NONE)
    if group_type == "OFFENSIVE_JAMMER":
        return WeaponCombatProfile(
            group_name, WeaponRole.OFFENSIVE_JAMMER, Guidance.NONE
        )
    if group_type == "DECOY" or _kw(
        f"{group_name} {weapon_name}".lower(), "tald", "mald", "adm-141", "adm-160"
    ):
        return WeaponCombatProfile(
            group_name,
            WeaponRole.DECOY,
            Guidance.NONE,
            count=_count_from_name(weapon_name),
        )

    entry = a2a_data.get(key)
    if entry is not None:
        return WeaponCombatProfile(
            name=group_name,
            role=WeaponRole.A2A,
            guidance=Guidance(entry["guidance"]),
            count=count,
            range_km=float(entry["range_km"]),
            nez_km=float(entry["nez_km"]),
            pk=float(entry["pk"]),
            all_aspect=bool(entry.get("all_aspect", entry["guidance"] != "ir")),
            hobs=bool(entry.get("hobs", False)),
        )

    text = f"{group_name} {weapon_name}".lower()
    if _kw(
        text,
        "fuel",
        "ptb",
        "droptank",
        "drop tank",
        "smoke",
        "illum",
        "luu-2",
        "practice",
        "captive trg",
        "trg round",
        "training",
        "cargo",
        "<clean>",
        "camera",
        "acmi",
        "datalink pod",
    ):
        return WeaponCombatProfile(group_name, WeaponRole.OTHER, Guidance.NONE)

    folder = _weapon_group_folders().get(group_name, "")
    if folder == "a2a-missiles" or _kw(text, "aam", "air-to-air", "air to air"):
        a2a = _classify_unknown_a2a(text)
        if a2a is None:
            a2a = (Guidance.SARH, 40, 12, 0.4, False, False)
        guidance, rng, nez, pk, all_aspect, hobs = a2a
        return WeaponCombatProfile(
            group_name, WeaponRole.A2A, guidance, count, rng, nez, pk, all_aspect, hobs
        )
    a2a = _classify_unknown_a2a(text)
    if a2a is not None and not _kw(text, "agm", "kh-", "bomb"):
        guidance, rng, nez, pk, all_aspect, hobs = a2a
        return WeaponCombatProfile(
            group_name, WeaponRole.A2A, guidance, count, rng, nez, pk, all_aspect, hobs
        )

    if group_type == "ARM":
        role, guidance, rng, warhead = (
            WeaponRole.ARM,
            Guidance.ANTI_RADIATION,
            80.0,
            Warhead.FRAGMENTATION,
        )
    else:
        role, guidance, rng, warhead = _classify_a2g(text, weight_kg / max(count, 1))
        if role is WeaponRole.OTHER and group_type == "LGB":
            role, guidance, rng, warhead = (
                WeaponRole.A2G,
                Guidance.LASER,
                10.0,
                Warhead.MEDIUM if weight_kg / max(count, 1) < 330 else Warhead.HEAVY,
            )
    if guidance is Guidance.ROCKET:
        # Rockets are fired in ripples; treat roughly seven rockets as one attack.
        count = max(1, round(count / 7))
    return WeaponCombatProfile(
        name=group_name,
        role=role,
        guidance=guidance,
        count=count,
        range_km=rng,
        warhead=warhead,
        accuracy=_A2G_ACCURACY.get(guidance, 0.0),
    )


# ---------------------------------------------------------------------------
# Air defenses
# ---------------------------------------------------------------------------


class AirDefenseGuidance(Enum):
    RADAR = "radar"
    TELAR = "telar"
    IR = "ir"
    GUN = "gun"


@dataclass(frozen=True)
class AirDefenseProfile:
    system: str
    guidance: AirDefenseGuidance
    range_km: float
    min_alt_m: float
    max_alt_m: float
    pk: float
    channels: int
    salvo: int
    missiles: int
    reaction_s: float
    eccm: float
    emcon: float
    mast_m: float
    #: Share of missiles that work as designed (motor, guidance, fuze).
    reliability: float = 0.8

    @property
    def emitter(self) -> bool:
        return self.guidance in (AirDefenseGuidance.RADAR, AirDefenseGuidance.TELAR)


def _reliability_for_year(year: int) -> float:
    """Missile reliability improves with each generation of electronics."""
    return max(0.6, min(0.92, 0.6 + (year - 1958) * 0.008))


#: Ships whose air defense reaches no further than this have guns and
#: MANPADS only (fast attack craft, patrol boats); naval SAMs reach further
#: (SA-N-4 16 km).
SHIP_GUN_OR_MANPADS_M = 6000.0


def is_ship(unit: TheaterUnit) -> bool:
    from dcs.unittype import ShipType

    try:
        return issubclass(unit.type, ShipType)
    except TypeError:
        return False


def _derive_air_defense(
    unit: TheaterUnit, data: Optional[dict[str, Any]]
) -> Optional[AirDefenseProfile]:
    threat_m = float(getattr(unit.type, "threat_range", 0) or 0)
    unit_type = unit.unit_type
    unit_class = unit_type.unit_class if unit_type is not None else UnitClass.UNKNOWN
    year = parse_year(
        unit_type.year_introduced if unit_type is not None else None, 1975
    )
    tech = max(0.6, min(1.2, 0.6 + (year - 1955) * 0.012))

    if data is not None:
        range_km = threat_m / 1000 if threat_m > 0 else float(data.get("range_km", 5))
        emcon = float(data.get("emcon", 0.4))
        skynet = getattr(unit_type, "skynet_properties", None)
        if skynet is not None and skynet.harm_detection_chance:
            try:
                chance = float(skynet.harm_detection_chance)
                emcon = chance / 100 if chance > 1 else chance
            except ValueError:
                pass
        return AirDefenseProfile(
            system=str(data.get("system", unit.type.id)),
            guidance=AirDefenseGuidance(data["guidance"]),
            range_km=range_km,
            min_alt_m=float(data.get("min_alt_m", 30)),
            max_alt_m=float(data.get("max_alt_m", 10000)),
            pk=float(data.get("pk", 0.5)),
            channels=int(data.get("channels", 1)),
            salvo=int(data.get("salvo", 1)),
            missiles=int(data.get("missiles", 4)),
            reaction_s=float(data.get("reaction_s", 15)),
            eccm=float(data.get("eccm", 0.3)),
            emcon=emcon,
            mast_m=float(data.get("mast_m", 5)),
            reliability=float(data.get("reliability", _reliability_for_year(year))),
        )

    if threat_m <= 0:
        return None
    detection_m = float(getattr(unit.type, "detection_range", 0) or 0)
    range_km = threat_m / 1000
    if is_ship(unit) and threat_m <= SHIP_GUN_OR_MANPADS_M:
        # A ship this short-ranged has guns or shoulder-launched missiles,
        # not a radar SAM: its detection range is its surface search radar.
        # As a TELAR it was a HARM target (the PG Growlers sank IRGCN fast
        # attack craft with HARMs in fast forward).
        if threat_m >= 3000:
            guidance, max_alt, pk, missiles = AirDefenseGuidance.IR, 3500.0, 0.4, 4
        else:
            guidance, max_alt, pk, missiles = (
                AirDefenseGuidance.GUN,
                min(3000.0, threat_m * 0.7),
                0.04,
                30,
            )
    elif unit_class is UnitClass.MANPAD:
        guidance, max_alt, pk, missiles = AirDefenseGuidance.IR, 3500.0, 0.4, 2
    elif unit_class is UnitClass.AAA:
        guidance, max_alt, pk, missiles = (
            AirDefenseGuidance.GUN,
            min(3000.0, threat_m * 0.7),
            0.04,
            30,
        )
    elif unit_class in (
        UnitClass.CRUISER,
        UnitClass.DESTROYER,
        UnitClass.FRIGATE,
        UnitClass.AIRCRAFT_CARRIER,
        UnitClass.HELICOPTER_CARRIER,
    ):
        guidance, max_alt, pk, missiles = (
            AirDefenseGuidance.TELAR,
            min(25000.0, threat_m * 0.3),
            0.6,
            16,
        )
    elif unit_class is UnitClass.SHORAD:
        if detection_m > 0:
            guidance, max_alt, pk, missiles = (
                AirDefenseGuidance.TELAR,
                min(6000.0, threat_m * 0.5),
                0.5,
                6,
            )
        else:
            guidance, max_alt, pk, missiles = AirDefenseGuidance.IR, 3500.0, 0.4, 4
    elif detection_m > 0:
        guidance, max_alt, pk, missiles = (
            AirDefenseGuidance.TELAR,
            min(20000.0, threat_m * 0.4),
            0.55,
            4,
        )
    else:
        guidance, max_alt, pk, missiles = (
            AirDefenseGuidance.RADAR,
            min(25000.0, threat_m * 0.4),
            0.55,
            4,
        )
    if guidance is AirDefenseGuidance.GUN:
        tech = (tech + 1) / 2
    return AirDefenseProfile(
        system=unit.type.id,
        guidance=guidance,
        range_km=range_km,
        min_alt_m=10.0 if guidance is not AirDefenseGuidance.RADAR else 50.0,
        max_alt_m=max_alt,
        pk=min(0.85, pk * tech),
        channels=2 if guidance is AirDefenseGuidance.TELAR and range_km > 30 else 1,
        salvo=(
            2
            if guidance in (AirDefenseGuidance.RADAR, AirDefenseGuidance.TELAR)
            and range_km > 15
            else 1
        ),
        missiles=missiles,
        reaction_s=(
            10.0
            if guidance in (AirDefenseGuidance.IR, AirDefenseGuidance.GUN)
            else 20.0
        ),
        eccm=max(0.1, min(0.8, (year - 1955) / 70)),
        emcon=(
            0.0 if guidance in (AirDefenseGuidance.IR, AirDefenseGuidance.GUN) else 0.35
        ),
        mast_m=5.0,
        reliability=_reliability_for_year(year),
    )


# ---------------------------------------------------------------------------
# Ground units
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundUnitCombatProfile:
    anti_armor: float
    anti_soft: float
    protection: float
    indirect: bool = False
    thermal: bool = False
    air_defense: float = 0.0

    @property
    def armored(self) -> bool:
        return self.protection >= 0.4


SHIP_HIT_POINTS = {
    UnitClass.BOAT: 1,
    UnitClass.LANDING_SHIP: 2,
    UnitClass.FRIGATE: 2,
    UnitClass.DESTROYER: 3,
    UnitClass.CRUISER: 4,
    UnitClass.SUBMARINE: 2,
    UnitClass.AIRCRAFT_CARRIER: 6,
    UnitClass.HELICOPTER_CARRIER: 5,
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class CombatProfiles:
    aircraft_data: dict[str, Any] = field(default_factory=dict)
    weapon_data: dict[str, Any] = field(default_factory=dict)
    air_defense_data: dict[str, Any] = field(default_factory=dict)
    ground_data: dict[str, Any] = field(default_factory=dict)
    _aircraft: dict[str, AircraftCombatProfile] = field(default_factory=dict)
    _weapons: dict[str, WeaponCombatProfile] = field(default_factory=dict)
    _air_defense: dict[str, Optional[AirDefenseProfile]] = field(default_factory=dict)
    _ground: dict[str, GroundUnitCombatProfile] = field(default_factory=dict)

    _instance: ClassVar[Optional[CombatProfiles]] = None

    @classmethod
    def instance(cls) -> CombatProfiles:
        if cls._instance is None:
            weapons = {
                normalize_weapon_name(str(name))[0]: data
                for name, data in _load_yaml("weapons.yaml").items()
            }
            cls._instance = CombatProfiles(
                aircraft_data=_load_yaml("aircraft.yaml"),
                weapon_data=weapons,
                air_defense_data=_load_yaml("air_defense.yaml"),
                ground_data=_load_yaml("ground_units.yaml"),
            )
        return cls._instance

    def aircraft(self, aircraft: AircraftType) -> AircraftCombatProfile:
        key = aircraft.variant_id
        if key not in self._aircraft:
            profile = _derive_aircraft(aircraft)
            data = self.aircraft_data.get(aircraft.dcs_unit_type.id)
            if data is None:
                data = self.aircraft_data.get(aircraft.variant_id)
            if data is not None:
                profile = _apply_aircraft_overrides(profile, data)
            self._aircraft[key] = profile
        return self._aircraft[key]

    def weapon(self, weapon: Weapon) -> WeaponCombatProfile:
        if weapon.clsid not in self._weapons:
            try:
                name = weapon.name
                weight = float(weapon.pydcs_data.get("weight", 0) or 0)
            except Exception:
                name = weapon.clsid
                weight = 0.0
            group = weapon.weapon_group
            self._weapons[weapon.clsid] = _derive_weapon(
                group.name, name, weight, group.type.name, self.weapon_data
            )
        return self._weapons[weapon.clsid]

    def air_defense(self, unit: TheaterUnit) -> Optional[AirDefenseProfile]:
        key = unit.type.id
        if key not in self._air_defense:
            self._air_defense[key] = _derive_air_defense(
                unit, self.air_defense_data.get(key)
            )
        return self._air_defense[key]

    def ground_unit(self, unit_type: GroundUnitType) -> GroundUnitCombatProfile:
        key = unit_type.dcs_id
        if key not in self._ground:
            classes = self.ground_data.get("classes", {})
            units = self.ground_data.get("units", {})
            base = classes.get(unit_type.unit_class.value) or classes.get("Unknown", {})
            override = units.get(key)
            data = dict(base)
            if override is not None:
                data.update(override)
                tech = 1.0
            else:
                year = parse_year(unit_type.year_introduced, 1975)
                tech = max(0.6, min(1.3, 0.6 + (year - 1950) * 0.012))
                if "thermal" not in data:
                    data["thermal"] = year >= 1985 and unit_type.unit_class in (
                        UnitClass.TANK,
                        UnitClass.IFV,
                        UnitClass.ATGM,
                    )
            self._ground[key] = GroundUnitCombatProfile(
                anti_armor=float(data.get("anti_armor", 0.1)) * tech,
                anti_soft=float(data.get("anti_soft", 0.3)) * tech,
                protection=float(data.get("protection", 0.3)) * (0.8 + 0.2 * tech),
                indirect=bool(data.get("indirect", False)),
                thermal=bool(data.get("thermal", False)),
                air_defense=float(data.get("air_defense", 0.0)),
            )
        return self._ground[key]
