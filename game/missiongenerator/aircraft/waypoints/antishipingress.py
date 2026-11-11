import logging
import math
from typing import Iterable, List, Optional, Sequence

from dcs.point import MovingPoint
from dcs.task import AttackGroup, AttackUnit, Expend, OptFormation, WeaponType

from game.theater import NavalControlPoint, TheaterGroundObject
from .pydcswaypointbuilder import PydcsWaypointBuilder

#: Anti-ship missiles lock the first ship their seeker finds on the way in,
#: not necessarily the one they were fired at (Tacview, PG turn 2: TAURUS's
#: Harpoons sank a LORIKEET boat 7.6 km off their path, 15 km short of their
#: own target; LORIKEET's three went to the first of two boats side by side,
#: 2 km apart). A ship is in the way of an attack from a bearing when it is
#: within ``CORRIDOR_M`` of the attack line, on the attacker's side of the
#: target or abeam it (less than ``BEHIND_M`` behind), and within ``REACH_M``.
CORRIDOR_M = 12_000.0
BEHIND_M = 500.0
REACH_M = 60_000.0
#: Bearings tried each side of the ingress bearing, at most this far off.
BEARING_STEP = 10.0
MAX_SHIFT = 90.0


def _bearing(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Bearing from a to b in degrees, DCS axes (x north, y east)."""
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 360


def blocking_ships(
    target: tuple[float, float],
    bearing: float,
    others: Iterable[tuple[float, float]],
) -> int:
    """How many of the other ships are in the way of an attacker coming in
    from ``bearing`` (from the target toward the attacker)."""
    ux, uy = math.cos(math.radians(bearing)), math.sin(math.radians(bearing))
    count = 0
    for ship in others:
        dx, dy = ship[0] - target[0], ship[1] - target[1]
        if math.hypot(dx, dy) < 1.0:
            continue
        along = dx * ux + dy * uy
        across = abs(dx * uy - dy * ux)
        if -BEHIND_M < along < REACH_M and across < CORRIDOR_M:
            count += 1
    return count


def attack_bearing(
    target: tuple[float, float],
    ingress: tuple[float, float],
    others: Sequence[tuple[float, float]],
) -> Optional[float]:
    """The attack bearing for one ship (from the ship toward the attacker):
    the one nearest the bearing to the ingress point with no other ship in
    the way, else the one with the fewest. None when nothing is in the way
    on the ingress bearing (no need to force a direction)."""
    base = _bearing(target, ingress)
    if blocking_ships(target, base, others) == 0:
        return None
    best: Optional[tuple[int, float, float]] = None
    for k in range(1, int(MAX_SHIFT / BEARING_STEP) + 1):
        for sign in (1, -1):
            bearing = (base + sign * k * BEARING_STEP) % 360
            blocked = blocking_ships(target, bearing, others)
            if blocked == 0:
                return bearing
            key = (blocked, k * BEARING_STEP, bearing)
            if best is None or key < best:
                best = key
    return best[2] if best is not None else None


class AntiShipIngressBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        self.register_special_ingress_points()
        group_names = []
        waypoint.tasks.append(OptFormation.finger_four_open())

        target = self.package.target
        if isinstance(target, NavalControlPoint):
            # Use find_main_tgo() like the flight plan does: ground_objects[0]
            # isn't necessarily the carrier (it may be a sunk, never-spawned
            # group), which would leave the flight with no AttackGroup target.
            carrier_tgo = target.find_main_tgo()
            for g in carrier_tgo.groups:
                group_names.append(g.group_name)
        elif isinstance(target, TheaterGroundObject):
            for group in target.groups:
                group_names.append(group.group_name)
        else:
            logging.error(
                "Unexpected target type for Anti-Ship mission: %s",
                target.__class__.__name__,
            )
            return

        # One missile at each ship first, then the rest at the group: one
        # AttackGroup alone put the whole flight's load on the first ship DCS
        # picked and left the others untouched.
        self.add_attack_unit_tasks(waypoint, group_names)
        added = 0
        for ordnance in (
            WeaponType.Antiship,
            WeaponType.Guided,
            WeaponType.Unguided,
        ):
            added += self.add_attack_group_tasks_for_ordnance(
                waypoint, group_names, ordnance
            )

        if not added:
            # No AttackGroup task could be attached, so the AI would fly to the
            # ingress point and turn back without engaging. Make this loud: it
            # almost always means the target group(s) were never spawned (e.g.
            # already destroyed) or the resolved name does not match a mission
            # group.
            logging.warning(
                "Anti-Ship flight %s has no attackable target group "
                "(resolved %s); it will not engage anything.",
                self.flight,
                group_names or "no groups",
            )

    def _enemy_ships(self) -> list[tuple[int, tuple[float, float]]]:
        """(unit id, position) of every enemy ship in the mission."""
        enemy = "red" if self.flight.blue.is_blue else "blue"
        ships: list[tuple[int, tuple[float, float]]] = []
        coalition = self.mission.coalition.get(enemy)
        if coalition is None:
            return ships
        for country in coalition.countries.values():
            for group in country.ship_group:
                for unit in group.units:
                    ships.append((unit.id, (unit.position.x, unit.position.y)))
        return ships

    def add_attack_unit_tasks(
        self, waypoint: MovingPoint, group_names: List[str]
    ) -> int:
        """An AttackUnit for each ship of the target (one attack run, one
        anti-ship missile, every aircraft for itself), each from a bearing
        with no other ship in the way: the seeker locks the first ship it
        finds, so a salvo down one line all goes to the nearest ship."""
        added = 0
        try:
            ships = self._enemy_ships()
        except Exception:
            logging.exception("Could not list the enemy ships for the attack bearings")
            ships = []
        ingress = (waypoint.position.x, waypoint.position.y)
        for group_name in group_names:
            miz_group = self.mission.find_group(group_name)
            if miz_group is None:
                continue
            units = list(miz_group.units)
            for unit in units:
                position = (unit.position.x, unit.position.y)
                others = [p for uid, p in ships if uid != unit.id]
                bearing = attack_bearing(position, ingress, others)
                if len(units) < 2 and bearing is None:
                    continue
                waypoint.tasks.append(
                    AttackUnit(
                        unit.id,
                        attack_limit=1,
                        weapon_type=WeaponType.Antiship,
                        group_attack=False,
                        direction_enabled=bearing is not None,
                        direction=math.radians(bearing) if bearing is not None else 0,
                        expend=Expend.One,
                    )
                )
                added += 1
        return added

    def add_attack_group_tasks_for_ordnance(
        self,
        waypoint: MovingPoint,
        group_names: List[str],
        ordnance: WeaponType,
    ) -> int:
        added = 0
        for group_name in group_names:
            miz_group = self.mission.find_group(group_name)
            if miz_group is None:
                logging.error(
                    "Could not find group for Anti-Ship mission %s", group_name
                )
                continue

            # expend=All so the AI empties its anti-ship load on the target instead of
            # DCS's default Auto salvo (which fires ~2 and RTBs with the rest). Matches
            # what DEAD does. weapon_type scopes it to the anti-ship ordnance only.
            task = AttackGroup(
                miz_group.id,
                group_attack=True,
                weapon_type=ordnance,
                expend=Expend.All,
            )
            waypoint.tasks.append(task)
            added += 1
        return added
