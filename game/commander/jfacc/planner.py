"""The JFACC planner: plans one ATO period for one side.

Order of work, as a JAOC strategy and plans cell would do it:

1. Assess the campaign and decide the phase.
2. Set front-line stances (the land component's scheme of manoeuvre).
3. Build the JIPTL from what intelligence knows.
4. Work out how many sorties the air wing can generate this period and
   apportion them across mission categories for the phase.
5. Plan, in order: personnel recovery, enablers (AEW&C, tankers), defensive
   counter-air, ground support (kill boxes, then CAS), then offensive packages
   from the JIPTL in rank order, each within its category's apportionment.
6. Hand unused sorties to other categories (overflow) and plan again.
7. Record the phase, intent, JIPTL and apportionment for the UI.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timedelta
from typing import Any, Optional, TYPE_CHECKING

from game.ato.flighttype import FlightType
from .apportionment import Apportionment
from .assessment import CampaignAssessment, assess
from .campaignstate import SideCampaign
from .composer import ComposedPackage, FlightRequest, PackageComposer, PackageRequest
from .dca import hvaa_station, station_for, threat_axes, threatened_bases
from .observations import ObservationLog
from .casestimate import flight_kills_or_fallback, front_armor_share
from .groundsupport import cas_lines, kill_boxes
from .phases import PhaseManager
from .profile import (
    Category,
    Modifier,
    Phase,
    PhaseSpec,
    PlanningProfile,
    category_for_task,
    load_profile,
)
from .scheduler import Timeline, patrol_end
from .sorties import SortieLedger, role_for
from .targets import TargetNomination, TargetNominator, snapshot
from . import weaponeering

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.profiling import MultiEventTracer
    from game.theater import ControlPoint, MissionTarget
    from game.theater.player import Player
    from game.squadrons import Squadron
    from game.theater.frontline import FrontLine


def request_replacements(
    coalition: Coalition, spec: PhaseSpec, per_squadron: Optional[int]
) -> None:
    """Ask for aircraft for squadrons below strength, those flying the
    mission types the phase apportions most first. Purchases happen after
    planning, within the side's budget (game.procurement.ProcurementAi).
    per_squadron=None fills squadrons completely."""
    from game.procurement import AircraftProcurementRequest

    shares = {category: share.share for category, share in spec.apportionment.items()}
    wanted = []
    for squadron in coalition.air_wing.iter_squadrons():
        missing = squadron.max_size - squadron.owned_aircraft - squadron.pending_deliveries
        if missing <= 0:
            continue
        if per_squadron is not None:
            missing = min(missing, per_squadron)
        category = category_for_task(squadron.primary_task)
        weight = shares.get(category, 0.05) if category is not None else 0.05
        wanted.append((weight, squadron, missing))
    for _, squadron, count in sorted(wanted, key=lambda w: -w[0]):
        # The full order, then a pair as a fallback when the budget can't
        # cover it (equal requests merge, so the pair is only added when it
        # differs; the squadron's capacity check prevents over-buying).
        for number in (count, 2) if count > 2 else (count,):
            coalition.add_procurement_request(
                AircraftProcurementRequest(
                    near=squadron.location,
                    task_capability=squadron.primary_task,
                    number=number,
                    heli=squadron.aircraft.helicopter,
                )
            )


def request_csar_readiness(coalition: Coalition, ready: int) -> int:
    """Keep a standing personnel recovery force. Pilots go down during the
    period and are only rescued if helicopters are already on hand, so buying
    after a shoot-down is too late. Requests enough CSAR-capable aircraft to
    bring the side up to `ready`, ahead of ordinary replacements. Returns the
    number requested."""
    from game.procurement import AircraftProcurementRequest

    game = coalition.game
    settings = game.settings
    enabled = (
        settings.csar_enabled if coalition.player.is_blue else settings.csar_enabled_red
    )
    if not enabled or ready <= 0:
        return 0
    squadrons = [
        s
        for s in coalition.air_wing.iter_squadrons()
        if FlightType.CSAR in s.auto_assignable_mission_types
    ]
    have = sum(s.owned_aircraft + s.pending_deliveries for s in squadrons)
    missing = ready - have
    if missing <= 0:
        return 0
    # Fill the emptiest squadrons first, closest to the fight being where
    # the CSAR squadrons are based anyway.
    requested = 0
    for squadron in sorted(squadrons, key=lambda s: s.owned_aircraft + s.pending_deliveries):
        room = squadron.max_size - squadron.owned_aircraft - squadron.pending_deliveries
        number = min(room, missing - requested)
        if number <= 0:
            continue
        # The full order, then a pair when the budget can't cover it (as in
        # request_replacements; at most one pair over `ready`).
        for size in (number, 2) if number > 2 else (number,):
            coalition.add_procurement_request(
                AircraftProcurementRequest(
                    near=squadron.location,
                    task_capability=FlightType.CSAR,
                    number=size,
                    heli=squadron.aircraft.helicopter,
                )
            )
        requested += number
        if requested >= missing:
            break
    return requested


def profile_for(game: Game, player: Player) -> Optional[PlanningProfile]:
    """The planning profile a side uses, or None for the legacy planner."""
    from game.settings.settings import PlannerEngine
    from game.warfare.doctrine import for_faction_obj

    setting = (
        game.settings.planner_engine_blue
        if player.is_blue
        else game.settings.planner_engine_red
    )
    if setting is PlannerEngine.LEGACY:
        return None
    coalition = game.coalition_for(player)
    try:
        name = for_faction_obj(coalition.faction).planning_profile
    except Exception:
        name = ""
    if setting is PlannerEngine.DOCTRINE and not name:
        # Forced on for a doctrine without its own profile: plan the Western way.
        name = "western"
    return load_profile(name) if name else None


def period_hours(game: Game, profile: PlanningProfile) -> float:
    return float(min(profile.period_hours, getattr(game.settings, "ato_period_hours", 6)))


class JfaccPlanner:
    # Set while planning a period (plan_missions).
    now: datetime
    assessment: CampaignAssessment
    phase: Phase
    spec: PhaseSpec
    modifiers: tuple[Modifier, ...]
    ledger: SortieLedger
    timeline: Timeline
    apportionment: Apportionment
    composer: PackageComposer
    nominations: list[TargetNomination]
    planned_keys: set[str]
    suppressed: dict[object, datetime]

    def __init__(self, game: Game, player: Player, profile: PlanningProfile) -> None:
        self.game = game
        self.player = player
        self.profile = profile
        self.coalition: Coalition = game.coalition_for(player)
        self.side: SideCampaign = game.air_campaign.side(player.is_blue)

    # ================================================================ entry

    def plan_missions(self, now: datetime, tracer: MultiEventTracer) -> None:
        from game.settings.settings import AutoAtoBehavior

        game = self.game
        settings = game.settings
        blue = self.player.is_blue
        self.now = now
        self.side.scrubbed = []
        self.side.raids = []

        with tracer.trace("JFACC assessment"):
            self.assessment = assess(game, self.player)
        decision = PhaseManager(self.profile).decide(
            self.side, self.assessment, game.turn
        )
        self.phase = decision.phase
        self.spec = self.profile.phases[self.phase]
        self.modifiers = decision.modifiers
        self.side.moes = self.assessment.as_dict()

        end = now + timedelta(hours=period_hours(game, self.profile))
        seed = getattr(game.war_state, "seed", 0) * 31 + game.turn * 2 + int(blue)
        game.air_campaign.note_period(game.turn, now, end)
        self.ledger = SortieLedger(self.profile, now, end, seed)
        self.timeline = Timeline(self.profile, now, end)
        self.conditions = weaponeering.conditions_for(game, self.profile)

        from game.commander.theaterstate import TheaterState

        with tracer.trace("JFACC theater state"):
            self.state = TheaterState.from_game(game, self.player, now, tracer)
        self._set_stances()

        planning_allowed = not (blue and settings.auto_ato_behavior is AutoAtoBehavior.Disabled)

        with tracer.trace("JFACC target nomination"):
            self.nominations = TargetNominator(
                game, self.player, self.profile, self.side, self.assessment, self.phase
            ).nominate()

        self.composer = PackageComposer(
            game,
            self.coalition,
            self.profile,
            self.ledger,
            self.conditions,
            aewc_available=self.coalition.air_wing.can_auto_plan(FlightType.AEWC),
        )
        self.side.qra = self._plan_alerts() if planning_allowed else []
        with tracer.trace("JFACC IADS management"):
            from .iads import plan_emcon

            plan_emcon(
                game,
                self.player,
                self.side,
                self.profile,
                preserving=bool(self.effect("iads_preserve", False)),
            )
        total = self._sortie_capacity()
        self.apportionment = Apportionment.for_phase(self.profile, self.spec, total)
        self._apply_category_scaling()
        self.planned_keys: set[str] = set()
        #: SAM site id -> TOT of the DEAD package tasked against it.
        self.suppressed: dict[object, datetime] = {}
        self.aewc_planned = False
        self.composer.risk_multiplier = float(
            self.spec.flag("risk_multiplier", 1.0)
        ) * float(self.effect("risk_scale", 1.0))  # type: ignore[arg-type]
        self.composer.rollback_allowed = bool(self.spec.flag("rollback_allowance", False))
        self.composer.phase_name = self.phase.value

        if planning_allowed:
            with tracer.trace("JFACC personnel recovery"):
                self._plan_csar()
            with tracer.trace("JFACC enablers"):
                self._plan_enablers()
            with tracer.trace("JFACC counter-air"):
                self._plan_dca()
            with tracer.trace("JFACC ground support"):
                self._plan_kill_boxes()
                self._plan_cas()
            with tracer.trace("JFACC air assault"):
                self._plan_air_assault()
            with tracer.trace("JFACC raids"):
                self._plan_raids()
            with tracer.trace("JFACC offensive packages"):
                self._plan_jiptl()
            self.apportionment.begin_overflow()
            with tracer.trace("JFACC overflow"):
                self._plan_cas()
                self._plan_jiptl()
            with tracer.trace("JFACC recovery tankers"):
                self._plan_recovery()
        # Aircraft purchases follow the "automate aircraft reinforcements"
        # setting, not ATO automation.
        with tracer.trace("JFACC request for forces"):
            self._request_forces()

        self._record()

    # ========================================================== modifiers

    def effect(self, name: str, default: object = None) -> object:
        """A modifier effect, combined over the active modifiers: scales
        multiply, flags are true if any modifier sets them, anything else
        comes from the last modifier that sets it."""
        value = default
        found = False
        for modifier in self.modifiers:
            if name not in modifier.effects:
                continue
            new = modifier.effects[name]
            if found and isinstance(new, (int, float)) and not isinstance(new, bool) and name.endswith("_scale"):
                value = float(value) * float(new)  # type: ignore[arg-type]
            elif found and isinstance(new, bool):
                value = bool(value) or new
            else:
                value = new
            found = True
        return value

    @property
    def raid_style(self) -> str:
        """massed | opportunistic | none, from the phase unless a modifier
        overrides it."""
        return str(self.effect("raid_style", self.spec.flag("raid_style", "none")))

    def _apply_category_scaling(self) -> None:
        """Modifiers that cut categories (force preservation) lower both the
        quota and the ceiling, so overflow doesn't hand the sorties back."""
        scales: dict[str, float] = {}
        for modifier in self.modifiers:
            for key, value in (modifier.effects.get("scale_categories") or {}).items():
                scales[key] = scales.get(key, 1.0) * float(value)
        for category in Category:
            scale = scales.get(category.value)
            if scale is None:
                continue
            self.apportionment.quota[category] = round(
                self.apportionment.quota[category] * scale
            )
            self.apportionment.ceiling[category] = round(
                self.apportionment.ceiling[category] * scale
            )

    # ============================================================ stances

    def _set_stances(self) -> None:
        from game.commander.tasks.primitive.aggressiveattack import AggressiveAttack
        from game.commander.tasks.primitive.breakthroughattack import (
            BreakthroughAttack,
        )
        from game.commander.tasks.primitive.defensivestance import DefensiveStance
        from game.commander.tasks.primitive.eliminationattack import (
            EliminationAttack,
        )
        from game.commander.tasks.primitive.retreatstance import RetreatStance

        stance = str(self.spec.flag("ground_stance", "hold"))
        for front in list(self.state.active_front_lines):
            options: list[type] = []
            if stance == "attack":
                options += [BreakthroughAttack, EliminationAttack, AggressiveAttack]
            elif stance == "hold":
                # Before the ground offensive the land component holds, and
                # only exploits overwhelming local superiority.
                options += [EliminationAttack]
            # "defend": no attacks at all.
            options += [DefensiveStance, RetreatStance]
            for task_type in options:
                task = task_type(front, self.player)
                try:
                    if task.preconditions_met(self.state):
                        task.apply_effects(self.state)
                        task.execute(self.coalition)
                        break
                except Exception:
                    logging.exception(f"JFACC: stance {task_type.__name__} failed")

    # ===================================================== request for forces

    def _request_forces(self) -> None:
        """Ask for aircraft. Shortfalls that limited this period's plan (a
        flight with no aircraft free, SEAD a package needed) were requested
        while planning; replacements (request_replacements) follow them. The
        standing CSAR force (request_csar_readiness) goes ahead of everything:
        a few helicopters are cheap, and without them downed pilots are lost."""
        procurement = self.profile.section("procurement")
        shortfalls = list(self.coalition.procurement_requests)
        self.coalition.procurement_requests.clear()
        request_csar_readiness(self.coalition, int(procurement.get("csar_ready", 4)))
        for request in shortfalls:
            self.coalition.add_procurement_request(request)
        per_squadron = int(procurement.get("replacements_per_squadron", 4))
        request_replacements(self.coalition, self.spec, per_squadron)

    # ========================================================== capacity

    def _plan_alerts(self) -> list[str]:
        """Ground alert (QRA) at the bases within reach of enemy fighters.

        Each alert is a package of one fighter pair holding at the runway
        end, with a station on the base's main threat axis. The side's GCI
        (game.sim.gci, and the GCI Lua plugin in DCS) scrambles it when its
        own radars see an enemy raid within the sector radius of the
        station. The airframes are held for the whole period, so they are
        never tasked with anything else; alerts that are never scrambled
        don't fly."""
        from .dca import CapStation

        alert = self.profile.section("alert")
        dca = self.profile.section("dca")
        pairs = int(alert.get("pairs_per_base", int(dca.get("qra_per_base", 0)) // 2))
        # Force preservation holds more fighters back for the defense.
        pairs += int(self.effect("alert_pairs_bonus", 0))  # type: ignore[call-overload]
        if pairs <= 0:
            return []
        size = int(alert.get("flight_size", 2))
        radius_m = float(alert.get("sector_radius_nm", 80)) * 1852.0
        near, far = (float(v) for v in alert.get("station_forward_nm", [10, 30]))
        reach = float(dca.get("threat_reach_nm", 200))
        axes = threat_axes(
            self.game,
            self.player,
            reach,
            float(dca.get("axis_merge_deg", 30)),
            int(dca.get("max_axes", 3)) * 3,
            learned=ObservationLog(self.side),
            learned_weight=float(
                self.profile.get("adaptation", "learned_axis_weight", 0.0)
            ),
        )
        strongest: dict[str, Any] = {}
        for candidate in axes:
            strongest.setdefault(candidate.defended.name, candidate)
        bases = [
            b for b in threatened_bases(self.game, self.player, reach) if not b.is_fleet
        ][: int(alert.get("bases_max", 4))]
        held: list[str] = []
        for base in bases:
            main_axis = strongest.get(base.name)
            if main_axis is not None:
                station = station_for(
                    self.game, self.player, main_axis, (near, far), under_own_sams=True
                )
            else:
                station = CapStation(
                    f"Alert {base.name}", base.position, self.player, base, 0.0
                )
            for _ in range(pairs):
                request = PackageRequest(
                    target=station,
                    flights=[FlightRequest(FlightType.BARCAP, size, home=base, alert=True)],
                    category_name="dca",
                    reason=f"Ground alert at {base.name}",
                )
                composed, why = self.composer.compose(
                    request, self.timeline.earliest, self.now
                )
                if composed is None:
                    break
                package = composed.package
                package.alert_radius_m = radius_m
                package.planning_rationale = (
                    f"{self.phase.title} | Ground alert at {base.name}, scrambled by "
                    f"GCI against raids within {radius_m / 1852:.0f} nm of the station"
                )
                package.planning_info = {
                    "phase": self.phase.title,
                    "reason": f"Ground alert at {base.name}",
                    "threat": "",
                    "risk": "",
                    "notes": ["Launches only when the GCI scrambles it"],
                }
                self.coalition.ato.add_package(package)
                flight = package.flights[0]
                held.append(f"{flight.count}x {flight.unit_type.display_name} at {base.name}")
        return held

    def _combat_squadrons(self) -> list[Squadron]:
        squadrons: list[Squadron] = []
        for squadron in self.coalition.air_wing.iter_squadrons():
            if squadron.untasked_aircraft <= 0:
                continue
            if role_for(squadron) == "support":
                continue
            if not squadron.auto_assignable_mission_types:
                continue
            squadrons.append(squadron)
        return squadrons

    def _sortie_capacity(self) -> int:
        return sum(
            self.ledger.sorties_possible(squadron, 2.0)
            for squadron in self._combat_squadrons()
        )

    # ========================================================== helpers

    def _commit(
        self,
        request: PackageRequest,
        tot: datetime,
        category: Optional[Category],
        quiet: bool = False,
    ) -> Optional[ComposedPackage]:
        composed, why = self.composer.compose(request, tot, self.now)
        if composed is None:
            if not quiet:
                self.side.scrubbed.append((request.target.name, why))
            return None
        package = composed.package
        parts = [self.phase.title, request.reason]
        if request.threat is not None:
            parts.append(f"threat {request.threat.level}")
        if composed.risk is not None:
            parts.append(f"est. attrition {composed.risk.describe()}")
        parts.extend(composed.notes)
        package.planning_rationale = " | ".join(p for p in parts if p)
        package.planning_info = {
            "phase": self.phase.title,
            "reason": request.reason,
            "threat": request.threat.level if request.threat is not None else "",
            "risk": composed.risk.describe() if composed.risk is not None else "",
            "notes": list(composed.notes),
        }
        self.coalition.ato.add_package(package)
        if category is not None:
            self.apportionment.spend(category, composed.sorties)
        self.timeline.reserve(package.time_over_target, request.target.position)
        return composed

    def _support_allowed(self, setting: str) -> bool:
        if not self.player.is_blue:
            return True
        return bool(getattr(self.game.settings, setting, True))

    # ====================================================== CSAR (PR)

    def _plan_csar(self) -> None:
        settings = self.game.settings
        limit = int(getattr(settings, "max_csar_flights", 2))
        from game.utils import meters

        radius = meters(getattr(settings, "csar_cluster_radius", 0))
        remaining = list(self.state.csar_targets)
        planned = 0
        for pilot in list(remaining):
            if planned >= limit:
                break
            if pilot not in remaining:
                # Collected by a rescue already planned for a nearby pilot.
                continue
            size = 1 if getattr(settings, "csar_single_flight", False) else 2
            threat = self.composer.threat_for(pilot)
            request = PackageRequest(
                target=pilot,
                flights=[FlightRequest(FlightType.CSAR, size)]
                + self.composer.support_for(threat, size),
                category_name="pr",
                reason="Personnel recovery",
                risk_kind="troops_in_contact",
                threat=threat,
            )
            # Rescue as soon as the package can get there.
            tot = self.timeline.earliest
            if self._commit(request, tot, None) is not None:
                planned += 1
                # One lift collects the whole cluster (the mission generator
                # rebuilds the same cluster at the pickup).
                for other in pilot.cluster(radius):
                    if other in remaining:
                        remaining.remove(other)

    # ======================================================== enablers

    def _plan_line(
        self,
        target: MissionTarget,
        task: FlightType,
        reason: str,
        category: Optional[Category],
        size: int = 1,
        max_packages: int = 12,
        first: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> list[ComposedPackage]:
        """A continuous line: relief arrives as the previous flight leaves."""
        planned: list[ComposedPackage] = []
        tot = first or self.timeline.earliest
        end = until or self.timeline.end
        while tot < end and len(planned) < max_packages:
            if category is not None and not self.apportionment.can_afford(category, size):
                break
            request = PackageRequest(
                target=target,
                flights=[FlightRequest(task, size)],
                category_name=task.value,
                reason=reason,
            )
            composed = self._commit(request, tot, category, quiet=True)
            if composed is None:
                # Try the next relief slot: maybe aircraft are free later.
                tot += timedelta(minutes=30)
                continue
            planned.append(composed)
            next_tot = patrol_end(composed.package)
            if next_tot is None or next_tot <= tot:
                next_tot = tot + timedelta(hours=1)
            tot = next_tot - timedelta(minutes=5)
        return planned

    def _plan_enablers(self) -> None:
        enablers = self.profile.section("enablers")
        if self._support_allowed("auto_ato_behavior_awacs") and enablers.get(
            "aewc_continuous", True
        ):
            for target in self.state.aewc_targets:
                packages = self._plan_line(
                    target,
                    FlightType.AEWC,
                    "Continuous AEW&C coverage",
                    None,
                )
                if packages:
                    self.aewc_planned = True
                    self.composer.aewc_available = True
                    self._plan_hvaa_cap(packages, "AEW&C")
        # Tankers are doctrine, not a player toggle: the "Automatic Theater
        # tanker package planning" setting only gates the legacy planner.
        if enablers.get("tanker_continuous", True):
            for target in self.state.refueling_targets:
                packages = self._plan_line(
                    target,
                    FlightType.REFUELING,
                    "Theater tanker track",
                    None,
                )
                self._plan_hvaa_cap(packages, "tanker")

    def _plan_hvaa_cap(self, packages: list[ComposedPackage], label: str) -> None:
        if not packages or not self.profile.get("dca", "hvaa_cap", True):
            return
        reach = float(self.profile.get("dca", "threat_reach_nm", 200))
        first = packages[0].package
        orbit = first.primary_flight
        if orbit is None:
            return
        try:
            position = orbit.flight_plan.layout.patrol_start.position
        except Exception:
            position = first.target.position
        from .dca import _enemy_fighter_bases

        if not any(
            base.position.distance_to_point(position) <= reach * 1852
            for base, _ in _enemy_fighter_bases(self.game, self.player)
        ):
            return
        defended = orbit.departure
        station = hvaa_station(self.player, defended, position, label)
        start = packages[0].package.time_over_target
        end_time = patrol_end(packages[-1].package) or self.timeline.end
        self._plan_line(
            station,
            FlightType.BARCAP,
            f"HVAA protection ({label} orbit)",
            Category.DCA,
            size=int(self.profile.get("dca", "cap_flight_size", 2)),
            first=start,
            until=end_time,
        )

    # ============================================================== DCA

    def _plan_dca(self) -> None:
        dca = self.profile.section("dca")
        reach = float(dca.get("threat_reach_nm", 200))
        size = int(dca.get("cap_flight_size", 2))
        scale = float(self.effect("dca_forward_scale", 1.0))  # type: ignore[arg-type]
        forward = tuple(float(f) * scale for f in dca.get("station_forward_nm", [25, 60]))
        under_own_sams = bool(self.effect("cap_under_own_sam", False))
        axes = threat_axes(
            self.game,
            self.player,
            reach,
            float(dca.get("axis_merge_deg", 30)),
            int(dca.get("max_axes", 3)),
            learned=ObservationLog(self.side),
            learned_weight=float(
                self.profile.get("adaptation", "learned_axis_weight", 0.0)
            ),
        )
        stations = [
            station_for(
                self.game,
                self.player,
                axis,
                (float(forward[0]), float(forward[1])),
                under_own_sams=under_own_sams,
            )
            for axis in axes
        ]
        if dca.get("point_defense", True):
            for cp in threatened_bases(self.game, self.player, reach):
                if cp.is_fleet:
                    stations.append(cp)  # type: ignore[arg-type]
        if not stations:
            return
        # Round-robin in time so every axis is covered before any line is
        # extended: limited DCA sorties cover all axes for part of the period
        # rather than one axis all day.
        next_tot: dict[int, datetime] = {
            i: self.timeline.earliest - timedelta(minutes=10) for i in range(len(stations))
        }
        open_lines = set(range(len(stations)))
        while open_lines:
            index = min(open_lines, key=lambda i: next_tot[i])
            tot = next_tot[index]
            if tot >= self.timeline.end or not self.apportionment.can_afford(
                Category.DCA, size
            ):
                open_lines.discard(index)
                continue
            station = stations[index]
            reason = (
                f"DCA on threat axis {int(getattr(station, 'axis_heading', 0)):03d}"
                if hasattr(station, "axis_heading")
                else f"Point defense of {station.name}"
            )
            request = PackageRequest(
                target=station,
                flights=[FlightRequest(FlightType.BARCAP, size)],
                category_name="dca",
                reason=reason,
            )
            composed = self._commit(
                request, max(tot, self.now), Category.DCA, quiet=True
            )
            if composed is None:
                next_tot[index] = tot + timedelta(minutes=30)
                continue
            end = patrol_end(composed.package)
            next_tot[index] = (end or tot + timedelta(hours=1)) - timedelta(minutes=5)

    # ===================================================== ground support

    def _suppressed_before(self, tot: datetime) -> set[object]:
        """SAM sites a DEAD package this period hits before ``tot``."""
        margin = timedelta(minutes=10)
        return {tgo_id for tgo_id, when in self.suppressed.items() if when + margin <= tot}

    def _offensive_request(
        self,
        nomination: TargetNomination,
        task: Optional[FlightType] = None,
        tot: Optional[datetime] = None,
    ) -> PackageRequest:
        from game.theater.theatergroundobject import SamGroundObject

        target = nomination.target
        mission = task or nomination.mission
        strikers = weaponeering.aircraft_needed(
            self.profile,
            "runway" if mission is FlightType.OCA_RUNWAY else nomination.target_class,
            weaponeering.live_elements(target),
        )
        flights = [FlightRequest(mission, strikers)]
        if mission is FlightType.OCA_RUNWAY:
            from game.ato.starttype import StartType

            if self.game.settings.default_start_type is StartType.COLD:
                flights.append(FlightRequest(FlightType.OCA_AIRCRAFT, 2, required=False))
        exclude = target if isinstance(target, SamGroundObject) else None
        suppressed = self._suppressed_before(tot) if tot is not None else None
        threat = self.composer.threat_for(target, exclude=exclude, suppressed=suppressed)
        flights += self.composer.support_for(threat, strikers)
        best = self.coalition.air_wing.best_squadron_for(
            target, mission, strikers, False, this_turn=False
        )
        if best is not None and self.composer.needs_tanker(target, best.aircraft):
            flights.append(
                FlightRequest(FlightType.REFUELING, 1, required=False, note="package tanker")
            )
        reason = (
            f"JIPTL #{nomination.rank} {nomination.target_class.replace('_', ' ')} "
            f"({nomination.status}, desired effect {nomination.desired_effect:.0%}, "
            f"assessed {nomination.assessed_effect:.0%})"
        )
        return PackageRequest(
            target=target,
            flights=flights,
            category_name=nomination.category.value,
            reason=reason,
            risk_kind=nomination.risk_kind,
            threat=threat,
            suppressed=suppressed,
        )

    def _plan_kill_boxes(self) -> None:
        gs = self.profile.section("ground_support")
        fronts = [f.front for f in self.assessment.fronts]
        boxes = kill_boxes(
            self.nominations,
            fronts,
            float(gs.get("kill_box_size_nm", 15)),
            float(gs.get("kill_box_max_depth_nm", 80)),
            int(gs.get("max_kill_boxes", 4)),
        )
        ki_task = (
            FlightType.ARMED_RECON
            if self.coalition.air_wing.can_auto_plan(FlightType.ARMED_RECON)
            else FlightType.BAI
        )
        for box in boxes:
            if not self.apportionment.can_afford(Category.INTERDICTION, 4):
                break
            lead = box.lead
            request = self._offensive_request(lead, ki_task)
            request.reason = (
                f"{box.name} interdiction: {len(box.nominations)} known target(s), "
                f"lead {lead.name}"
            )
            tot = self.timeline.strike_tot(lead.target.position)
            if tot is None:
                continue
            if self._commit(request, tot, Category.INTERDICTION) is not None:
                for nomination in box.nominations:
                    self._mark_planned(nomination)

    def _plan_cas(self) -> None:
        gs = self.profile.section("ground_support")
        if not gs.get("cas_stack", True):
            return
        size = int(gs.get("cas_flight_size", 2))
        contact = [f.front for f in self.assessment.fronts if f.troops_in_contact]
        if not contact:
            return
        effort = self.assessment.main_effort
        lines = cas_lines(
            contact,
            effort.front if effort is not None else None,
            int(gs.get("main_effort_cas_lines", 2)),
            int(gs.get("supporting_cas_lines", 1)),
        )
        if not lines:
            return
        threats = {id(f): self.composer.threat_for(f) for f in contact}
        # Cost of one CAS package including its support.
        sample = threats[id(lines[0])]
        cost = size + sum(r.count for r in self.composer.support_for(sample, size))
        affordable = self.apportionment.remaining(Category.CAS) // max(cost, 1)
        if affordable <= 0:
            return
        on_station = timedelta(minutes=float(gs.get("cas_on_station_min", 40)))
        windows: list[tuple[datetime, FrontLine]] = []
        for i, front in enumerate(lines):
            for tot in self.timeline.relief_tots(
                on_station, self.timeline.earliest + timedelta(minutes=7 * i)
            ):
                windows.append((tot, front))
        windows.sort(key=lambda w: w[0])
        # Desired effect against the fielded forces in contact: enough CAS to
        # attrit them by the doctrine share this period, and no more.
        share = float(self.spec.flag("cas_attrition", 0.35))
        # Desired kills per front, against the expected kills of the CAS
        # flights already tasked (from their actual loadouts).
        wanted = {
            id(f.front): f.enemy_units * share
            for f in self.assessment.fronts
            if f.troops_in_contact
        }
        armor = {id(f): front_armor_share(self.game, f, self.player) for f in contact}
        tasked: dict[int, float] = getattr(self, "_cas_kills", {})
        windows = [
            w for w in windows if tasked.get(id(w[1]), 0.0) < wanted.get(id(w[1]), 0.0)
        ]
        planned_tots: set[tuple[datetime, int]] = getattr(self, "_cas_tots", set())
        windows = [w for w in windows if (w[0], id(w[1])) not in planned_tots]
        if not windows:
            return
        # Spread the affordable vul windows evenly over the period.
        step = max(1, math.ceil(len(windows) / affordable))
        for tot, front in windows[::step]:
            if not self.apportionment.can_afford(Category.CAS, cost):
                break
            if tasked.get(id(front), 0.0) >= wanted.get(id(front), 0.0):
                continue
            threat = threats[id(front)]
            request = PackageRequest(
                target=front,
                flights=[FlightRequest(FlightType.CAS, size)]
                + self.composer.support_for(threat, size),
                category_name="cas",
                reason=(
                    "CAS for troops in contact"
                    + (" (main effort)" if effort is not None and front is effort.front else "")
                ),
                risk_kind="troops_in_contact",
                threat=threat,
            )
            composed = self._commit(request, tot, Category.CAS)
            if composed is not None:
                planned_tots.add((tot, id(front)))
                kills = sum(
                    flight_kills_or_fallback(f, armor[id(front)])
                    for f in composed.package.flights
                    if f.flight_type is FlightType.CAS
                )
                tasked[id(front)] = tasked.get(id(front), 0.0) + kills
                composed.package.planning_rationale += (
                    f" | expected {kills:.0f} vehicles destroyed"
                )
        self._cas_tots = planned_tots
        self._cas_kills = tasked

    # ======================================================= air assault

    def _plan_air_assault(self) -> None:
        """Phase IV vertical envelopment: seize enemy bases the ground
        offensive can exploit, with helicopter-borne troops."""
        from .threat import LEVELS

        cfg = self.profile.section("ground_support").get("air_assault") or {}
        if not self.spec.flag("air_assault", False):
            return
        if not self.coalition.air_wing.can_auto_plan(FlightType.AIR_ASSAULT):
            return
        if self.assessment.air_superiority < float(cfg.get("min_air_superiority", 1.5)):
            self.side.scrubbed.append(
                ("Air assault", "no air superiority for helicopter operations")
            )
            return
        max_level = LEVELS.index(str(cfg.get("max_lz_threat", "medium")))
        limit = int(cfg.get("max_per_period", 2))
        size = int(cfg.get("lift_size", 2))
        radius = float(cfg.get("main_effort_radius_nm", 60)) * 1852
        effort = self.assessment.main_effort

        def distance_to_effort(cp: ControlPoint) -> float:
            if effort is None:
                return 0.0
            return cp.position.distance_to_point(effort.front.position)

        objectives = sorted(
            (cp for cp in self.state.vulnerable_control_points if not cp.is_fleet),
            key=distance_to_effort,
        )
        if not objectives:
            self.side.scrubbed.append(
                ("Air assault", "no objective clear of enemy battle positions")
            )
            return
        planned = 0
        for cp in objectives:
            if planned >= limit:
                break
            if effort is not None and distance_to_effort(cp) > radius:
                continue
            threat = self.composer.threat_for(cp)
            if threat.target_defended or LEVELS.index(threat.level) > max_level:
                self.side.scrubbed.append(
                    (cp.name, f"air assault: landing zone threat {threat.level}")
                )
                continue
            tot = self.timeline.strike_tot(cp.position, preferred_wave=1)
            if tot is None:
                continue
            request = PackageRequest(
                target=cp,
                flights=[FlightRequest(FlightType.AIR_ASSAULT, size)]
                + self.composer.support_for(threat, size),
                category_name="air_assault",
                reason=f"Air assault to seize {cp.name} ahead of the main effort",
                threat=threat,
            )
            if self._commit(request, tot, None) is not None:
                planned += 1

    # ============================================================ raids

    def _plan_raids(self) -> None:
        from .raids import RaidPlanner

        raids = RaidPlanner(self).plan()
        self.side.raids = [
            f"{raid.raid_id}: {raid.nomination.name} "
            f"({', '.join(role for _, _, role in raid.committed)}; {raid.sorties} sorties)"
            for raid in raids
        ]

    # ============================================================ JIPTL

    def _mark_planned(self, nomination: TargetNomination) -> None:
        self.planned_keys.add(nomination.key)
        record = self.side.record(nomination.key, nomination.name, self.game.turn)
        if record.last_struck_turn != self.game.turn:
            record.strikes += 1
            record.last_struck_turn = self.game.turn

    #: Preferred strike wave per category: SEAD/DEAD opens the period so
    #: later waves fly through a rolled-back IADS.
    WAVE_PREFERENCE = {
        Category.SEAD: 0,
        Category.OCA: 1,
        Category.STRIKE: 1,
        Category.INTERDICTION: 2,
    }

    def _wave_preference(self, category: Category) -> Optional[int]:
        table = self.spec.flag("wave_preference")
        if isinstance(table, dict):
            value = table.get(category.value)
            return None if value is None else int(value)
        return self.WAVE_PREFERENCE.get(category)

    def _plan_jiptl(self) -> None:
        from game.theater.theatergroundobject import SamGroundObject

        for nomination in self.nominations:
            if nomination.priority <= 0 or nomination.key in self.planned_keys:
                continue
            category = nomination.category
            if self.apportionment.remaining(category) <= 0:
                continue
            if not self.coalition.air_wing.can_auto_plan(nomination.mission):
                continue
            tot = self.timeline.strike_tot(
                nomination.target.position, self._wave_preference(category)
            )
            if tot is None:
                continue
            request = self._offensive_request(nomination, tot=tot)
            cost = sum(f.count for f in request.flights if f.required)
            if not self.apportionment.can_afford(category, cost):
                continue
            composed = self._commit(request, tot, category)
            if composed is not None:
                self._mark_planned(nomination)
                if isinstance(nomination.target, SamGroundObject):
                    self.suppressed[nomination.target.id] = (
                        composed.package.time_over_target
                    )

    # ======================================================= recovery

    def _plan_recovery(self) -> None:
        if not self.profile.get("enablers", "recovery_tanker", True):
            return
        settings = self.game.settings
        per_tanker = int(getattr(settings, "aircraft_per_recovery_tanker", 4))
        for carrier, _ in self.state.recovery_targets.items():
            sorties = sum(
                f.count
                for p in self.coalition.ato.packages
                for f in p.flights
                if f.departure is carrier and not f.is_helo
            )
            if sorties < per_tanker + 4:
                continue
            self._plan_line(
                carrier,
                FlightType.RECOVERY,
                "Carrier recovery tanker",
                None,
                max_packages=3,
            )

    # ========================================================== record

    def _record(self) -> None:
        side = self.side
        side.jiptl = snapshot(self.nominations[:60], self.planned_keys)
        side.apportioned = dict(self.apportionment.quota)
        side.planned = dict(self.apportionment.used)
        side.total_sorties = self.apportionment.total
        side.intent = self._intent()
        logging.info(
            f"JFACC {'blue' if self.player.is_blue else 'red'}: {self.phase.title}; "
            f"{self.apportionment.total_used()}/{self.apportionment.total} sorties "
            f"planned; {len(self.coalition.ato.packages)} packages; "
            f"{len(side.scrubbed)} scrubbed; "
            f"{self.ledger.second_sorties()} second sorties"
        )

    def _intent(self) -> str:
        spec = self.spec
        effort = self.assessment.main_effort
        effort_text = ""
        if effort is not None:
            effort_text = (
                f" Main effort: {effort.friendly_cp.name} front "
                f"(force ratio {min(effort.force_ratio, 99):.1f})."
            )
        weather = self.conditions.describe()
        modifiers = "".join(
            f" {m.description or m.name.replace('_', ' ').capitalize()}"
            for m in self.modifiers
        )
        return f"{spec.description}{modifiers}{effort_text} Conditions: {weather}."


def plan(game: Game, player: Player, now: datetime, tracer: MultiEventTracer) -> bool:
    """Plan the side's ATO with the JFACC planner. Returns False when the side
    uses the legacy planner."""
    profile = profile_for(game, player)
    if profile is None:
        return False
    JfaccPlanner(game, player, profile).plan_missions(now, tracer)
    return True
