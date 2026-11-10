import logging

from dcs.point import MovingPoint
from dcs.task import AttackGroup, Expend, OptFormation, WeaponType

from game.missiongenerator.aircraft.defendedtarget import target_area_defended
from game.theater import TheaterGroundObject
from game.transfers import MultiGroupTransport
from .pydcswaypointbuilder import PydcsWaypointBuilder

# Rockets and bombs: the unguided weapons minus the cannon.
UNGUIDED_NO_GUN = WeaponType.Unguided.value & ~WeaponType.Cannon.value


class BaiIngressBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        self.register_special_ingress_points()
        if not self.flight.is_helo:
            waypoint.tasks.append(OptFormation.trail_open())
        # TODO: Add common "UnitGroupTarget" base type.
        group_names = []
        target = self.package.target
        if isinstance(target, TheaterGroundObject):
            for group in target.groups:
                group_names.append(group.group_name)
        elif isinstance(target, MultiGroupTransport):
            group_names.append(target.name)
        else:
            logging.error(
                "Unexpected target type for BAI mission: %s",
                target.__class__.__name__,
            )
            return

        defended = target_area_defended(self.flight)
        for group_name in group_names:
            miz_group = self.mission.find_group(group_name)
            if miz_group is None:
                logging.error("Could not find group for BAI mission %s", group_name)
                continue

            if defended:
                self.add_defended_target_attack(waypoint, miz_group.id)
            else:
                task = AttackGroup(miz_group.id, weapon_type=WeaponType.Auto)
                waypoint.tasks.append(task)

    def add_defended_target_attack(self, waypoint: MovingPoint, group_id: int) -> None:
        """Attacks with primary munitions only, then lets the flight egress.

        WeaponType.Auto lets the AI keep re-attacking with whatever is left, which ends
        in low altitude gun runs through the target's air defenses. Instead, release
        guided weapons from the ingress altitude, then make a single pass with any
        rockets and bombs. Neither task permits the cannon, so once they complete the
        flight moves on to its egress waypoint.
        """
        waypoint.tasks.append(
            AttackGroup(
                group_id,
                weapon_type=WeaponType.Guided,
                expend=Expend.All,
                altitude=waypoint.alt,
                group_attack=True,
            )
        )
        unguided = AttackGroup(group_id, attack_limit=1, expend=Expend.All)
        unguided.params["weaponType"] = UNGUIDED_NO_GUN
        waypoint.tasks.append(unguided)
