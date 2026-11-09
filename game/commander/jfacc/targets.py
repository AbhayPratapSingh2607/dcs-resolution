"""Target nomination: the Joint Integrated Prioritized Target List (JIPTL).

Only targets the side has detected and believes alive are nominated. Each
nomination carries the desired effect for its target class and the effect
assessed from BDA so far. Targets drop off the list once BDA says the desired
effect has been achieved, and come back for restrike when it falls short.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterator, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from .assessment import CampaignAssessment, believed_destroyed_fraction
from .campaignstate import NominationSnapshot, SideCampaign
from .intelview import believed_live_radar_sam, estimated_parked
from .profile import Category, Phase, PlanningProfile, TargetSystem
from .targetclass import MOBILE_CLASSES, classify, target_key

if TYPE_CHECKING:
    from game import Game
    from game.theater import MissionTarget
    from game.theater.player import Player


#: Target class -> (mission type, apportionment category).
TASKING: dict[str, tuple[FlightType, Category]] = {
    "sam_lorad": (FlightType.DEAD, Category.SEAD),
    "sam_merad": (FlightType.DEAD, Category.SEAD),
    "sam_shorad": (FlightType.DEAD, Category.SEAD),
    "ewr": (FlightType.DEAD, Category.SEAD),
    "c2_node": (FlightType.STRIKE, Category.STRIKE),
    "power": (FlightType.STRIKE, Category.STRIKE),
    "airfield": (FlightType.OCA_RUNWAY, Category.OCA),
    "factory": (FlightType.STRIKE, Category.STRIKE),
    "ammo": (FlightType.STRIKE, Category.INTERDICTION),
    "fuel": (FlightType.STRIKE, Category.STRIKE),
    "building": (FlightType.STRIKE, Category.STRIKE),
    "bridge": (FlightType.STRIKE, Category.INTERDICTION),
    "armor": (FlightType.BAI, Category.INTERDICTION),
    "motorpool": (FlightType.BAI, Category.INTERDICTION),
    "convoy": (FlightType.BAI, Category.INTERDICTION),
    "ship": (FlightType.ANTISHIP, Category.STRIKE),
}

NM = 1852.0


@dataclass
class TargetNomination:
    target: MissionTarget
    key: str
    system: TargetSystem
    target_class: str
    mission: FlightType
    category: Category
    priority: float
    desired_effect: float
    assessed_effect: float
    bda_confidence: float
    confidence: float
    status: str
    #: Risk tier used to scale the acceptable attrition.
    risk_kind: str = "routine"
    rank: int = 0

    @property
    def name(self) -> str:
        return self.target.name


class TargetNominator:
    def __init__(
        self,
        game: Game,
        player: Player,
        profile: PlanningProfile,
        side: SideCampaign,
        assessment: CampaignAssessment,
        phase: Phase,
    ) -> None:
        self.game = game
        self.player = player
        self.profile = profile
        self.side = side
        self.assessment = assessment
        self.phase = phase
        from game.commander.objectivefinder import ObjectiveFinder

        self.finder = ObjectiveFinder(game, player)

    # ---------------------------------------------------------------- helpers

    def _flag(self, name: str) -> bool:
        spec = self.profile.phases.get(self.phase)
        return bool(spec.flag(name, False)) if spec is not None else False

    def _picture_contact(self, tgo: object) -> Optional[object]:
        war_state = getattr(self.game, "war_state", None)
        if war_state is None or not war_state.intel_enabled(self.game):
            return None
        return war_state.picture(self.game, self.player).contact(tgo)

    def _reference_points(self) -> list[object]:
        effort = self.assessment.main_effort
        if effort is not None:
            return [effort.front]
        return list(self.finder.friendly_control_points())

    def _proximity(self, target: MissionTarget) -> float:
        refs = self._reference_points()
        if not refs:
            return 1.0
        distance = min(target.distance_to(ref) for ref in refs)  # type: ignore[arg-type]
        # Strategic targets matter regardless of depth; others decay with it.
        scale = 250 if self._flag("strategic_reach") else 120
        return 0.4 + 0.6 * math.exp(-distance / (scale * NM))

    def _candidates(self) -> Iterator[MissionTarget]:
        from game.theater.theatergroundobject import (
            IadsGroundObject,
            VehicleGroupGroundObject,
        )

        seen: set[str] = set()

        def fresh(target: MissionTarget) -> bool:
            key = target_key(target)
            if key in seen:
                return False
            seen.add(key)
            return True

        for sam in self.finder.enemy_air_defenses():
            if isinstance(sam, IadsGroundObject) and fresh(sam):
                yield sam
        for building in self.finder.strike_targets():
            if fresh(building):
                yield building
        for cp in self.finder.enemy_control_points():
            for tgo in cp.ground_objects:
                if not isinstance(tgo, VehicleGroupGroundObject) or tgo.is_dead:
                    continue
                if self.finder.known(tgo) and fresh(tgo):
                    yield tgo
        for ship in self.finder.enemy_ships():
            if self.finder.known(ship) and fresh(ship):
                yield ship
        for motorpool in self.finder.motorpool_targets():
            if self.finder.known(motorpool) and fresh(motorpool):
                yield motorpool
        min_aircraft = max(
            4, int(self.game.settings.oca_target_autoplanner_min_aircraft_count) // 2
        )
        for airfield in self.finder.oca_targets(min_aircraft):
            if fresh(airfield):
                yield airfield
        for convoy in self.finder.convoys():
            if fresh(convoy):
                yield convoy
        for cargo in self.finder.cargo_ships():
            if fresh(cargo):
                yield cargo

    # -------------------------------------------------------------- nominate

    def _assess(self, target: MissionTarget, target_class: str) -> tuple[float, float]:
        from game.theater import ControlPoint
        from game.theater.theatergroundobject import TheaterGroundObject

        if isinstance(target, TheaterGroundObject):
            if target_class in ("sam_lorad", "sam_merad", "sam_shorad") and (
                not believed_live_radar_sam(self.game, self.player, target)
            ):
                # Radars down: suppressed even if launchers survive.
                destroyed, confidence = believed_destroyed_fraction(
                    self.game, self.player, target
                )
                return max(destroyed, 0.5), confidence
            return believed_destroyed_fraction(self.game, self.player, target)
        if isinstance(target, ControlPoint):
            return (0.0 if target.runway_is_operational() else 0.6), 1.0
        return 0.0, 1.0

    def _confidence(self, target: MissionTarget, target_class: str) -> tuple[float, bool]:
        """Intel confidence, and whether the contact is too stale to strike."""
        from game.theater.theatergroundobject import TheaterGroundObject

        if not isinstance(target, TheaterGroundObject):
            return 1.0, False
        contact = self._picture_contact(target)
        if contact is None:
            return 1.0, False
        confidence = float(getattr(contact, "confidence", 1.0))
        last_seen = int(getattr(contact, "last_seen_turn", -1))
        max_age = int(self.profile.raw.get("mobile_target_max_age_turns", 2))
        stale = (
            target_class in MOBILE_CLASSES
            and last_seen >= 0
            and self.game.turn - last_seen > max_age
            and not getattr(contact, "confirmed", False)
        )
        return confidence, stale

    def _risk_kind(self, target: MissionTarget, system: TargetSystem) -> str:
        if self._flag("defense_priority") and system in (
            TargetSystem.FIELDED,
            TargetSystem.LOC,
        ):
            return "defense"
        if system in (TargetSystem.C2, TargetSystem.IADS):
            return "hvt"
        return "routine"

    def _value(self, target: MissionTarget, target_class: str) -> float:
        from game.theater import ControlPoint

        value = self.profile.effect_for(target_class).value
        if isinstance(target, ControlPoint):

            present = estimated_parked(self.game, self.player, target)
            value *= min(1.5, 0.4 + present / 16)
        return value

    def nominate(self) -> list[TargetNomination]:
        from game.theater.theatergroundobject import TheaterGroundObject

        nominations: list[TargetNomination] = []
        turn = self.game.turn
        for target in self._candidates():
            system, target_class = classify(target)
            mission, category = TASKING.get(
                target_class, (FlightType.STRIKE, Category.STRIKE)
            )
            if target_class == "sam_shorad" and not (
                isinstance(target, TheaterGroundObject)
                and believed_live_radar_sam(self.game, self.player, target)
            ):
                # AAA and IR SHORAD are avoided by flying medium altitude, not
                # hunted (Desert Storm practice).
                continue
            effect = self.profile.effect_for(target_class)
            key = target_key(target)
            record = self.side.targets.get(key)
            assessed, bda_confidence = self._assess(target, target_class)
            if record is not None:
                record.assessed_effect = assessed
                record.bda_confidence = bda_confidence
            confidence, stale = self._confidence(target, target_class)
            if effect.destroy > 0 and assessed >= effect.destroy:
                status = "effect achieved"
                remaining = 0.0
            elif record is not None and record.strikes > 0:
                status = "restrike" if assessed < effect.restrike_below else "assess"
                remaining = 1.0 - assessed / max(effect.destroy, 0.01)
                if status == "assess":
                    remaining *= 0.3
            else:
                status = "nominated"
                remaining = 1.0 - (
                    assessed / effect.destroy if effect.destroy > 0 else 0.0
                )
            if stale:
                status = "stale intel"
            priority = (
                self.profile.system_weight(self.phase, system)
                * self._value(target, target_class)
                * self._proximity(target)
                * max(0.2, confidence)
                * max(0.0, remaining)
            )
            if stale or remaining <= 0:
                priority = 0.0
            nominations.append(
                TargetNomination(
                    target=target,
                    key=key,
                    system=system,
                    target_class=target_class,
                    mission=mission,
                    category=category,
                    priority=priority,
                    desired_effect=effect.destroy,
                    assessed_effect=assessed,
                    bda_confidence=bda_confidence,
                    confidence=confidence,
                    status=status,
                    risk_kind=self._risk_kind(target, system),
                )
            )
        nominations.sort(key=lambda n: -n.priority)
        for rank, nomination in enumerate(nominations, start=1):
            nomination.rank = rank
            if nomination.priority > 0:
                self.side.record(nomination.key, nomination.name, turn)
        return nominations


def snapshot(nominations: list[TargetNomination], planned: set[str]) -> list[NominationSnapshot]:
    return [
        NominationSnapshot(
            rank=n.rank,
            key=n.key,
            name=n.name,
            system=n.system,
            target_class=n.target_class,
            priority=n.priority,
            confidence=n.confidence,
            desired_effect=n.desired_effect,
            assessed_effect=n.assessed_effect,
            bda_confidence=n.bda_confidence,
            status=n.status,
            planned=n.key in planned,
        )
        for n in nominations
    ]
