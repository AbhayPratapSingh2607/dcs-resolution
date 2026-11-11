import logging

from dcs.point import MovingPoint
from dcs.task import EngageTargets, EngageTargetsInZone, Targets

from game.ato.flightplans.cas import CasFlightPlan
from game.utils import nautical_miles
from .pydcswaypointbuilder import PydcsWaypointBuilder


class CasIngressBuilder(PydcsWaypointBuilder):
    def add_tasks(self, waypoint: MovingPoint) -> None:
        self.register_special_ingress_points()
        from game.commander.jfacc.faca import fac_capable, is_fac

        if is_fac(self.flight) and fac_capable(self.flight):
            self._add_fac(waypoint)
            return
        if isinstance(self.flight.flight_plan, CasFlightPlan):
            patrol_center = (
                self.flight.flight_plan.layout.patrol_start.position
                + self.flight.flight_plan.layout.patrol_end.position
            ) / 2
            waypoint.add_task(
                EngageTargetsInZone(
                    position=patrol_center,
                    radius=int(self.flight.flight_plan.engagement_distance.meters),
                    targets=[
                        Targets.All.GroundUnits.GroundVehicles,
                        Targets.All.GroundUnits.AirDefence.AAA,
                        Targets.All.GroundUnits.Infantry,
                    ],
                )
            )
        else:
            logging.error("No CAS waypoint found. Falling back to search and engage")
            waypoint.add_task(
                EngageTargets(
                    max_distance=int(
                        nautical_miles(
                            self.flight.coalition.game.settings.cas_engagement_range_distance
                        ).meters
                    ),
                    targets=[
                        Targets.All.GroundUnits.GroundVehicles,
                        Targets.All.GroundUnits.AirDefence.AAA,
                        Targets.All.GroundUnits.Infantry,
                    ],
                )
            )

    def _add_fac(self, waypoint: MovingPoint) -> None:
        """FAC(A) (V3): the FAC enroute task on the flight's own frequency,
        which the CAS checks in on; listed on the kneeboard with the JTACs."""
        from dcs.task import FAC

        from game.missiongenerator.missiondata import JtacInfo

        from game.radio.radios import MHz

        # setup_radios gives every flight its own or its package's frequency.
        freq = self.flight.frequency or self.flight.package.frequency or MHz(251)
        cs = self.group.units[0].callsign_dict
        callsign_id = cs.get(1) if isinstance(cs, dict) else None
        number = cs.get(2) if isinstance(cs, dict) else None
        waypoint.add_task(
            FAC(
                callsign=callsign_id if isinstance(callsign_id, int) else 1,
                number=number if isinstance(number, int) else 1,
                frequency=int(freq.mhz),
                modulation=freq.modulation,
            )
        )
        target = self.flight.package.target
        code = getattr(target, "laser_code", None)
        if self.flight.squadron.player.is_blue:
            self.mission_data.jtacs.append(
                JtacInfo(
                    group_name=self.group.name,
                    unit_name=self.group.units[0].name,
                    callsign=f"{self.group.units[0].callsign} FAC(A)",
                    region=target.name,
                    code=str(code) if code is not None else "-",
                    blue=self.flight.squadron.player,
                    freq=freq,
                )
            )
