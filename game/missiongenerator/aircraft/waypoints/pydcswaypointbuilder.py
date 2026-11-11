from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable, Union

from dcs import Mission
from dcs.planes import AJS37, F_14A_135_GR, F_14B, JF_17, F_15ESE
from dcs.point import MovingPoint, PointAction
from dcs.task import RunScript
from dcs.unitgroup import FlyingGroup

from game.ato import Flight, FlightWaypoint
from game.ato.flightwaypointtype import FlightWaypointType
from game.ato.starttype import StartType
from game.ato.traveltime import GroundSpeed
from game.data.weapons import WeaponType
from game.missiongenerator.missiondata import MissionData
from game.theater import MissionTarget, TheaterUnit, OffMapSpawn

TARGET_WAYPOINTS = (
    FlightWaypointType.TARGET_GROUP_LOC,
    FlightWaypointType.TARGET_POINT,
    FlightWaypointType.TARGET_SHIP,
)

# Waypoints whose generated .miz name is matched as a structural identifier downstream --
# CTLD air-assault split (landingzone.py: name == "DROPOFFZONE"), EW jamming placement and
# formation join/split (aircraftgenerator.py / missiongenerator.py: name in {"JOIN", "SPLIT",
# "RACETRACK START", "RACETRACK END"}). A player rename must NOT reach the .miz for these or
# that logic silently breaks, so they keep their canonical name regardless of custom_name.
STRUCTURAL_WAYPOINT_NAMES = frozenset(
    {"JOIN", "SPLIT", "RACETRACK START", "RACETRACK END", "DROPOFFZONE"}
)


class PydcsWaypointBuilder:
    def __init__(
        self,
        waypoint: FlightWaypoint,
        group: FlyingGroup[Any],
        flight: Flight,
        mission: Mission,
        now: datetime,
        mission_data: MissionData,
    ) -> None:
        self.waypoint = waypoint
        self.group = group
        self.package = flight.package
        self.flight = flight
        self.mission = mission
        self.now = now
        self.mission_data = mission_data

    def dcs_name_for_waypoint(self) -> str:
        # Structural waypoints are matched by name downstream; never let a rename reach the
        # .miz for them (see STRUCTURAL_WAYPOINT_NAMES). The UI still allows the edit, but it
        # is a harmless no-op in the cockpit for these.
        if self.waypoint.name in STRUCTURAL_WAYPOINT_NAMES:
            return self.waypoint.name
        # Prefer the player's rename; otherwise the terse auto .miz name. NB the CDU
        # fallback is `name`, not `pretty_name` (the list/kneeboard fallback) — by design.
        #
        # Flight-agnostic by design: AI flights are unaffected by a player's rename
        # because a rename is written only to the player's own flight-plan waypoints
        # (FlightWaypoint.apply_name_edit), and the player-only waypoint types a rename
        # usually targets (target/divert/bullseye) are filtered out for AI flights
        # upstream in WaypointGenerator.create_waypoints (only_for_player, client_count).
        # See test_divert_and_bullseye_waypoints_are_player_only.
        return self.waypoint.custom_name or self.waypoint.name

    def build(self) -> MovingPoint:
        waypoint = self.group.add_waypoint(
            self.waypoint.position,
            self.waypoint.alt.meters,
            # The speed we pass will be overridden for most waypoints because we'll set
            # a TOT and leave the speed up to the AI, but for the few types of waypoints
            # that don't have TOTs (e.g. nav points), we set a reasonable cruise speed
            # to pydcs doesn't assign the default of 600kph ground speed (which is very
            # slow at most altitudes).
            #
            # Calling GroundSpeed.for_flight isn't really a correct fix here. We ought
            # to be using FlightPlan.speed_between_waypoints, but the way the waypoint
            # builder is called makes it difficult to track the previous waypoint. This
            # is probably good enough for a stop gap, and most of the flight planning
            # code is hopefully being rewritten soon anyway.
            #
            # https://github.com/dcs-liberation/dcs_liberation/issues/3113
            speed=GroundSpeed.for_flight(self.flight, self.waypoint.alt).kph,
            name=self.dcs_name_for_waypoint(),
        )

        waypoint.alt_type = self.waypoint.alt_type
        if self.flight.is_helo and self.flight.coalition.game.settings.switch_baro_fix:
            self.switch_to_baro_if_in_sea(waypoint)
        if self.waypoint.flyover:
            waypoint.action = PointAction.FlyOverPoint
            # It seems we need to leave waypoint.type exactly as it is even
            # though it's set to "Turning Point". If I set this to "Fly Over
            # Point" and then save the mission in the ME DCS resets it.
            if self.flight.client_count > 0:
                # Set Altitute to 0 AGL for player flights so that they can slave target pods or weapons to the waypoint
                waypoint.alt = 0
                waypoint.alt_type = "RADIO"

        tot = self.flight.flight_plan.tot_for_waypoint(self.waypoint)
        if tot is not None:
            self.set_waypoint_tot(waypoint, tot)
        self.add_tasks(waypoint)
        self.redirect_to_decoy(waypoint)
        return waypoint

    def redirect_to_decoy(self, waypoint: MovingPoint) -> bool:
        """An AI package that took the decoy for its target (the decoy call,
        game.warfare.deception, made before the mission) attacks the decoy:
        its own attack tasks on the real site are pointed at the decoy group
        (game.missiongenerator.decoygenerator), with the same weapons and
        release settings. A point Bombing task on the decoy instead had the
        Hornets' JSOWs released 100 km out, 45 km short of anything (PG,
        turn 3). Returns True when the tasks were changed."""
        from dcs.task import (
            AttackGroup,
            AttackMapObject,
            AttackUnit,
            Bombing,
            CarpetBombing,
        )
        from game.missiongenerator.decoygenerator import decoy_group_name
        from game.warfare.deception import _attack_types

        call = getattr(self.package, "decoy_call", None)
        if call is None or call.spotted or self.flight.client_count > 0:
            return False
        if self.flight.flight_type not in _attack_types():
            return False
        target = self.package.target
        decoy = self.mission.find_group(decoy_group_name(target.name, call.decoy_index))
        if decoy is None:
            logging.warning(
                f"{self.flight}: took the decoy for {target.name}, but the decoy "
                "isn't in the mission; it attacks the real site"
            )
            return False
        real_groups: set[int] = set()
        real_units: set[int] = set()
        for group in getattr(target, "groups", []):
            miz_group = self.mission.find_group(group.group_name)
            if miz_group is not None:
                real_groups.add(miz_group.id)
                real_units.update(u.id for u in miz_group.units)
        dx = call.x - target.position.x
        dy = call.y - target.position.y
        changed = False
        seen: set[str] = set()
        tasks = []
        for task in waypoint.tasks:
            params = task.params
            if isinstance(task, AttackGroup) and params.get("groupId") in real_groups:
                params["groupId"] = decoy.id
                changed = True
            elif isinstance(task, AttackUnit) and params.get("unitId") in real_units:
                # The same weapons at the decoy group.
                retarget = AttackGroup(decoy.id)
                for key in (
                    "weaponType",
                    "expend",
                    "attackQty",
                    "attackQtyLimit",
                    "directionEnabled",
                    "direction",
                    "altitudeEnabled",
                    "altitude",
                ):
                    if key in params:
                        retarget.params[key] = params[key]
                task = retarget
                changed = True
            elif isinstance(task, (Bombing, CarpetBombing, AttackMapObject)):
                if "x" in params and "y" in params:
                    params["x"] += dx
                    params["y"] += dy
                    changed = True
            if isinstance(task, AttackGroup) and task.params.get("groupId") == decoy.id:
                # A site of several groups (SAM and point defence) gives the
                # same attack once per group; the decoy needs it once.
                key = repr(sorted(task.params.items()))
                if key in seen:
                    continue
                seen.add(key)
            tasks.append(task)
        if not changed:
            return False
        waypoint.tasks = tasks
        logging.info(
            f"{self.flight}: took the decoy for {target.name}; attacking the decoy "
            f"group {decoy.name}"
        )
        return True

    def switch_to_baro_if_in_sea(self, waypoint: MovingPoint) -> None:
        if waypoint.alt_type == "RADIO" and (
            self.flight.coalition.game.theater.is_in_sea(waypoint.position)
            or not self.flight.coalition.game.theater.is_on_land(
                waypoint.position, ignore_exclusion=True
            )
        ):
            waypoint.alt_type = "BARO"

    def ai_despawn(
        self, waypoint: MovingPoint, ignore_landing_wpt: bool = False
    ) -> bool:
        if self.flight.roster.members[0].is_player:
            return False
        arrival = self.flight.arrival
        offmap = isinstance(arrival, OffMapSpawn)
        ai_despawn = self.flight.coalition.game.settings.perf_ai_despawn_airstarted
        ai_despawn &= self.flight.start_type in {
            StartType.IN_FLIGHT,
            StartType.ON_STATION,
        }
        is_landing_wpt = arrival.position == waypoint.position
        return (offmap or ai_despawn) and (is_landing_wpt or ignore_landing_wpt)

    def add_tasks(self, waypoint: MovingPoint) -> None:
        if self.ai_despawn(waypoint):
            waypoint.tasks.append(
                RunScript(
                    f"local g = Group.getByName('{self.group.name}')\n"
                    f"Group.destroy(g)"
                )
            )

    def set_waypoint_tot(self, waypoint: MovingPoint, tot: datetime) -> None:
        self.waypoint.tot = tot
        if not self._viggen_client_tot():
            waypoint.ETA = max(0, int((tot - self.now).total_seconds()))
            waypoint.ETA_locked = True
            waypoint.speed_locked = waypoint.ETA == 0

    def _viggen_client_tot(self) -> bool:
        """Viggen player aircraft consider any waypoint with a TOT set to be a target ("M") waypoint.
        If the flight is a player controlled Viggen flight, no TOT should be set on any waypoint except actual target waypoints.
        """
        if (
            self.flight.client_count > 0
            and self.flight.unit_type.dcs_unit_type == AJS37
            and self.waypoint.waypoint_type not in TARGET_WAYPOINTS
        ):
            return True
        else:
            return False

    def register_special_strike_points(
        self,
        targets: Iterable[Union[MissionTarget, TheaterUnit]],
        start: int = 1,
    ) -> None:
        """Create special strike  waypoints for various aircraft"""
        for i, t in enumerate(targets):
            if self.group.units[0].unit_type == JF_17 and i < 4:
                self.group.add_nav_target_point(t.position, "PP" + str(i + 1))
            if self.group.units[0].unit_type in [F_14B, F_14A_135_GR] and i == 0:
                self.group.add_nav_target_point(t.position, "ST")
            # Add F-15E mission target points as mission 1 (for JDAM for instance)
            if self.group.units[0].unit_type == F_15ESE:
                self.group.add_nav_target_point(
                    t.position, f"M{(i//8)+start}.{i%8+1}\nH-1\nA0\nV0"
                )

    def register_special_ingress_points(self) -> None:
        # Register Tomcat Initial Point
        if self.flight.client_count and (
            self.group.units[0].unit_type in (F_14A_135_GR, F_14B)
        ):
            self.group.add_nav_target_point(self.waypoint.position, "IP")

    def defensive_jamming(self, waypoint: MovingPoint, action: str) -> None:
        # Explodes incoming missiles within the jamming bubble through the EW-Jamming script
        settings = self.flight.coalition.game.settings
        ecm_required = settings.plugin_option("ewrj.ecm_required")
        for unit, member in zip(self.group.units, self.flight.iter_members()):
            has_jammer = member.loadout.has_weapon_of_type(
                WeaponType.JAMMER
            ) or member.loadout.has_weapon_of_type(WeaponType.OFFENSIVE_JAMMER)
            built_in_jammer = (
                self.flight.squadron.aircraft.has_built_in_ecm
                or self.flight.squadron.aircraft.has_built_in_jamming
            )
            if ecm_required and not (has_jammer or built_in_jammer):
                continue
            if not member.is_player:
                script_content = f'{action}IAdefjamming("{unit.name}")'
                jamming_script = RunScript(script_content)
                waypoint.tasks.append(jamming_script)

    def offensive_jamming(self, waypoint: MovingPoint, action: str) -> None:
        # Silences enemy radars through the EW-Jamming script
        settings = self.flight.coalition.game.settings
        ecm_required = settings.plugin_option("ewrj.ecm_required")
        for unit, member in zip(self.group.units, self.flight.iter_members()):
            has_jammer = member.loadout.has_weapon_of_type(WeaponType.OFFENSIVE_JAMMER)
            built_in_jammer = self.flight.squadron.aircraft.has_built_in_jamming
            if ecm_required and not (has_jammer or built_in_jammer):
                continue
            if not member.is_player:
                script_content = f'{action}EWjamm("{unit.name}")'
                stop_jamming_script = RunScript(script_content)
                waypoint.tasks.append(stop_jamming_script)
