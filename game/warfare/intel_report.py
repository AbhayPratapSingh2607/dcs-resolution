"""What the player's intelligence picture looks like, for the Intelligence
window's "Intel picture" page.

Everything here is from blue's point of view: our own resolve and front
morale exactly, the enemy's as a judgement, and enemy sites only as blue
knows them (fog of war). A false report looks like any other contact.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING

from game.theater.player import Player

if TYPE_CHECKING:
    from game import Game


#: Readable names for ground object categories.
CATEGORY_NAMES = {
    "aa": "air defense",
    "ewr": "early warning radar",
    "armor": "armor",
    "missile": "missile site",
    "coastal": "coastal defense",
    "ammo": "ammo depot",
    "factory": "factory",
    "fob": "forward base",
    "oil": "oil",
    "comms": "comms",
    "power": "power plant",
    "commandcenter": "command center",
    "fuel": "fuel depot",
    "ware": "warehouse",
    "farp": "FARP",
    "derrick": "derrick",
    "motorpool": "motor pool",
    "ship": "ship",
}


def category_name(category: str) -> str:
    return CATEGORY_NAMES.get(category, category)


@dataclass(frozen=True)
class ContactRow:
    name: str
    base: str
    kind: str
    status: str  # confirmed | unconfirmed | believed destroyed
    source: str
    last_seen: str
    #: For sorting, latest first; -1 for pre-war.
    last_seen_turn: int
    confidence: int  # percent
    uncertainty_km: float

    @property
    def position_error(self) -> str:
        if self.status == "confirmed":
            return "exact"
        if self.uncertainty_km < 0.1:
            return "<0.1 km"
        return f"~{self.uncertainty_km:.1f} km"


@dataclass(frozen=True)
class FrontMorale:
    base: str
    enemy_base: str
    morale: str


@dataclass
class IntelReport:
    #: None when war-weariness is off.
    own_resolve: Optional[str] = None
    enemy_resolve: Optional[str] = None
    collateral_incidents: int = 0
    fronts: list[FrontMorale] = field(default_factory=list)
    #: None when the intel model is off.
    isr: Optional[int] = None
    humint: Optional[int] = None
    sigint: Optional[int] = None
    contacts: list[ContactRow] = field(default_factory=list)
    by_source: Counter[str] = field(default_factory=Counter)

    @property
    def confirmed(self) -> int:
        return sum(1 for c in self.contacts if c.status == "confirmed")

    @property
    def believed_destroyed(self) -> int:
        return sum(1 for c in self.contacts if c.status == "believed destroyed")


def build_intel_report(game: Game) -> IntelReport:
    from game.server.fogofwar import fog_mode
    from game.settings.settings import FogOfWar

    report = IntelReport()
    war_state = getattr(game, "war_state", None)
    if war_state is None:
        return report

    if war_state.morale_enabled(game) and getattr(
        game.settings, "war_weariness_enabled", True
    ):
        from .morale import describe

        morale = war_state.morale
        report.own_resolve = describe(morale.national_resolve(Player.BLUE))
        report.enemy_resolve = "~" + describe(morale.national_resolve(Player.RED))
        report.collateral_incidents = war_state.collateral_incidents.get(True, 0)
    if war_state.morale_enabled(game):
        from .morale import describe

        for front in game.theater.conflicts():
            report.fronts.append(
                FrontMorale(
                    front.blue_cp.name,
                    front.red_cp.name,
                    describe(war_state.morale.front(front.blue_cp)),
                )
            )

    if fog_mode(game) is FogOfWar.OFF:
        return report
    picture = war_state.picture(game, Player.BLUE)
    report.isr = round(picture.isr * 100)
    if getattr(game.settings, "space_and_agency_intel", True):
        from .agencies import reliability

        report.humint = round(reliability(game, war_state, Player.BLUE, "humint") * 100)
        report.sigint = round(reliability(game, war_state, Player.BLUE, "sigint") * 100)
    report.contacts = _contacts(game, picture)
    report.by_source = Counter(c.source for c in report.contacts)
    return report


def _contacts(game: Game, picture: object) -> list[ContactRow]:
    from .intel import IntelPicture, IntelSource, always_visible, enemy_ground_objects

    assert isinstance(picture, IntelPicture)
    rows: list[ContactRow] = []
    for tgo in enemy_ground_objects(game, Player.BLUE):
        if tgo.is_control_point or always_visible(tgo):
            continue
        contact = picture.contact(tgo)
        if contact is None or not contact.known:
            continue
        if not picture.believed_alive(tgo):
            status = "believed destroyed"
        elif picture.confirmed(tgo):
            status = "confirmed"
        else:
            status = "unconfirmed"
        prewar = contact.source is IntelSource.PREWAR
        rows.append(
            ContactRow(
                name=tgo.name,
                base=tgo.control_point.name,
                kind=(
                    category_name(getattr(tgo, "category", "site"))
                    if status == "confirmed"
                    else "unknown"
                ),
                status=status,
                source=contact.source.value,
                last_seen="pre-war" if prewar else f"turn {contact.last_seen_turn}",
                last_seen_turn=-1 if prewar else contact.last_seen_turn,
                confidence=round(contact.confidence * 100),
                uncertainty_km=round(picture.error_m(tgo) / 1000, 1),
            )
        )
    # False reports are planned around like real ones and look the same.
    red_bases = list(game.theater.control_points_for(Player.RED))
    for phantom in picture.phantoms.values():
        base = ""
        if red_bases:
            base = min(
                red_bases,
                key=lambda cp: (cp.position.x - phantom.x) ** 2
                + (cp.position.y - phantom.y) ** 2,
            ).name
        rows.append(
            ContactRow(
                name=f"Reported {phantom.kind} site",
                base=base,
                kind="unknown",
                status="unconfirmed",
                source=IntelSource.AGENT.value,
                last_seen=f"turn {phantom.reported_turn}",
                last_seen_turn=phantom.reported_turn,
                confidence=round(phantom.confidence * 100),
                uncertainty_km=round(phantom.error_m / 1000, 1),
            )
        )
    rows.sort(key=lambda r: (-r.last_seen_turn, r.base, r.name))
    return rows
