"""Air wing presets made from a faction's own aircraft, so every faction
(built in or the player's own) has presets for every kind of base.

A template names roles (fighter, strike, SEAD, AEW&C, tanker, attack and
transport helicopters, ...) with a squadron size. For a faction, each role
is filled by the faction's best aircraft for it (the highest task priority,
as the planner ranks them) that can fly from that kind of base; a second
slot of the same role takes the next best type when there is one. Templates
are offered by base kind and, for airfields, by distance from the battle
(``Band``): close air support near the front, tankers and AWACS at the rear.

The hand-made presets in resources/airwing_presets stay; ``presets_for_base``
offers the generated ones first, then the hand-made groups whose aircraft
the faction has.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Iterable, Optional

from game.ato.flighttype import FlightType
from game.dcs.aircrafttype import AircraftType
from game.factions.faction import Faction
from .airwingpreset import (
    AirWingPreset,
    Band,
    BasePreset,
    BaseKind,
    Placement,
    PresetGroup,
    PresetSquadronConfig,
    RankedBase,
    base_presets_for,
)

#: Strategic bombers, for the off-map base and the rear's heavy strike.
BOMBERS = {
    "B-52H Stratofortress",
    "B-1B Lancer",
    "Tu-95MS Bear-H",
    "Tu-160 Blackjack",
    "Tu-22M3 Backfire-C",
    "Tu-142 Bear-F",
    "H-6J Badger",
    "Tu-16 Badger-B",
    "B-17G Flying Fortress",
    "[CH] Tu-160M2",
    "Tu-4K Bull",
}


class Role(Enum):
    FIGHTER = "fighter"
    STRIKE = "strike"
    CAS = "close air support"
    SEAD = "SEAD"
    ANTISHIP = "anti-ship"
    AEW = "AEW&C"
    TANKER = "tanker"
    AIRLIFT = "airlift"
    ATTACK_HELO = "attack helicopter"
    TRANSPORT_HELO = "transport helicopter"
    BOMBER = "bomber"


def _fixed_wing(a: AircraftType) -> bool:
    # Bombers only fill bomber slots: a Tu-160 isn't a strike squadron's jet.
    return not a.helicopter and a.variant_id not in BOMBERS


#: Role -> (tasks it is ranked by, best first; which aircraft may fill it).
ROLES: dict[Role, tuple[tuple[FlightType, ...], Callable[[AircraftType], bool]]] = {
    Role.FIGHTER: ((FlightType.BARCAP, FlightType.INTERCEPTION), _fixed_wing),
    Role.STRIKE: ((FlightType.STRIKE, FlightType.BAI), _fixed_wing),
    Role.CAS: ((FlightType.CAS, FlightType.BAI), _fixed_wing),
    Role.SEAD: ((FlightType.SEAD, FlightType.DEAD), _fixed_wing),
    Role.ANTISHIP: ((FlightType.ANTISHIP,), _fixed_wing),
    Role.AEW: ((FlightType.AEWC,), _fixed_wing),
    Role.TANKER: ((FlightType.REFUELING,), _fixed_wing),
    Role.AIRLIFT: ((FlightType.TRANSPORT,), _fixed_wing),
    Role.ATTACK_HELO: ((FlightType.CAS,), lambda a: a.helicopter),
    Role.TRANSPORT_HELO: (
        (FlightType.AIR_ASSAULT, FlightType.TRANSPORT),
        lambda a: a.helicopter,
    ),
    Role.BOMBER: ((FlightType.STRIKE,), lambda a: a.variant_id in BOMBERS),
}

#: The primary task a role's squadron is created with.
PRIMARY = {
    Role.FIGHTER: FlightType.BARCAP,
    Role.STRIKE: FlightType.STRIKE,
    Role.CAS: FlightType.CAS,
    Role.SEAD: FlightType.SEAD,
    Role.ANTISHIP: FlightType.ANTISHIP,
    Role.AEW: FlightType.AEWC,
    Role.TANKER: FlightType.REFUELING,
    Role.AIRLIFT: FlightType.TRANSPORT,
    Role.ATTACK_HELO: FlightType.CAS,
    Role.TRANSPORT_HELO: FlightType.AIR_ASSAULT,
    Role.BOMBER: FlightType.STRIKE,
}


@dataclass(frozen=True)
class Template:
    name: str
    description: str
    kind: BaseKind
    #: Airfield bands it is offered for (None: every band / not an airfield).
    bands: Optional[tuple[Band, ...]]
    #: (role, squadron size); a role listed twice takes two types if it can.
    slots: tuple[tuple[Role, int], ...]
    #: Slots that must be filled for the template to be offered.
    required: tuple[Role, ...] = ()


F, M, R = Band.FRONT, Band.MIDDLE, Band.REAR

TEMPLATES: tuple[Template, ...] = (
    # Carriers: 90 deck spots; every wing leaves room for its helicopters.
    Template(
        "Carrier air wing",
        "A full air wing: two fighter and two strike squadrons, SEAD, AEW&C, "
        "tankers and helicopters.",
        BaseKind.CARRIER,
        None,
        (
            (Role.FIGHTER, 12),
            (Role.FIGHTER, 12),
            (Role.STRIKE, 12),
            (Role.STRIKE, 12),
            (Role.SEAD, 6),
            (Role.AEW, 4),
            (Role.TANKER, 4),
            (Role.TRANSPORT_HELO, 4),
        ),
        (Role.FIGHTER,),
    ),
    Template(
        "Fleet defense",
        "Fighters to hold the air over the fleet, with AEW&C and tankers.",
        BaseKind.CARRIER,
        None,
        (
            (Role.FIGHTER, 12),
            (Role.FIGHTER, 12),
            (Role.FIGHTER, 12),
            (Role.AEW, 4),
            (Role.TANKER, 4),
            (Role.TRANSPORT_HELO, 4),
        ),
        (Role.FIGHTER,),
    ),
    Template(
        "Carrier strike group",
        "Strike and anti-ship heavy, with one fighter squadron and SEAD.",
        BaseKind.CARRIER,
        None,
        (
            (Role.FIGHTER, 12),
            (Role.STRIKE, 12),
            (Role.STRIKE, 12),
            (Role.ANTISHIP, 12),
            (Role.SEAD, 6),
            (Role.AEW, 4),
            (Role.TANKER, 4),
            (Role.TRANSPORT_HELO, 4),
        ),
        (Role.STRIKE,),
    ),
    # LHAs: about 20 spots.
    Template(
        "Amphibious ready group",
        "STOVL jets, attack helicopters and assault helicopters.",
        BaseKind.LHA,
        None,
        ((Role.CAS, 6), (Role.ATTACK_HELO, 4), (Role.TRANSPORT_HELO, 6)),
    ),
    Template(
        "Helicopter assault",
        "Attack and assault helicopters only.",
        BaseKind.LHA,
        None,
        (
            (Role.ATTACK_HELO, 6),
            (Role.TRANSPORT_HELO, 6),
            (Role.TRANSPORT_HELO, 6),
        ),
        (Role.TRANSPORT_HELO,),
    ),
    Template(
        "STOVL strike",
        "As many STOVL jets as the deck takes, with a few helicopters.",
        BaseKind.LHA,
        None,
        ((Role.CAS, 10), (Role.ATTACK_HELO, 4), (Role.TRANSPORT_HELO, 4)),
        (Role.CAS,),
    ),
    # Airfields near the battle.
    Template(
        "Close air support",
        "Ground attack jets and helicopters for the front, with fighter cover.",
        BaseKind.AIRFIELD,
        (F, M),
        (
            (Role.CAS, 12),
            (Role.ATTACK_HELO, 8),
            (Role.TRANSPORT_HELO, 8),
            (Role.FIGHTER, 12),
        ),
        (Role.CAS,),
    ),
    Template(
        "Front-line fighters",
        "Fighters to hold the air over the front, and SEAD to open it.",
        BaseKind.AIRFIELD,
        (F, M),
        ((Role.FIGHTER, 12), (Role.FIGHTER, 12), (Role.SEAD, 12)),
        (Role.FIGHTER,),
    ),
    Template(
        "Strike and SEAD",
        "Strike and SEAD squadrons with an escort squadron.",
        BaseKind.AIRFIELD,
        (F, M),
        ((Role.STRIKE, 12), (Role.SEAD, 12), (Role.FIGHTER, 12)),
        (Role.STRIKE,),
    ),
    Template(
        "Helicopter base",
        "Attack and transport helicopters close to the troops.",
        BaseKind.AIRFIELD,
        (F, M),
        (
            (Role.ATTACK_HELO, 8),
            (Role.ATTACK_HELO, 8),
            (Role.TRANSPORT_HELO, 8),
        ),
        (Role.ATTACK_HELO,),
    ),
    # Airfields between.
    Template(
        "Balanced wing",
        "One squadron each of fighters, strike, SEAD and close air support.",
        BaseKind.AIRFIELD,
        (M, F, R),
        ((Role.FIGHTER, 12), (Role.STRIKE, 12), (Role.SEAD, 12), (Role.CAS, 12)),
        (Role.FIGHTER,),
    ),
    Template(
        "Air superiority",
        "Three fighter squadrons.",
        BaseKind.AIRFIELD,
        (M, F),
        ((Role.FIGHTER, 12), (Role.FIGHTER, 12), (Role.FIGHTER, 12)),
        (Role.FIGHTER,),
    ),
    Template(
        "Deep strike",
        "Two strike squadrons with SEAD and escorts, for targets far behind the front.",
        BaseKind.AIRFIELD,
        (M, R),
        ((Role.STRIKE, 12), (Role.STRIKE, 12), (Role.SEAD, 12), (Role.FIGHTER, 12)),
        (Role.STRIKE,),
    ),
    Template(
        "Maritime strike",
        "Anti-ship squadrons with fighter cover.",
        BaseKind.AIRFIELD,
        (M, R),
        ((Role.ANTISHIP, 12), (Role.ANTISHIP, 12), (Role.FIGHTER, 12)),
        (Role.ANTISHIP,),
    ),
    # Airfields far from the battle.
    Template(
        "Support",
        "AEW&C, tankers and airlift.",
        BaseKind.AIRFIELD,
        (R, M),
        ((Role.AEW, 4), (Role.TANKER, 4), (Role.TANKER, 4), (Role.AIRLIFT, 6)),
    ),
    Template(
        "Heavy strike",
        "Bombers or strike aircraft with escorts and a tanker.",
        BaseKind.AIRFIELD,
        (R,),
        ((Role.BOMBER, 6), (Role.STRIKE, 12), (Role.FIGHTER, 12), (Role.TANKER, 4)),
        (Role.STRIKE,),
    ),
    Template(
        "Rear air defense",
        "Fighters and AEW&C to guard the rear.",
        BaseKind.AIRFIELD,
        (R,),
        ((Role.FIGHTER, 12), (Role.FIGHTER, 12), (Role.AEW, 4)),
        (Role.FIGHTER,),
    ),
    Template(
        "Strategic bombers",
        "Bombers entering at the map edge from the off-map base.",
        BaseKind.OFF_MAP,
        None,
        ((Role.BOMBER, 4), (Role.BOMBER, 4)),
        (Role.BOMBER,),
    ),
)


def _flies_from(kind: BaseKind, aircraft: AircraftType) -> bool:
    if kind is BaseKind.CARRIER:
        return bool(aircraft.carrier_capable)
    if kind is BaseKind.LHA:
        return bool(aircraft.lha_capable)
    return True


def _score(aircraft: AircraftType, tasks: tuple[FlightType, ...]) -> int:
    # The first task counts in full, the others only to break ties.
    best = 0
    for i, task in enumerate(tasks):
        if aircraft.capable_of(task):
            best = max(best, aircraft.task_priority(task) * (1000 if i == 0 else 1))
    return best


def family(aircraft: AircraftType) -> str:
    """The model family (F-14, AH-64, Ka-50, Su-25): variants and AI-only
    copies of one jet share it."""
    name = re.sub(r"^\[[^\]]*\]\s*", "", aircraft.variant_id)
    match = re.match(r"([A-Za-z/]+[- ]?\d+)", name)
    return match.group(1) if match else name


#: A second slot takes another family's jet only when it scores this close.
CLOSE_SCORE = 0.8


def _ai_copy(aircraft: AircraftType, taken: list[AircraftType]) -> bool:
    base = aircraft.variant_id.replace(" (AI)", "")
    return any(t.variant_id.replace(" (AI)", "") == base for t in taken)


def scored_for_role(
    aircraft: Iterable[AircraftType], role: Role, kind: BaseKind
) -> list[tuple[AircraftType, int]]:
    """The aircraft that can fill the role from this kind of base, with
    their scores, best first."""
    tasks, allowed = ROLES[role]
    usable = [a for a in aircraft if allowed(a) and _flies_from(kind, a)]
    scored = [(a, _score(a, tasks)) for a in usable]
    scored = [(a, s) for a, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].variant_id))
    if kind is BaseKind.CARRIER:
        # STOVL jets belong on the LHA; on a carrier only when nothing else can.
        conventional = [(a, s) for a, s in scored if not _stovl(a)]
        if conventional:
            return conventional
    return scored


def _stovl(aircraft: AircraftType) -> bool:
    return bool(aircraft.lha_capable) and not aircraft.helicopter


def ranked_for_role(
    aircraft: Iterable[AircraftType], role: Role, kind: BaseKind
) -> list[AircraftType]:
    """The aircraft that can fill the role from this kind of base, best first."""
    return [a for a, _ in scored_for_role(aircraft, role, kind)]


def faction_aircraft(faction: Faction) -> list[AircraftType]:
    return [a for a in faction.all_aircrafts if isinstance(a, AircraftType)]


def build(template: Template, aircraft: list[AircraftType]) -> Optional[PresetGroup]:
    """The template filled with the faction's aircraft, or None if a
    required role can't be filled."""
    squadrons: list[PresetSquadronConfig] = []
    used: dict[Role, list[AircraftType]] = {}
    filled: set[Role] = set()
    for role, size in template.slots:
        scored = scored_for_role(aircraft, role, template.kind)
        ranked = [a for a, _ in scored]
        if not ranked:
            continue
        taken = used.setdefault(role, [])
        # A second slot of the role takes another airframe (not the same jet
        # under another name, like an AI-only copy), else the same one.
        # A close second from another family (an AH-1W next to the AH-64);
        # else another variant (the F/A-18E next to the F/A-18C).
        families = {family(a) for a in taken}
        close = [a for a, score in scored if score >= scored[0][1] * CLOSE_SCORE]
        choice = next(
            (a for a in close if family(a) not in families),
            next(
                (a for a in ranked if a not in taken and not _ai_copy(a, taken)),
                ranked[0],
            ),
        )
        taken.append(choice)
        filled.add(role)
        capabilities = [
            t for t in choice.iter_task_capabilities() if t is not PRIMARY[role]
        ]
        primary = PRIMARY[role]
        if not choice.capable_of(primary):
            primary = next(iter(choice.iter_task_capabilities()))
        squadrons.append(
            PresetSquadronConfig(
                primary=primary,
                secondary=capabilities,
                aircraft=[choice.variant_id],
                max_size=size,
                name=None,
                nickname=None,
                female_pilot_percentage=None,
                aircraft_type=choice.variant_id,
            )
        )
    if not squadrons or any(r not in filled for r in template.required):
        return None
    return PresetGroup(template.kind, 1, Placement.ANY, squadrons)


def faction_presets(faction: Faction) -> list[AirWingPreset]:
    """One preset per template the faction can fill, all of its own aircraft."""
    aircraft = faction_aircraft(faction)
    presets: list[AirWingPreset] = []
    seen: set[tuple[BaseKind, tuple[str, ...]]] = set()
    for template in TEMPLATES:
        group = build(template, aircraft)
        if group is None:
            continue
        key = (template.kind, tuple(s.aircraft[0] for s in group.squadrons))
        if key in seen:
            continue  # Same squadrons as an earlier template.
        seen.add(key)
        presets.append(
            AirWingPreset(
                name=template.name,
                description=template.description,
                era=None,
                side=None,
                groups=[group],
            )
        )
    return presets


@dataclass(frozen=True)
class BaseChoice:
    """A preset offered for one base."""

    base_preset: BasePreset
    #: Made from the faction's aircraft (else a hand-made preset).
    generated: bool

    @property
    def label(self) -> str:
        if self.generated:
            return f"{self.base_preset.preset.name}: {self.summary}"
        return f"{self.base_preset.preset.name} (historical): {self.summary}"

    @property
    def summary(self) -> str:
        counts: dict[str, int] = {}
        for config in self.base_preset.group.squadrons:
            name = config.aircraft[0] if config.aircraft else (config.squadron or "?")
            counts[name] = counts.get(name, 0) + config.max_size
        return ", ".join(f"{n} ×{c}" for n, c in counts.items())


def _template_for(name: str) -> Optional[Template]:
    return next((t for t in TEMPLATES if t.name == name), None)


def presets_for_base(
    faction: Faction,
    ranked: RankedBase,
    year: int,
    handmade: Iterable[AirWingPreset] = (),
    generated: Optional[list[AirWingPreset]] = None,
) -> list[BaseChoice]:
    """The presets offered for one base: the faction's own (by base kind and
    band), then the hand-made groups for it whose aircraft the faction has."""
    choices: list[BaseChoice] = []
    if generated is None:
        generated = faction_presets(faction)
    for preset in generated:
        group = preset.groups[0]
        if group.base is not ranked.kind:
            continue
        template = _template_for(preset.name)
        if (
            ranked.band is not None
            and template is not None
            and template.bands is not None
            and ranked.band not in template.bands
        ):
            continue
        choices.append(BaseChoice(BasePreset(preset, group), True))
    if ranked.band is not None:
        # The band's own templates first, in the order they are listed for it.
        def order(choice: BaseChoice) -> int:
            template = _template_for(choice.base_preset.preset.name)
            if template is None or template.bands is None:
                return 0
            return template.bands.index(ranked.band)

        choices.sort(key=order)
    available = {a.variant_id for a in faction_aircraft(faction)}
    for base_preset in base_presets_for(handmade, ranked, year):
        usable = all(
            any(name in available for name in config.aircraft)
            for config in base_preset.group.squadrons
        )
        if usable:
            choices.append(BaseChoice(base_preset, False))
    # Only presets the base can take every squadron of (a FOB: helicopters).
    return [c for c in choices if _base_takes(ranked, c)]


def _base_takes(ranked: RankedBase, choice: BaseChoice) -> bool:
    for config in choice.base_preset.group.squadrons:
        types = []
        for name in config.aircraft:
            try:
                types.append(AircraftType.named(name))
            except KeyError:
                continue
        if types and not any(ranked.base.can_operate(t) for t in types):
            return False
    return True
