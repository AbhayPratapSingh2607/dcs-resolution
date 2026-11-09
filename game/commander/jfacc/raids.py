"""Massed, echeloned raids (Soviet and Russian air operations).

Western packages put everything a strike needs into one package against one
target. Soviet doctrine instead flies a raid as several groups over the same
target area, minutes apart:

1. **Suppression echelon**: anti-radiation and DEAD groups against the air
   defense sites covering the route, timed to arrive first.
2. **Fighter clearing**: fighters sweep the target area ahead of the strike.
   This is the sweep element of the main group, which flies ahead of it.
3. **Main strike group**: massed strikers against the decisive target, with
   their escort.
4. **Follow-up** (optional): a second strike group that finishes the target.

Each echelon is its own package (its own target and TOT). All of them share
``Package.raid_id`` and carry their ``raid_role``. The raid is planned all
or nothing: if the main strike group can't be composed, the echelons already
committed are released again.

Only the most important targets get raids (``raids.decisive_classes``), at
most ``raids.max_per_period`` per period, and only in phases (or under
modifiers) whose raid style is ``massed``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from .composer import ComposedPackage, FlightRequest, PackageRequest
from .profile import Category
from .targetclass import classify, sam_weight
from . import weaponeering

if TYPE_CHECKING:
    from game.theater.theatergroundobject import TheaterGroundObject
    from .planner import JfaccPlanner
    from .targets import TargetNomination


@dataclass
class Echelon:
    role: str
    offset_min: float
    optional: bool = False


@dataclass
class Raid:
    raid_id: str
    nomination: TargetNomination
    main_tot: datetime
    committed: list[tuple[ComposedPackage, Optional[Category], str]] = field(
        default_factory=list
    )

    @property
    def sorties(self) -> int:
        return sum(c.sorties for c, _, _ in self.committed)


def _echelons(cfg: dict[str, Any]) -> dict[str, Echelon]:
    table: dict[str, Echelon] = {}
    for entry in cfg.get("echelons") or []:
        echelon = Echelon(
            role=str(entry["role"]),
            offset_min=float(entry.get("offset_min", 0)),
            optional=bool(entry.get("optional", False)),
        )
        table[echelon.role] = echelon
    table.setdefault("main", Echelon("main", 0.0))
    return table


class RaidPlanner:
    def __init__(self, planner: JfaccPlanner) -> None:
        self.p = planner
        self.cfg = planner.profile.section("raids")
        self.echelons = _echelons(self.cfg)
        self.raids: list[Raid] = []

    # -------------------------------------------------------------- entry

    def plan(self) -> list[Raid]:
        p = self.p
        limit = int(self.cfg.get("max_per_period", 0))
        if p.raid_style != "massed" or limit <= 0:
            return []
        decisive = set(self.cfg.get("decisive_classes") or [])
        for nomination in p.nominations:
            if len(self.raids) >= limit:
                break
            if nomination.priority <= 0 or nomination.key in p.planned_keys:
                continue
            if nomination.target_class not in decisive:
                continue
            if not p.coalition.air_wing.can_auto_plan(nomination.mission):
                continue
            if p.apportionment.remaining(nomination.category) <= 0:
                continue
            raid = self._plan_raid(nomination)
            if raid is not None:
                self.raids.append(raid)
        return self.raids

    # ------------------------------------------------------------ helpers

    def _main_tot(self, nomination: TargetNomination) -> Optional[datetime]:
        p = self.p
        lead = min((e.offset_min for e in self.echelons.values()), default=0.0)
        tot = p.timeline.strike_tot(
            nomination.target.position, p._wave_preference(nomination.category)
        )
        if tot is None:
            return None
        # The first echelon must still be after the earliest TOT.
        earliest_main = p.timeline.earliest - timedelta(minutes=min(lead, 0.0))
        return max(tot, earliest_main)

    def _route_sams(self, nomination: TargetNomination) -> list[TheaterGroundObject]:
        """The air defense sites the suppression echelon goes after: the
        heaviest radar SAMs on the main group's route, the target excluded."""
        from game.theater.theatergroundobject import SamGroundObject

        target = nomination.target
        exclude = target if isinstance(target, SamGroundObject) else None
        threat = self.p.composer.threat_for(target, exclude=exclude)
        seen: dict[object, TheaterGroundObject] = {}
        for sam in threat.sams:
            if sam is not exclude and sam.id not in self.p.suppressed:
                seen.setdefault(sam.id, sam)
        # threat.sams holds only sites the side believes are live.
        ranked = sorted(seen.values(), key=lambda s: -sam_weight(s, live=True))
        return ranked[: int(self.cfg.get("max_suppression_targets", 2))]

    def _suppression_request(
        self, sam: TheaterGroundObject, raid_name: str
    ) -> Optional[PackageRequest]:
        p = self.p
        air_wing = p.coalition.air_wing
        if air_wing.can_auto_plan(FlightType.DEAD):
            mission = FlightType.DEAD
            _, target_class = classify(sam)
            count = weaponeering.aircraft_needed(
                p.profile, target_class, weaponeering.live_elements(sam)
            )
        elif air_wing.can_auto_plan(FlightType.SEAD):
            mission = FlightType.SEAD
            count = 2
        else:
            return None
        count = max(2, count + count % 2)
        threat = p.composer.threat_for(sam, exclude=sam)
        return PackageRequest(
            target=sam,
            flights=[FlightRequest(mission, count)] + p.composer.support_for(threat, count),
            category_name="sead",
            reason=f"{raid_name}: suppression echelon against {sam.name}",
            risk_kind="hvt",
            threat=threat,
        )

    def _main_request(
        self, nomination: TargetNomination, tot: datetime, raid_name: str
    ) -> PackageRequest:
        p = self.p
        request = p._offensive_request(nomination, tot=tot)
        min_strikers = int(self.cfg.get("min_strikers", 4))
        max_strikers = int(p.profile.get("packages", "max_strikers", 8))
        main = request.flights[0]
        main.count = min(max(main.count, min_strikers), max(max_strikers, main.count))
        main.count += main.count % 2
        threat = request.threat
        if (
            "clearing" in self.echelons
            and threat is not None
            and threat.air_level != "low"
            and not any(f.task is FlightType.SWEEP for f in request.flights)
        ):
            # Fighters clear the target area ahead of the strike group.
            request.flights.append(
                FlightRequest(FlightType.SWEEP, 2, required=False, note="fighter clearing")
            )
        request.reason = f"{raid_name}: main strike group. {request.reason}"
        return request

    def _tag(self, raid: Raid, composed: ComposedPackage, role: str) -> None:
        package = composed.package
        package.raid_id = raid.raid_id
        package.raid_role = role
        if package.planning_info is not None:
            package.planning_info["raid"] = f"{raid.raid_id} ({role.replace('_', ' ')})"

    def _release(self, raid: Raid) -> None:
        p = self.p
        for composed, category, _ in reversed(raid.committed):
            package = composed.package
            tot = package.time_over_target
            if package in p.coalition.ato.packages:
                p.coalition.ato.remove_package(package)
            for allocation in composed.allocations:
                p.ledger.release(allocation)
            if category is not None:
                p.apportionment.spend(category, -composed.sorties)
            p.timeline.unreserve(tot, package.target.position)
            target_id = getattr(package.target, "id", None)
            if target_id is not None and p.suppressed.get(target_id) == tot:
                del p.suppressed[target_id]
        raid.committed.clear()

    # --------------------------------------------------------------- raid

    def _plan_raid(self, nomination: TargetNomination) -> Optional[Raid]:
        p = self.p
        tot = self._main_tot(nomination)
        if tot is None:
            return None
        raid_name = f"Raid on {nomination.name}"
        raid = Raid(f"raid-{p.game.turn}-{len(self.raids) + 1}", nomination, tot)

        suppression = self.echelons.get("suppression")
        if suppression is not None:
            for sam in self._route_sams(nomination):
                request = self._suppression_request(sam, raid_name)
                if request is None:
                    break
                when = tot + timedelta(minutes=suppression.offset_min)
                composed = p._commit(request, when, Category.SEAD, quiet=True)
                if composed is None:
                    continue
                self._tag(raid, composed, "suppression")
                raid.committed.append((composed, Category.SEAD, "suppression"))
                p.suppressed[sam.id] = composed.package.time_over_target

        request = self._main_request(nomination, tot, raid_name)
        cost = sum(f.count for f in request.flights if f.required)
        if not p.apportionment.can_afford(nomination.category, cost):
            self._release(raid)
            return None
        composed = p._commit(request, tot, nomination.category)
        if composed is None:
            logging.info(f"JFACC: {raid_name} scrubbed, releasing its echelons")
            self._release(raid)
            return None
        self._tag(raid, composed, "main")
        raid.committed.append((composed, nomination.category, "main"))
        p._mark_planned(nomination)

        follow_up = self.echelons.get("follow_up")
        if follow_up is not None and p.apportionment.remaining(nomination.category) > 0:
            when = tot + timedelta(minutes=follow_up.offset_min)
            request = p._offensive_request(nomination, tot=when)
            request.reason = f"{raid_name}: follow-up group. {request.reason}"
            extra = p._commit(request, when, nomination.category, quiet=True)
            if extra is not None:
                self._tag(raid, extra, "follow_up")
                raid.committed.append((extra, nomination.category, "follow_up"))
        logging.info(
            f"JFACC: {raid_name}: {len(raid.committed)} echelons, {raid.sorties} sorties"
        )
        return raid
