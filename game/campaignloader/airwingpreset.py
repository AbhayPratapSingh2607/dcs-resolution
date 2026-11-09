"""Air wing presets: ready-made air wings that are not tied to one theater.

A preset describes squadrons by the *kind* of base they belong on (carrier, LHA or
airfield) rather than by a specific base, so the same preset works on any campaign.
``PresetPlacer`` turns a preset into concrete placements for a coalition, and
``apply_preset`` creates the squadrons. Aircraft are bought from the starting budget
at turn 0 by ``buy_preset_aircraft``.
"""

from __future__ import annotations

import dataclasses
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Optional, TYPE_CHECKING

import yaml

from game.dcs.aircrafttype import AircraftType
from game.dcs.countries import country_with_name
from game.squadrons.squadrondef import SquadronDef
from game.squadrons.squadrondefloader import SquadronDefLoader
from game.theater.controlpoint import ControlPoint, ControlPointType, ParkingType
from .campaignairwingconfig import CampaignAirWingConfig, SquadronConfig
from .defaultsquadronassigner import DefaultSquadronAssigner

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.squadrons import Squadron

BUILTIN_PRESET_DIR = Path("resources/airwing_presets")


class BaseKind(Enum):
    CARRIER = "carrier"
    LHA = "lha"
    AIRFIELD = "airfield"

    @classmethod
    def of(cls, control_point: ControlPoint) -> BaseKind:
        if control_point.is_carrier:
            return cls.CARRIER
        if control_point.is_lha:
            return cls.LHA
        return cls.AIRFIELD


class Placement(Enum):
    #: Fill the bases closest to the enemy first.
    FRONT = "front"
    #: Fill the bases farthest from the enemy first.
    REAR = "rear"
    #: Spread squadrons over the bases with the most free parking.
    ANY = "any"


@dataclass(frozen=True)
class PresetSquadronConfig(SquadronConfig):
    #: DCS country name the squadron should come from (e.g. "UK"). Squadron
    #: definitions for other countries are skipped for this entry.
    country: Optional[str] = None
    #: Name of a squadron definition to use, if available.
    squadron: Optional[str] = None
    #: Aircraft to buy at the start. None means "fill the squadron" (max size).
    buy: Optional[int] = None

    @property
    def aircraft_to_buy(self) -> int:
        if self.buy is None:
            return self.max_size
        return max(0, min(self.buy, self.max_size))

    @classmethod
    def from_preset_data(cls, data: dict[str, Any]) -> PresetSquadronConfig:
        base = SquadronConfig.from_data(data)
        values = {f.name: getattr(base, f.name) for f in dataclasses.fields(base)}
        aircraft = values["aircraft"]
        if isinstance(aircraft, str):
            values["aircraft"] = [aircraft]
        return cls(
            **values,
            country=data.get("country"),
            squadron=data.get("squadron"),
            buy=data.get("buy"),
        )


@dataclass(frozen=True)
class PresetGroup:
    base: BaseKind
    #: Carriers/LHAs: how many bases of this kind each get these squadrons.
    #: Airfields: how many airfields the squadrons may be spread over (None = all).
    count: Optional[int]
    placement: Placement
    squadrons: list[PresetSquadronConfig]

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> PresetGroup:
        base = BaseKind(data.get("base", "airfield"))
        count = data.get("count")
        if count is None and base is not BaseKind.AIRFIELD:
            count = 1
        return PresetGroup(
            base,
            count,
            Placement(data.get("placement", "any")),
            [PresetSquadronConfig.from_preset_data(s) for s in data["squadrons"]],
        )


@dataclass(frozen=True)
class AirWingPreset:
    name: str
    description: str
    era: Optional[int]
    #: "blue", "red" or None if the preset suits either side.
    side: Optional[str]
    groups: list[PresetGroup]
    path: Optional[Path] = None

    @property
    def squadron_count(self) -> int:
        return sum(len(g.squadrons) for g in self.groups)

    @classmethod
    def from_data(
        cls, data: dict[str, Any], path: Optional[Path] = None
    ) -> AirWingPreset:
        return AirWingPreset(
            name=data["name"],
            description=data.get("description", ""),
            era=data.get("era"),
            side=data.get("side"),
            groups=[PresetGroup.from_data(g) for g in data.get("groups", [])],
            path=path,
        )

    @classmethod
    def from_yaml(cls, path: Path) -> AirWingPreset:
        with path.open(encoding="utf-8") as f:
            return cls.from_data(yaml.safe_load(f), path)

    def sort_key(self, year: int) -> tuple[int, str]:
        """Sorts presets closest to the campaign year first."""
        distance = abs(self.era - year) if self.era is not None else 10_000
        return distance, self.name


class AirWingPresetLoader:
    @staticmethod
    def preset_directories() -> Iterator[Path]:
        from game import persistency

        yield persistency.airwing_presets_dir()
        yield BUILTIN_PRESET_DIR

    @classmethod
    def load_all(cls) -> list[AirWingPreset]:
        presets: list[AirWingPreset] = []
        for directory in cls.preset_directories():
            presets.extend(cls.load_from(directory))
        return presets

    @staticmethod
    def load_from(directory: Path) -> Iterator[AirWingPreset]:
        for path in sorted(directory.glob("*.yaml")):
            try:
                yield AirWingPreset.from_yaml(path)
            except Exception:
                logging.exception(f"Failed to load air wing preset {path}")


@dataclass(frozen=True)
class PlacedSquadron:
    config: PresetSquadronConfig
    aircraft: AircraftType
    base: ControlPoint

    @property
    def cost(self) -> int:
        return self.aircraft.price * self.config.aircraft_to_buy


@dataclass
class PresetPlan:
    preset: AirWingPreset
    placements: list[PlacedSquadron] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    #: Aircraft the faction lacks that must be added for this plan to work.
    missing_aircraft: set[AircraftType] = field(default_factory=set)

    @property
    def total_cost(self) -> int:
        return sum(p.cost for p in self.placements)

    @property
    def total_aircraft(self) -> int:
        return sum(p.config.aircraft_to_buy for p in self.placements)


def is_mod_aircraft(aircraft: AircraftType) -> bool:
    """True for aircraft from a DCS mod (defined in pydcs_extensions)."""
    unit_type = getattr(aircraft, "dcs_unit_type", None)
    return unit_type is not None and unit_type.__module__.startswith("pydcs_extensions")


def _distance_to_enemy(cp: ControlPoint, enemy_bases: list[ControlPoint]) -> float:
    if not enemy_bases:
        return 0.0
    return min(cp.position.distance_to_point(e.position) for e in enemy_bases)


class PresetPlacer:
    """Works out which base each preset squadron goes to, without changing anything."""

    def __init__(
        self,
        game: Game,
        coalition: Coalition,
        add_missing_aircraft: bool = False,
        replace_existing: bool = True,
    ) -> None:
        self.game = game
        self.coalition = coalition
        self.add_missing_aircraft = add_missing_aircraft
        self.replace_existing = replace_existing
        self.ground_start = game.settings.ground_start_ai_planes
        self._def_names: Optional[dict[str, AircraftType]] = None

    def own_bases(self) -> list[ControlPoint]:
        return list(self.game.theater.control_points_for(self.coalition.player))

    def enemy_bases(self) -> list[ControlPoint]:
        return list(
            self.game.theater.control_points_for(self.coalition.player.opponent)
        )

    @staticmethod
    def is_airfield(cp: ControlPoint) -> bool:
        return not cp.is_fleet and cp.cptype is not ControlPointType.OFF_MAP

    def bases_for(self, group: PresetGroup) -> list[ControlPoint]:
        own = self.own_bases()
        if group.base is BaseKind.CARRIER:
            return [cp for cp in own if cp.is_carrier]
        if group.base is BaseKind.LHA:
            return [cp for cp in own if cp.is_lha]
        airfields = [cp for cp in own if self.is_airfield(cp)]
        if group.placement is not Placement.ANY:
            enemies = self.enemy_bases()
            airfields.sort(
                key=lambda cp: _distance_to_enemy(cp, enemies),
                reverse=group.placement is Placement.REAR,
            )
        return airfields

    def squadron_def_aircraft(self, name: str) -> Optional[AircraftType]:
        if self._def_names is None:
            self._def_names = {}
            for directory in SquadronDefLoader.squadron_directories():
                if not directory.exists():
                    continue
                for _, squadron_def in SquadronDefLoader.load_squadrons_from(directory):
                    self._def_names.setdefault(squadron_def.name, squadron_def.aircraft)
        return self._def_names.get(name)

    def candidate_aircraft(self, config: PresetSquadronConfig) -> list[AircraftType]:
        """Aircraft named by the entry, in preference order, duplicates removed."""
        names: list[str] = []
        if config.aircraft_type is not None:
            names.append(config.aircraft_type)
        names.extend(config.aircraft)
        result: list[AircraftType] = []
        for name in names:
            aircraft: Optional[AircraftType]
            try:
                aircraft = AircraftType.named(name)
            except KeyError:
                aircraft = self.squadron_def_aircraft(name)
            if aircraft is not None and aircraft not in result:
                result.append(aircraft)
        if config.squadron is not None:
            aircraft = self.squadron_def_aircraft(config.squadron)
            if aircraft is not None and aircraft not in result:
                result.insert(0, aircraft)
        return result

    def unknown_aircraft_names(self, config: PresetSquadronConfig) -> list[str]:
        """Aircraft names in the entry that match no aircraft or squadron."""
        names: list[str] = []
        if config.aircraft_type is not None:
            names.append(config.aircraft_type)
        names.extend(config.aircraft)
        unknown: list[str] = []
        for name in names:
            try:
                AircraftType.named(name)
            except KeyError:
                if self.squadron_def_aircraft(name) is None and name not in unknown:
                    unknown.append(name)
        return unknown

    def rejection_reason(
        self, aircraft: AircraftType, base_kind: BaseKind, bases: list[ControlPoint]
    ) -> Optional[str]:
        """Why this aircraft can't be used for the entry, or None if it can."""
        if aircraft not in set(self.coalition.faction.all_aircrafts):
            if is_mod_aircraft(aircraft):
                # Mod aircraft are only added to factions through the new game
                # wizard's mod settings (the mod must be installed), so never add
                # them here.
                return "modded aircraft not selected"
            if not self.add_missing_aircraft:
                return "aircraft not available to faction"
        if not any(b.can_operate(aircraft) for b in bases):
            names = {
                BaseKind.CARRIER: "a carrier",
                BaseKind.LHA: "an LHA",
                BaseKind.AIRFIELD: "any owned airfield",
            }
            return f"cannot operate from {names[base_kind]}"
        return None

    def choose_aircraft(
        self,
        config: PresetSquadronConfig,
        bases: list[ControlPoint],
        base_kind: BaseKind = BaseKind.AIRFIELD,
    ) -> tuple[Optional[AircraftType], bool, list[str]]:
        """Returns the aircraft to use, whether the faction lacks it, and the
        reasons every candidate was rejected (when none is usable)."""
        faction_aircraft = set(self.coalition.faction.all_aircrafts)
        candidates = self.candidate_aircraft(config)
        reasons: list[str] = []
        usable: list[AircraftType] = []
        for aircraft in candidates:
            reason = self.rejection_reason(aircraft, base_kind, bases)
            if reason is None:
                usable.append(aircraft)
            else:
                reasons.append(f"{aircraft}: {reason}")
        # Prefer aircraft the faction already has over ones that must be added.
        for aircraft in usable:
            if aircraft in faction_aircraft:
                return aircraft, False, []
        if usable:
            return usable[0], True, []
        reasons.extend(
            f"{name}: unknown aircraft" for name in self.unknown_aircraft_names(config)
        )
        if not reasons:
            reasons.append("no aircraft listed")
        return None, False, reasons

    @staticmethod
    def entry_label(config: PresetSquadronConfig) -> str:
        if config.squadron:
            return config.squadron
        if config.aircraft:
            return " / ".join(config.aircraft)
        return f"{config.primary.value} squadron"

    def capacity(self, cp: ControlPoint, aircraft: AircraftType) -> int:
        return cp.total_aircraft_parking(
            ParkingType().from_aircraft(aircraft, self.ground_start)
        )

    def resolve(self, preset: AirWingPreset) -> PresetPlan:
        plan = PresetPlan(preset)
        used: dict[ControlPoint, int] = {}
        self._placed_count: dict[ControlPoint, int] = {}
        if not self.replace_existing:
            for squadron in self.coalition.air_wing.iter_squadrons():
                used[squadron.location] = (
                    used.get(squadron.location, 0) + squadron.max_size
                )

        for group in preset.groups:
            bases = self.bases_for(group)
            if not bases:
                plan.warnings.append(
                    f"No {group.base.value} owned: skipped {len(group.squadrons)} "
                    f"squadron(s) ("
                    + ", ".join(self.entry_label(c) for c in group.squadrons)
                    + ")"
                )
                continue
            if group.count is not None:
                bases = bases[: group.count]

            for config in group.squadrons:
                aircraft, missing, reasons = self.choose_aircraft(
                    config, bases, group.base
                )
                if aircraft is None:
                    plan.warnings.append(
                        f"Skipped {self.entry_label(config)} ({group.base.value}): "
                        + "; ".join(reasons)
                    )
                    continue
                if missing:
                    plan.missing_aircraft.add(aircraft)

                if group.base is BaseKind.AIRFIELD:
                    targets = [self.pick_airfield(group, bases, aircraft, config, used)]
                else:
                    targets = [b for b in bases if b.can_operate(aircraft)]

                for base in targets:
                    if base is None:
                        plan.warnings.append(
                            f"Skipped {self.entry_label(config)}: {aircraft}: no "
                            f"owned airfield in range can operate it"
                        )
                        continue
                    free = self.capacity(base, aircraft) - used.get(base, 0)
                    if free < config.max_size:
                        plan.warnings.append(
                            f"Not enough parking for {self.entry_label(config)} "
                            f"({aircraft}) at {base}: {max(free, 0)} free spot(s) "
                            f"for a squadron of {config.max_size}"
                        )
                    used[base] = used.get(base, 0) + config.max_size
                    self._placed_count[base] = self._placed_count.get(base, 0) + 1
                    preferred = dataclasses.replace(
                        config,
                        aircraft=[aircraft.variant_id] + list(config.aircraft),
                        aircraft_type=aircraft.variant_id,
                    )
                    plan.placements.append(PlacedSquadron(preferred, aircraft, base))
        return plan

    def pick_airfield(
        self,
        group: PresetGroup,
        bases: list[ControlPoint],
        aircraft: AircraftType,
        config: PresetSquadronConfig,
        used: dict[ControlPoint, int],
    ) -> Optional[ControlPoint]:
        usable = [b for b in bases if b.can_operate(aircraft)]
        if not usable:
            return None

        def free(cp: ControlPoint) -> int:
            return self.capacity(cp, aircraft) - used.get(cp, 0)

        if group.placement is Placement.ANY:
            # Spread out: the base with the fewest preset squadrons that still has
            # room, preferring more free parking on a tie.
            roomy = [b for b in usable if free(b) >= config.max_size]
            if roomy:
                return min(
                    roomy, key=lambda b: (self._placed_count.get(b, 0), -free(b))
                )
            return max(usable, key=free)
        # Bases are already ordered front-to-rear (or rear-to-front).
        for base in usable:
            if free(base) >= config.max_size:
                return base
        return max(usable, key=free)


class PresetSquadronAssigner(DefaultSquadronAssigner):
    """Creates the squadrons of a resolved preset plan."""

    def __init__(self, plan: PresetPlan, game: Game, coalition: Coalition) -> None:
        super().__init__(CampaignAirWingConfig({}), game, coalition)
        self.plan = plan
        self._foreign_defs: Optional[dict[AircraftType, list[SquadronDef]]] = None

    @property
    def foreign_defs(self) -> dict[AircraftType, list[SquadronDef]]:
        """Squadron definitions of every country, for entries that ask for one."""
        if self._foreign_defs is None:
            known = {
                (d.name, d.aircraft)
                for defs in self.air_wing.squadron_defs.values()
                for d in defs
            }
            loaded = SquadronDefLoader(self.game, self.coalition.faction).load(
                any_country=True
            )
            self._foreign_defs = {
                aircraft: [d for d in defs if (d.name, d.aircraft) not in known]
                for aircraft, defs in loaded.items()
            }
        return self._foreign_defs

    def all_defs_for(self, aircraft: AircraftType) -> Iterable[SquadronDef]:
        yield from self.air_wing.squadron_defs.get(aircraft, [])
        yield from self.foreign_defs.get(aircraft, [])

    def adopt(self, squadron_def: SquadronDef) -> SquadronDef:
        """Makes a foreign def part of the air wing so claiming/unclaiming works."""
        defs = self.air_wing.squadron_defs[squadron_def.aircraft]
        if squadron_def not in defs:
            defs.append(squadron_def)
            foreign = self.foreign_defs.get(squadron_def.aircraft, [])
            if squadron_def in foreign:
                foreign.remove(squadron_def)
        return squadron_def

    def find_def_for_placement(self, placed: PlacedSquadron) -> Optional[SquadronDef]:
        config = placed.config
        base = placed.base

        def usable(d: SquadronDef) -> bool:
            if d.claimed or not base.can_operate(d.aircraft):
                return False
            return config.country is None or d.country.name == config.country

        if config.squadron is not None:
            for d in self.all_defs_for(placed.aircraft):
                if d.name == config.squadron and usable(d):
                    return self.adopt(d)

        if config.country is not None:
            choices = [
                d
                for d in self.all_defs_for(placed.aircraft)
                if usable(d)
                and d.operates_from(base)
                and (d.livery is not None or d.livery_set)
            ]
            if choices:
                return self.adopt(random.choice(choices))
            generated = self.air_wing.squadron_def_generator.generate_for_aircraft(
                placed.aircraft
            )
            try:
                generated.country = country_with_name(config.country)
            except KeyError:
                logging.warning(f"Unknown country in air wing preset: {config.country}")
            return generated

        return self.find_squadron_for(config, base)

    def assign_plan(self) -> list[Squadron]:
        from game.squadrons import Squadron

        created = []
        for placed in self.plan.placements:
            squadron_def = self.override_squadron_defaults(
                self.find_def_for_placement(placed), placed.config
            )
            if squadron_def is None:
                logging.warning(f"No squadron could be made for {placed.aircraft}")
                continue
            squadron = Squadron.create_from(
                squadron_def,
                placed.config.primary,
                placed.config.max_size,
                placed.base,
                self.coalition,
                self.game,
            )
            squadron.set_auto_assignable_mission_types(placed.config.auto_assignable)
            squadron.preset_purchase = placed.config.aircraft_to_buy
            self.air_wing.add_squadron(squadron)
            created.append(squadron)
        return created


def add_aircraft_to_faction(
    coalition: Coalition, aircraft: Iterable[AircraftType]
) -> None:
    """Adds aircraft to this game's copy of the faction, plus their squadron defs."""
    new = [a for a in aircraft if a not in coalition.faction.all_aircrafts]
    if not new:
        return
    faction = coalition.faction
    faction.aircraft = set(faction.aircraft) | set(new)
    # all_aircrafts is a cached_property; drop the cached value so it is rebuilt.
    faction.__dict__.pop("all_aircrafts", None)
    loaded = SquadronDefLoader(coalition.game, faction).load()
    for aircraft_type in new:
        coalition.air_wing.squadron_defs[aircraft_type].extend(
            loaded.get(aircraft_type, [])
        )


def apply_preset(
    plan: PresetPlan, game: Game, coalition: Coalition, replace_existing: bool = True
) -> list[Squadron]:
    """Creates the squadrons of a resolved plan on the coalition's air wing."""
    from collections import defaultdict

    if plan.missing_aircraft:
        add_aircraft_to_faction(coalition, plan.missing_aircraft)
    air_wing = coalition.air_wing
    if replace_existing:
        for squadron in list(air_wing.iter_squadrons()):
            air_wing.unclaim_squadron_def(squadron)
        air_wing.squadrons = defaultdict(list)
    elif not isinstance(air_wing.squadrons, defaultdict):
        air_wing.squadrons = defaultdict(list, air_wing.squadrons)
    return PresetSquadronAssigner(plan, game, coalition).assign_plan()


def buy_preset_aircraft(
    squadrons: Iterable[Squadron],
    budget: float,
    free_parking: Callable[[Squadron], int],
) -> float:
    """Buys each squadron's ``preset_purchase`` aircraft from the budget.

    Aircraft are bought one at a time, round-robin across squadrons, so a budget
    shortfall leaves every squadron a little short instead of leaving the last
    squadrons empty. Returns the remaining budget.
    """
    pending = [s for s in squadrons if s.preset_purchase > 0]
    while pending:
        still_pending = []
        for squadron in pending:
            price = squadron.aircraft.price
            if (
                price > budget
                or squadron.owned_aircraft >= squadron.max_size
                or free_parking(squadron) <= 0
            ):
                squadron.preset_purchase = 0
                continue
            squadron.owned_aircraft += 1
            squadron.preset_purchase -= 1
            budget -= price
            if squadron.preset_purchase > 0:
                still_pending.append(squadron)
        pending = still_pending
    return budget


def preset_from_air_wing(
    name: str, description: str, era: Optional[int], coalition: Coalition
) -> dict[str, Any]:
    """Builds preset YAML data from a coalition's current air wing.

    Bases are written by kind (carrier/LHA/airfield), so the preset works on other
    theaters.
    """
    groups: dict[BaseKind, list[dict[str, Any]]] = {}
    air_wing = coalition.air_wing
    for squadron in air_wing.iter_squadrons():
        entry: dict[str, Any] = {
            "aircraft": [squadron.aircraft.variant_id],
            "country": squadron.country.name,
        }
        def_names = {d.name for d in air_wing.squadron_defs.get(squadron.aircraft, [])}
        if squadron.name in def_names:
            entry["squadron"] = squadron.name
        else:
            entry["name"] = squadron.name
        entry |= {
            "primary": squadron.primary_task.value,
            "secondary": sorted(
                t.value
                for t in squadron.auto_assignable_mission_types
                if t is not squadron.primary_task
            ),
            "size": squadron.max_size,
            "buy": squadron.preset_purchase or squadron.max_size,
        }
        if squadron.nickname:
            entry["nickname"] = squadron.nickname
        groups.setdefault(BaseKind.of(squadron.location), []).append(entry)

    data: dict[str, Any] = {"name": name, "description": description}
    if era is not None:
        data["era"] = era
    data["groups"] = [
        {"base": kind.value, "placement": "any", "squadrons": entries}
        for kind, entries in groups.items()
    ]
    return data
