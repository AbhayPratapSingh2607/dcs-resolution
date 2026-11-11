"""What each side believes about the enemy.

Each side keeps a picture of the enemy's ground objects: which ones it knows
about, how confident it is, roughly where they are, and which of their units it
believes destroyed. The AI plans from this picture, the map shows it to the
player (fog of war), and the combat model gives unknown sites surprise.

Sources, roughly in increasing quality: the pre-war picture, early warning
radars and AWACS listening for emitters (ELINT), pilots seeing things on the
way to their targets, sites revealing themselves by firing, strike crews
reporting what they hit, and dedicated reconnaissance.
"""

from __future__ import annotations

import math
import random
import weakref
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Iterator, Optional, TYPE_CHECKING
from uuid import UUID

from game.theater.player import Player

if TYPE_CHECKING:
    from dcs import Point

    from game import Game
    from game.theater import TheaterGroundObject

#: Confidence at which a contact counts as known (planned around, shown).
KNOWN = 0.35
#: Confidence at which unit lists and ranges are shown (fog of war).
CONFIRMED = 0.8


class IntelSource(Enum):
    PREWAR = "pre-war intelligence"
    ELINT = "ELINT"
    VISUAL = "visual sighting"
    ENGAGEMENT = "engagement"
    STRIKE = "strike report"
    RECON = "reconnaissance"
    SATELLITE = "satellite imagery"
    AGENT = "agency report"
    SIGINT = "signals intelligence"


#: Typical position error of a fix from each source, meters.
SOURCE_ERROR = {
    IntelSource.PREWAR: 1500.0,
    IntelSource.ELINT: 4000.0,
    IntelSource.VISUAL: 1500.0,
    IntelSource.ENGAGEMENT: 3000.0,
    IntelSource.STRIKE: 300.0,
    IntelSource.RECON: 100.0,
    IntelSource.SATELLITE: 60.0,
    IntelSource.AGENT: 6000.0,
    IntelSource.SIGINT: 5000.0,
}

#: Sources whose close look can unmask a decoy.
EXPOSING_SOURCES = {IntelSource.RECON, IntelSource.STRIKE, IntelSource.ENGAGEMENT}

MOBILE_TASKS = {
    "MERAD",
    "SHORAD",
    "AAA",
    "PointDefense",
    "FrontLine",
    "BaseDefense",
    "Missile",
    "Coastal",
    "Motorpool",
}


def is_mobile(tgo: TheaterGroundObject) -> bool:
    task = getattr(tgo, "task", None)
    if task is not None and getattr(task, "description", None) in MOBILE_TASKS:
        return True
    from game.theater.theatergroundobject import (
        VehicleGroupGroundObject,
        MissileSiteGroundObject,
        CoastalSiteGroundObject,
    )

    return isinstance(
        tgo,
        (VehicleGroupGroundObject, MissileSiteGroundObject, CoastalSiteGroundObject),
    )


def always_visible(tgo: TheaterGroundObject) -> bool:
    """Things nobody can hide: carriers and other large ships at sea, and the
    ground objects that make up an airbase or port."""
    from game.theater.theatergroundobject import NavalGroundObject

    return isinstance(tgo, NavalGroundObject) or tgo.is_control_point


@dataclass
class Contact:
    tgo_id: UUID
    confidence: float = 0.0
    known_type: bool = False
    #: Offset of the believed position from the true one, meters.
    offset_x: float = 0.0
    offset_y: float = 0.0
    error_m: float = 5000.0
    #: Ids of units this side believes destroyed.
    believed_dead: set[int] = field(default_factory=set)
    last_seen_turn: int = -1
    source: IntelSource = IntelSource.PREWAR
    #: When set, this side has latched onto one of the site's decoys: the
    #: believed position is the decoy's, and looks convincingly precise.
    decoy_index: Optional[int] = None

    def __setstate__(self, state: dict[str, object]) -> None:
        # Fill fields added after the save was made.
        defaults = Contact(state["tgo_id"]).__dict__  # type: ignore[arg-type]
        self.__dict__.update({**defaults, **state})

    @property
    def known(self) -> bool:
        return self.confidence >= KNOWN

    @property
    def confirmed(self) -> bool:
        return self.confidence >= CONFIRMED and self.error_m <= 1000

    def estimated_position(self, tgo: TheaterGroundObject) -> Point:
        return tgo.position.point_from_heading(
            math.degrees(math.atan2(self.offset_x, self.offset_y)),
            math.hypot(self.offset_x, self.offset_y),
        )


@dataclass
class PhantomContact:
    """A reported enemy site that doesn't exist (a false agency tip). It is
    planned around like a real threat until imagery or recon clears it."""

    id: UUID
    x: float
    y: float
    confidence: float
    error_m: float
    reported_turn: int
    kind: str = "SAM"
    #: Assumed threat radius, meters.
    threat_m: float = 25000.0


@dataclass
class IntelPicture:
    """One side's picture of the enemy."""

    isr: float = 0.7
    contacts: dict[UUID, Contact] = field(default_factory=dict)
    initialized: bool = False
    #: False reports believed real.
    phantoms: dict[UUID, PhantomContact] = field(default_factory=dict)
    #: Quality of the order-of-battle estimate per enemy control point (0..1),
    #: from imagery and agencies. Better than the side's baseline ISR only
    #: where someone looked.
    airbase_quality: dict[UUID, float] = field(default_factory=dict)

    def __setstate__(self, state: dict[str, object]) -> None:
        defaults = IntelPicture().__dict__
        self.__dict__.update({**defaults, **state})

    def estimate_quality(self, control_point_id: UUID) -> float:
        return max(self.isr, self.airbase_quality.get(control_point_id, 0.0))

    # ------------------------------------------------------------------ queries

    def contact(self, tgo: TheaterGroundObject) -> Optional[Contact]:
        return self.contacts.get(tgo.id)

    def knows(self, tgo: TheaterGroundObject) -> bool:
        if always_visible(tgo):
            return True
        contact = self.contacts.get(tgo.id)
        return contact is not None and contact.known

    def confirmed(self, tgo: TheaterGroundObject) -> bool:
        contact = self.contacts.get(tgo.id)
        return contact is not None and contact.confirmed

    def believed_alive(self, tgo: TheaterGroundObject) -> bool:
        """Whether this side thinks the target still has live units. Units the
        side never saw die (missed BDA) are still believed alive."""
        contact = self.contacts.get(tgo.id)
        if contact is None:
            return not tgo.is_dead
        return any(u.id not in contact.believed_dead for u in tgo.units)

    def estimated_position(self, tgo: TheaterGroundObject) -> Point:
        contact = self.contacts.get(tgo.id)
        if contact is None or always_visible(tgo):
            return tgo.position
        return contact.estimated_position(tgo)

    def error_m(self, tgo: TheaterGroundObject) -> float:
        contact = self.contacts.get(tgo.id)
        if contact is None or always_visible(tgo):
            return 0.0
        return contact.error_m

    # ------------------------------------------------------------------ updates

    def _contact_for(self, tgo: TheaterGroundObject) -> Contact:
        contact = self.contacts.get(tgo.id)
        if contact is None:
            contact = Contact(tgo.id)
            self.contacts[tgo.id] = contact
        return contact

    def observe(
        self,
        tgo: TheaterGroundObject,
        quality: float,
        source: IntelSource,
        turn: int,
        rng: random.Random,
    ) -> Contact:
        """Adds an observation of quality 0..1."""
        contact = self._contact_for(tgo)
        quality = max(0.0, min(1.0, quality))
        contact.confidence = 1 - (1 - contact.confidence) * (1 - quality)
        fix_error = SOURCE_ERROR[source] * (1.2 - 0.7 * quality)
        if contact.decoy_index is not None:
            # Fixed on a decoy: further looks confirm the wrong spot unless the
            # look is close enough to see through it (handled by expose()).
            contact.last_seen_turn = turn
            contact.source = source
            return contact
        if fix_error < contact.error_m or contact.last_seen_turn < turn - 1:
            contact.error_m = fix_error
            distance = contact.error_m * math.sqrt(rng.random())
            bearing = rng.uniform(0, 2 * math.pi)
            contact.offset_x = distance * math.sin(bearing)
            contact.offset_y = distance * math.cos(bearing)
        if quality >= 0.5 or source in (
            IntelSource.ENGAGEMENT,
            IntelSource.STRIKE,
            IntelSource.RECON,
        ):
            contact.known_type = True
        if source is IntelSource.RECON:
            # Photographs settle the battle damage question.
            contact.believed_dead = {u.id for u in tgo.units if not u.alive}
        contact.last_seen_turn = turn
        contact.source = source
        return contact

    def report_kill(
        self,
        tgo: TheaterGroundObject,
        unit_id: int,
        reliability: float,
        rng: random.Random,
    ) -> None:
        contact = self._contact_for(tgo)
        if rng.random() < reliability:
            contact.believed_dead.add(unit_id)

    def overclaim(
        self, tgo: TheaterGroundObject, probability: float, rng: random.Random
    ) -> None:
        """Strike crews claim kills they didn't make."""
        contact = self._contact_for(tgo)
        for unit in tgo.units:
            if unit.alive and unit.id not in contact.believed_dead:
                if rng.random() < probability:
                    contact.believed_dead.add(unit.id)

    def latch_decoy(
        self, tgo: TheaterGroundObject, index: int, offset: tuple[float, float]
    ) -> None:
        """This side's picture of the site is now a decoy."""
        contact = self._contact_for(tgo)
        contact.decoy_index = index
        contact.offset_x, contact.offset_y = offset
        contact.error_m = min(contact.error_m, 250.0)
        contact.confidence = max(contact.confidence, 0.85)
        contact.known_type = True

    def expose(self, tgo: TheaterGroundObject, rng: random.Random) -> None:
        """A close look reveals the decoy for what it is; the real site's
        position is again only roughly known."""
        contact = self.contacts.get(tgo.id)
        if contact is None or contact.decoy_index is None:
            return
        contact.decoy_index = None
        contact.error_m = 2500.0
        distance = contact.error_m * math.sqrt(rng.random())
        bearing = rng.uniform(0, 2 * math.pi)
        contact.offset_x = distance * math.sin(bearing)
        contact.offset_y = distance * math.cos(bearing)
        contact.confidence = min(contact.confidence, 0.6)
        contact.believed_dead = {u.id for u in tgo.units if not u.alive}

    def add_phantom(
        self, x: float, y: float, turn: int, rng: random.Random, kind: str = "SAM"
    ) -> PhantomContact:
        import uuid

        phantom = PhantomContact(
            uuid.UUID(int=rng.getrandbits(128)),
            x,
            y,
            confidence=rng.uniform(0.4, 0.6),
            error_m=rng.uniform(3000, 8000),
            reported_turn=turn,
            kind=kind,
        )
        self.phantoms[phantom.id] = phantom
        return phantom

    def clear_phantoms_near(
        self, x: float, y: float, radius_m: float, p: float, rng: random.Random
    ) -> int:
        cleared = 0
        for phantom_id, phantom in list(self.phantoms.items()):
            if (
                math.hypot(phantom.x - x, phantom.y - y) <= radius_m
                and rng.random() < p
            ):
                del self.phantoms[phantom_id]
                cleared += 1
        return cleared

    def scooted(self, tgo: TheaterGroundObject) -> None:
        """A mobile site relocated after firing."""
        contact = self.contacts.get(tgo.id)
        if contact is None:
            return
        contact.confidence *= 0.6
        contact.error_m += 3000

    def decay(self, game: Game, turn: int) -> None:
        # Unconfirmed reports fade if nobody reports them again.
        for phantom_id, phantom in list(self.phantoms.items()):
            if turn - phantom.reported_turn >= 3:
                del self.phantoms[phantom_id]
            else:
                phantom.confidence *= 0.85
        for contact in self.contacts.values():
            if contact.last_seen_turn >= turn:
                continue
            tgo = _tgo_by_id(game, contact.tgo_id)
            if tgo is None:
                continue
            if is_mobile(tgo):
                contact.confidence *= 0.75
                contact.error_m = min(contact.error_m + 1500, 25000)
            else:
                contact.confidence *= 0.97

    def initialize(
        self,
        game: Game,
        viewer: Player,
        prewar_mobile: float,
        rng: random.Random,
    ) -> None:
        """The picture at the start of the war: fixed infrastructure is mostly
        known, mobile forces mostly not."""
        for tgo in enemy_ground_objects(game, viewer):
            if always_visible(tgo):
                continue
            # Pre-war intelligence knows roughly where things are, but confirming
            # what is there takes imagery or reconnaissance.
            if is_mobile(tgo):
                if rng.random() < prewar_mobile:
                    self.observe(tgo, 0.3 + 0.2 * self.isr, IntelSource.PREWAR, 0, rng)
            elif rng.random() < 0.35 + 0.35 * self.isr:
                self.observe(tgo, 0.3 + 0.25 * self.isr, IntelSource.PREWAR, 0, rng)
        self.initialized = True


def enemy_ground_objects(game: Game, viewer: Player) -> Iterator[TheaterGroundObject]:
    for cp in game.theater.control_points_for(viewer.opponent):
        yield from cp.ground_objects


_TGO_INDEX: "weakref.WeakKeyDictionary[Game, dict[UUID, TheaterGroundObject]]" = (
    weakref.WeakKeyDictionary()
)


def _tgo_by_id(game: Game, tgo_id: UUID) -> Optional[TheaterGroundObject]:
    index = _TGO_INDEX.get(game)
    if index is None or tgo_id not in index:
        index = {
            tgo.id: tgo
            for cp in game.theater.controlpoints
            for tgo in cp.ground_objects
        }
        _TGO_INDEX[game] = index
    return index.get(tgo_id)


def tgo_by_id(game: Game, tgo_id: UUID) -> Optional[TheaterGroundObject]:
    return _tgo_by_id(game, tgo_id)


def estimate_count(true_count: int, isr: float, rng: random.Random) -> int:
    """An intelligence estimate of a number of aircraft or vehicles."""
    if true_count <= 0:
        return 0
    spread = 0.5 * (1 - isr)
    return max(0, round(true_count * rng.uniform(1 - spread, 1 + spread)))


def iter_known(
    picture: IntelPicture, tgos: Iterable[TheaterGroundObject]
) -> Iterator[TheaterGroundObject]:
    for tgo in tgos:
        if picture.knows(tgo):
            yield tgo


def player_estimate(
    game: Game,
    owner: Player,
    true_count: int,
    salt: str,
    control_point_id: Optional[UUID] = None,
) -> str:
    """How many of something the player believes the enemy has. Exact for the
    player's own forces or with fog of war off; an estimate otherwise."""
    from game.server.fogofwar import fog_mode
    from game.settings.settings import FogOfWar

    if owner.is_blue or fog_mode(game) is FogOfWar.OFF:
        return str(true_count)
    picture = game.war_state.picture(game, Player.BLUE)
    rng = game.war_state.rng(game, f"estimate:{salt}")
    quality = picture.isr
    if control_point_id is not None:
        quality = picture.estimate_quality(control_point_id)
    return f"~{estimate_count(true_count, quality, rng)}"


def believed_offset(game: Any, viewer: Any, target: Any) -> tuple[float, float]:
    """How far the viewer's picture puts an enemy ground object from where it
    really is (north, east metres): zero for its own objects, for unknown
    ones and with intel off. Flight plans put their target marks there, the
    same place the map shows."""
    from game.theater import TheaterGroundObject

    if not isinstance(target, TheaterGroundObject):
        return 0.0, 0.0
    war_state = getattr(game, "war_state", None)
    if war_state is None or not war_state.intel_enabled(game):
        return 0.0, 0.0
    if target.control_point.captured == viewer:
        return 0.0, 0.0
    picture = war_state.picture(game, viewer)
    if not picture.knows(target):
        return 0.0, 0.0
    believed = picture.estimated_position(target)
    return believed.x - target.position.x, believed.y - target.position.y
