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
from .faca import is_fac, mark_fac
from .scheduler import Timeline, patrol_end
from .sorties import SortieLedger, role_for
from .targets import TargetNomination, TargetNominator, snapshot
from . import weaponeering

if TYPE_CHECKING:
    from game import Game
    from game.coalition import Coalition
    from game.profiling import MultiEventTracer
    from game.sim.combat.model.fuel import RefuelingSystem
    from game.theater import ControlPoint, MissionTarget
    from game.theater.player import Player
    from game.squadrons import Squadron
    from game.theater.frontline import FrontLine
    from .threat import RouteThreat


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
        missing = (
            squadron.max_size - squadron.owned_aircraft - squadron.pending_deliveries
        )
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
    for squadron in sorted(
        squadrons, key=lambda s: s.owned_aircraft + s.pending_deliveries
    ):
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


#: Categories the focused-turn package guidance limits (F6). Personnel
#: recovery, support and DCA are planned first and aren't limited.
BUDGETED_CATEGORIES = {
    Category.OCA,
    Category.SEAD,
    Category.STRIKE,
    Category.INTERDICTION,
    Category.CAS,
}


def counts_toward_target(package: Any) -> bool:
    """Whether a package counts toward the focused-turn package guidance."""
    flights = list(package.flights)
    if not flights or all(getattr(f, "alert", False) for f in flights):
        return False
    if all(getattr(f, "returning", False) for f in flights):
        return False
    if all(f.flight_type in UNCOUNTED_TASKS for f in flights):
        return False
    from .dca import HVAA_PREFIX

    return not str(getattr(package.target, "name", "")).startswith(HVAA_PREFIX)


#: Support lines that don't count toward the package guidance.
UNCOUNTED_TASKS = {
    FlightType.AEWC,
    FlightType.REFUELING,
    FlightType.RECOVERY,
    FlightType.RESCUE_KING,
}

#: Categories whose packages are offensive strikes: the main push takes its
#: share of each.
OFFENSIVE_CATEGORIES = {
    Category.OCA,
    Category.SEAD,
    Category.STRIKE,
    Category.INTERDICTION,
}


def is_offensive_package(package: Any) -> bool:
    """Whether a package is an offensive strike (OCA, SEAD, strike or
    interdiction), as opposed to a line, an alert or support."""
    task = package.primary_task
    if task is None or not counts_toward_target(package):
        return False
    return category_for_task(task) in OFFENSIVE_CATEGORIES


def focused_lead_in(game: Game) -> Optional[timedelta]:
    """The lead-in of a focused turn (settings.focused_turns), or None when
    turns plan a whole ATO period."""
    settings = game.settings
    if not getattr(settings, "focused_turns", False):
        return None
    return timedelta(minutes=int(getattr(settings, "focused_lead_in_min", 30)))


def period_hours(game: Game, profile: PlanningProfile) -> float:
    lead_in = focused_lead_in(game)
    if lead_in is not None:
        span = lead_in + game.settings.desired_player_mission_duration
        return span.total_seconds() / 3600
    return float(
        min(profile.period_hours, getattr(game.settings, "ato_period_hours", 6))
    )


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
        lead_in = focused_lead_in(game)
        game.air_campaign.note_period(
            game.turn,
            now,
            end,
            None if lead_in is None else int(lead_in.total_seconds() // 60),
        )
        self.ledger = SortieLedger(self.profile, now, end, seed)
        self.timeline = Timeline(
            self.profile,
            now,
            end,
            window=None if lead_in is None else (now + lead_in, end),
        )
        self.timeline.push = self._main_push(now, end) if lead_in is None else None
        self.side.push_start, self.side.push_end = self.timeline.push or (None, None)
        if blue and self.timeline.push is not None:
            # The DCS window picker opens on blue's main push.
            from game.sim import atoperiod

            atoperiod.set_window_offset(
                game, int((self.timeline.push[0] - now).total_seconds() // 60)
            )
        self.conditions = weaponeering.conditions_for(game, self.profile)

        from game.commander.theaterstate import TheaterState

        with tracer.trace("JFACC theater state"):
            self.state = TheaterState.from_game(game, self.player, now, tracer)
        self._set_stances()

        planning_allowed = not (
            blue and settings.auto_ato_behavior is AutoAtoBehavior.Disabled
        )
        # P7: the commander flies the routine lines and the player plans the
        # rest. Red is always planned by its commander.
        offensive_allowed = planning_allowed and not (
            blue and settings.auto_ato_behavior is AutoAtoBehavior.RoutineOnly
        )

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
        #: Focused turns: about this many packages (guidance, F6).
        self.package_target: Optional[int] = None
        #: Set while planning packages that may exceed the guidance (raids).
        self.budget_exempt = False
        #: Why the last _commit failed ("" when it didn't).
        self.last_scrub_reason = ""
        self.budget_reached = False
        self.dca_stations: list[Any] = []
        if self.timeline.window is not None:
            self.composer.patrol_until = self.timeline.end
            self.package_target = int(getattr(settings, "focused_package_target", 10))
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
        self._set_push_quota()
        self.planned_keys: set[str] = set()
        #: SAM site (or air defense ship) id -> TOT of the package tasked
        #: against it.
        self.suppressed: dict[object, datetime] = {}
        self.aewc_planned = False
        risk_scale = self.effect("risk_scale", 1.0)
        self.composer.risk_multiplier = float(
            self.spec.flag("risk_multiplier", 1.0)
        ) * float(
            risk_scale  # type: ignore[arg-type]
        )
        self.composer.rollback_allowed = bool(
            self.spec.flag("rollback_allowance", False)
        )
        self.composer.phase_name = self.phase.value
        self._apply_experience()

        if planning_allowed:
            with tracer.trace("JFACC personnel recovery"):
                self._plan_csar()
            with tracer.trace("JFACC enablers"):
                self._plan_enablers()
            with tracer.trace("JFACC counter-air"):
                self._plan_dca()
                self._plan_returning()
        if offensive_allowed:
            with tracer.trace("JFACC ground support"):
                self._plan_kill_boxes()
                self._plan_cas()
            with tracer.trace("JFACC air assault"):
                self._plan_air_assault()
            with tracer.trace("JFACC raids"):
                self.budget_exempt = True
                try:
                    self._plan_raids()
                finally:
                    self.budget_exempt = False
            with tracer.trace("JFACC offensive packages"):
                self._choose_rollback_openers()
                self._plan_jiptl()
                if self._rollback_stalled():
                    # The straight-line threat said the normal allowance
                    # could start the rollback, but every SAM site's planned
                    # route was heavier: open on the lightest ones anyway.
                    self._choose_rollback_openers(force=True)
                    self._plan_jiptl()
            self.apportionment.begin_overflow()
            with tracer.trace("JFACC overflow"):
                self._plan_cas()
                self._plan_jiptl()
        if planning_allowed:
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
            if (
                found
                and isinstance(new, (int, float))
                and not isinstance(new, bool)
                and name.endswith("_scale")
            ):
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

    # ========================================================= main push

    def _main_push(
        self, now: datetime, end: datetime
    ) -> Optional[tuple[datetime, datetime]]:
        """Where this side's main push sits in the period: the commander's
        choice from its own doctrine (``period.main_push_start_min``), as
        long as the desired mission duration. None when the profile spreads
        its packages over the period instead."""
        period = self.profile.section("period")
        share = float(period.get("main_push_share", 0.5))
        if share <= 0:
            return None
        length = max(
            self.game.settings.desired_player_mission_duration, timedelta(minutes=30)
        )
        scale = float(self.effect("push_start_scale", 1.0))  # type: ignore[arg-type]
        start = now + timedelta(
            minutes=scale * float(period.get("main_push_start_min", 120))
        )
        earliest = now + timedelta(minutes=float(period.get("earliest_tot_min", 20)))
        if start + length > end:
            start = end - length
        start = max(start, earliest - self.timeline.h_hour)
        if start + length > end:
            return None
        return start, start + length

    def _set_push_quota(self) -> None:
        """About ``main_push_share`` of each offensive category's sorties go
        into the main push, so the push holds the phase's main effort in a
        representative mix (SEAD and DEAD first, then the strikes)."""
        self.push_quota: dict[Category, int] = {}
        self.push_used: dict[Category, int] = {}
        if self.timeline.push is None:
            return
        share = float(self.profile.get("period", "main_push_share", 0.5))
        for category, quota in self.apportionment.quota.items():
            if category in OFFENSIVE_CATEGORIES:
                self.push_quota[category] = int(round(quota * share))

    def _push_first(self, category: Optional[Category]) -> Optional[bool]:
        """Whether the next package of this category belongs in the main
        push (True), outside it (False), or anywhere (None: no push)."""
        if self.timeline.push is None or category is None:
            return None
        return self.push_used.get(category, 0) < self.push_quota.get(category, 0)

    def _strike_tot(
        self, position: Any, category: Optional[Category]
    ) -> Optional[datetime]:
        """A TOT in the main push or outside it, by the push quota, with the
        other as the fallback."""
        first = self._push_first(category)
        if first is None:
            return self.timeline.strike_tot(
                position, self._wave_preference(category) if category else None
            )
        for push in (first, not first):
            tot = self.timeline.strike_tot(
                position,
                self._wave_preference(category, push) if category else None,
                push=push,
            )
            if tot is not None:
                return tot
        return None

    def _note_push_spend(self, category: Optional[Category], composed: Any) -> None:
        if category is None or composed is None:
            return
        if self.timeline.in_push(composed.package.time_over_target):
            self.push_used[category] = (
                self.push_used.get(category, 0) + composed.sorties
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
        # Turn 1: red's posture at H-hour (game.opening, T8).
        from game.opening import alert_pairs_bonus

        pairs += alert_pairs_bonus(self.game, self.player)
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
        bases = self._alert_bases(reach * 1.5, int(alert.get("bases_max", 4)))
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
                    flights=[
                        FlightRequest(FlightType.BARCAP, size, home=base, alert=True)
                    ],
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
                held.append(
                    f"{flight.count}x {flight.unit_type.display_name} at {base.name}"
                )
        return held

    def _alert_bases(self, reach_nm: float, limit: int) -> list[Any]:
        """Own bases with fighters that can hold an alert, nearest to the
        enemy's fighter bases first, within reach of at least one."""
        from .dca import _enemy_fighter_bases

        enemy = [
            base.position for base, _ in _enemy_fighter_bases(self.game, self.player)
        ]
        if not enemy:
            return []
        ranked: list[tuple[float, Any]] = []
        for cp in self.game.theater.control_points_for(self.player):
            if cp.is_fleet:
                continue
            if not any(
                s.location is cp
                and s.untasked_aircraft >= 2
                and FlightType.BARCAP in s.auto_assignable_mission_types
                and role_for(s) == "fighter"
                for s in self.coalition.air_wing.iter_squadrons()
            ):
                continue
            distance = min(cp.position.distance_to_point(p) for p in enemy) / 1852.0
            if distance <= reach_nm:
                ranked.append((distance, cp))
        ranked.sort(key=lambda r: r[0])
        return [cp for _, cp in ranked[:limit]]

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
        if category in BUDGETED_CATEGORIES and self._over_package_target():
            if not self.budget_reached:
                self.budget_reached = True
                self.side.scrubbed.append(
                    (
                        request.target.name,
                        f"packages per turn reached ({self.package_target}): "
                        "no further offensive packages",
                    )
                )
            return None
        composed, why = self.composer.compose(request, tot, self.now)
        self.last_scrub_reason = why if composed is None else ""
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

    def _over_package_target(self) -> bool:
        """Whether the side already has the turn's guidance of combat
        packages. Ground alerts (they only fly when scrambled), AEW&C, tankers
        and their HVAA CAPs don't count."""
        if self.package_target is None or self.budget_exempt:
            return False
        return (
            sum(1 for p in self.coalition.ato.packages if counts_toward_target(p))
            >= self.package_target
        )

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
            # Rescue as soon as the package can get there.
            tot = self.timeline.earliest
            # Helicopters on a Rescue King (game/farps.py) are the nearest
            # squadron when the King is near the pilot, so they go first.
            request = PackageRequest(
                target=pilot,
                flights=[FlightRequest(FlightType.CSAR, size)]
                + self.composer.support_for(threat, size),
                category_name="pr",
                reason="Personnel recovery",
                risk_kind="troops_in_contact",
                threat=threat,
            )
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
        refueling_system: Optional[RefuelingSystem] = None,
    ) -> list[ComposedPackage]:
        """A continuous line: relief arrives as the previous flight leaves."""
        planned: list[ComposedPackage] = []
        tot = first or self.timeline.earliest
        end = until or self.timeline.end
        while tot < end and len(planned) < max_packages:
            if category is not None and not self.apportionment.can_afford(
                category, size
            ):
                break
            request = PackageRequest(
                target=target,
                flights=[FlightRequest(task, size, refueling_system=refueling_system)],
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
            if not self._relief_needed(next_tot, end):
                break
            tot = next_tot - timedelta(minutes=5)
        return planned

    def _plan_returning(self) -> None:
        """Focused turns (F3): a few CAPs that flew the shift before this one
        and are on their way home when the mission starts. Real sorties: the
        airframes are busy, the flights can be intercepted on the way home,
        and losses count. Their earlier patrol is assumed, not fought."""
        window = self.timeline.window
        if window is None or not self.dca_stations:
            return
        period = self.profile.section("period")
        wanted = int(period.get("returning_flights", 2))
        patrol = float(period.get("returning_patrol_min", 40))
        # Off station a few minutes before the mission starts, so it is on
        # its way home then. The end of its shift falls in the lead-in and is
        # fought there; the part before the turn is assumed.
        leave = window[0] - timedelta(
            minutes=float(period.get("returning_left_station_min", 5))
        )
        tot = leave - timedelta(minutes=patrol)
        size = int(self.profile.get("dca", "cap_flight_size", 2))
        planned = 0
        for station in self.dca_stations:
            if planned >= wanted:
                break
            request = PackageRequest(
                target=station,
                flights=[
                    FlightRequest(
                        FlightType.BARCAP,
                        size,
                        returning=True,
                        patrol_minutes=patrol,
                    )
                ],
                category_name="dca",
                reason="Returning from the previous CAP shift",
            )
            composed, why = self.composer.compose(
                request, tot, tot - timedelta(hours=3)
            )
            if composed is None:
                self.side.scrubbed.append((station.name, f"returning CAP: {why}"))
                continue
            package = composed.package
            package.planning_rationale = (
                f"{self.phase.title} | Returning from the previous CAP shift: on "
                "its way home when the mission starts"
            )
            package.planning_info = {
                "phase": self.phase.title,
                "reason": request.reason,
                "threat": "",
                "risk": "",
                "notes": ["Flew before this turn; lands during the mission"],
            }
            self.coalition.ato.add_package(package)
            planned += 1

    def _relief_needed(self, line_ends: datetime, until: datetime) -> bool:
        """Whether a line ending at ``line_ends`` needs a relief to cover up to
        ``until``. In a focused turn a gap at the very end of the window isn't
        worth another flight."""
        if self.timeline.window is None:
            return line_ends < until
        gap = timedelta(
            minutes=float(self.profile.get("period", "min_relief_gap_min", 15))
        )
        return line_ends < until - gap

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
            # One line per tanker track: boom tankers where the boom receivers
            # fly, drogue tankers off the carriers and for probe aircraft
            # ashore (tankers.py).
            from game.theater import ControlPoint

            from .tankers import tanker_tracks

            max_tracks = int(enablers.get("tanker_tracks_max", 3))
            for front in self.state.refueling_targets:
                if not isinstance(front, ControlPoint):
                    continue
                for track in tanker_tracks(self.coalition, front, max_tracks):
                    packages = self._plan_line(
                        track.anchor,
                        FlightType.REFUELING,
                        track.reason,
                        None,
                        refueling_system=track.system,
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
        if self.timeline.window is not None:
            end_time = min(end_time, self.timeline.end)
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
        forward = tuple(
            float(f) * scale for f in dca.get("station_forward_nm", [25, 60])
        )
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

        def place(axis: Any, scale: float = 1.0) -> Any:
            return station_for(
                self.game,
                self.player,
                axis,
                (float(forward[0]) * scale, float(forward[1]) * scale),
                under_own_sams=under_own_sams,
            )

        stations = [place(axis) for axis in axes]
        axis_of = {id(station): axis for station, axis in zip(stations, axes)}
        if dca.get("point_defense", True):
            for cp in threatened_bases(self.game, self.player, reach):
                if cp.is_fleet:
                    stations.append(cp)
        # Two axes can end up at the same station (a learned axis next to a
        # geometric one): one CAP covers both.
        merge_m = float(dca.get("station_merge_nm", 10)) * 1852
        unique: list[Any] = []
        for station in stations:
            if all(
                station.position.distance_to_point(other.position) > merge_m
                for other in unique
            ):
                unique.append(station)
        stations = unique
        self.dca_stations = stations
        if not stations:
            return
        # Round-robin in time so every axis is covered before any line is
        # extended: limited DCA sorties cover all axes for part of the period
        # rather than one axis all day.
        next_tot: dict[int, datetime] = {
            i: self.timeline.earliest - timedelta(minutes=10)
            for i in range(len(stations))
        }
        open_lines = set(range(len(stations)))
        station_threats: dict[int, RouteThreat] = {}
        # A station whose estimate is over the limit (the enemy moved SAMs up
        # the axis) is pulled back along it before the line is given up:
        # half the forward distance, then over the defended asset.
        pullbacks = [float(s) for s in dca.get("pullback_scales", [0.5, 0.0])]
        pulled: dict[int, int] = {}
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
            if index not in station_threats:
                station_threats[index] = self.composer.threat_for(station)
            request = PackageRequest(
                target=station,
                flights=[FlightRequest(FlightType.BARCAP, size)],
                category_name="dca",
                reason=reason,
                risk_kind="defense",
                threat=station_threats[index],
            )
            composed = self._commit(
                request, max(tot, self.now), Category.DCA, quiet=True
            )
            if composed is None:
                axis = axis_of.get(id(station))
                level = pulled.get(index, 0)
                if (
                    axis is not None
                    and level < len(pullbacks)
                    and "attrition" in self.last_scrub_reason
                ):
                    stations[index] = place(axis, pullbacks[level])
                    axis_of[id(stations[index])] = axis
                    pulled[index] = level + 1
                    station_threats.pop(index, None)
                    continue
                next_tot[index] = tot + timedelta(minutes=30)
                continue
            end = patrol_end(composed.package) or tot + timedelta(hours=1)
            if not self._relief_needed(end, self.timeline.end):
                open_lines.discard(index)
                continue
            next_tot[index] = end - timedelta(minutes=5)

    # ===================================================== ground support

    def _suppressed_before(self, tot: datetime) -> set[object]:
        """SAM sites a DEAD package this period hits before ``tot``."""
        margin = timedelta(minutes=10)
        return {
            tgo_id for tgo_id, when in self.suppressed.items() if when + margin <= tot
        }

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
                flights.append(
                    FlightRequest(FlightType.OCA_AIRCRAFT, 2, required=False)
                )
        exclude = target if isinstance(target, SamGroundObject) else None
        suppressed = self._suppressed_before(tot) if tot is not None else None
        threat = self.composer.threat_for(
            target, exclude=exclude, suppressed=suppressed
        )
        flights += self.composer.support_for(threat, strikers)
        best = self.coalition.air_wing.best_squadron_for(
            target, mission, strikers, False, this_turn=False
        )
        if best is not None and self.composer.needs_tanker(target, best.aircraft):
            # A tanker of the strikers' own system: a boom can't refuel a
            # probe, nor a drogue a receptacle.
            from game.sim.combat.model.fuel import receiver_system

            flights.append(
                FlightRequest(
                    FlightType.REFUELING,
                    1,
                    required=False,
                    note="package tanker",
                    refueling_system=receiver_system(best.aircraft),
                )
            )
        reason = (
            f"JIPTL #{nomination.rank} {nomination.target_class.replace('_', ' ')} "
            f"({nomination.status}, desired effect {nomination.desired_effect:.0%}, "
            f"assessed {nomination.assessed_effect:.0%} when planned)"
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
            tot = self._strike_tot(lead.target.position, Category.INTERDICTION)
            if tot is None:
                continue
            composed = self._commit(request, tot, Category.INTERDICTION)
            if composed is not None:
                self._note_push_spend(Category.INTERDICTION, composed)
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
            # FAC(A) (V3): over the main effort, an optional second element
            # that finds and marks targets and talks the CAS on.
            fac = (
                bool(gs.get("fac_a_line", False))
                and effort is not None
                and front is effort.front
            )
            fac_request = (
                [
                    FlightRequest(
                        FlightType.CAS,
                        int(gs.get("fac_a_flight_size", 2)),
                        required=False,
                        note="FAC(A)",
                    )
                ]
                if fac
                else []
            )
            request = PackageRequest(
                target=front,
                flights=[FlightRequest(FlightType.CAS, size)]
                + fac_request
                + self.composer.support_for(threat, size),
                category_name="cas",
                reason=(
                    "CAS for troops in contact"
                    + (
                        " (main effort)"
                        if effort is not None and front is effort.front
                        else ""
                    )
                ),
                risk_kind="troops_in_contact",
                threat=threat,
            )
            composed = self._commit(request, tot, Category.CAS)
            if composed is not None:
                planned_tots.add((tot, id(front)))
                if fac:
                    self._mark_fac_a(composed)
                kills = sum(
                    flight_kills_or_fallback(f, armor[id(front)])
                    for f in composed.package.flights
                    if f.flight_type is FlightType.CAS and not is_fac(f)
                )
                tasked[id(front)] = tasked.get(id(front), 0.0) + kills
                composed.package.planning_rationale += (
                    f" | expected {kills:.0f} vehicles destroyed"
                )
        self._cas_tots = planned_tots
        self._cas_kills = tasked

    @staticmethod
    def _mark_fac_a(composed: ComposedPackage) -> None:
        """Flags the second CAS element of a main effort package as its
        FAC(A), if it was placed and its type can fly the AFAC task."""
        package = composed.package
        cas = [f for f in package.flights if f.flight_type is FlightType.CAS]
        info = package.planning_info if package.planning_info is not None else {}
        package.planning_info = info
        notes: list[str] = info.setdefault("notes", [])  # type: ignore[assignment]
        if len(cas) < 2:
            return
        if mark_fac(cas[-1]):
            package.planning_rationale += (
                f" | FAC(A): {cas[-1].unit_type.display_name} finds and marks "
                "targets, talks the CAS on"
            )
            notes.append("FAC(A): controls the CAS on this front")
        else:
            notes.append("FAC(A) type cannot fly AFAC in DCS: flies as CAS")

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
            # Ahead of the main effort: in the main push when there is one.
            tot = self.timeline.strike_tot(cp.position, preferred_wave=1, push=True)
            if tot is None:
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

    #: Preferred wave inside the main push: suppression at H-hour, the
    #: strikes minutes later through the corridors it opens, then the
    #: follow-up.
    PUSH_WAVE_PREFERENCE = {
        Category.SEAD: 0,
        Category.OCA: 1,
        Category.STRIKE: 1,
        Category.INTERDICTION: 2,
    }

    def _wave_preference(
        self, category: Category, push: Optional[bool] = None
    ) -> Optional[int]:
        if push:
            return self.PUSH_WAVE_PREFERENCE.get(category)
        table = self.spec.flag("wave_preference")
        if isinstance(table, dict):
            value = table.get(category.value)
            return None if value is None else int(value)
        return self.WAVE_PREFERENCE.get(category)

    def _rollback_stalled(self) -> bool:
        """Rollback is allowed, no openers were named and no SAM site was
        attacked this period."""
        from game.theater.theatergroundobject import SamGroundObject

        sam_attacked = any(
            isinstance(n.target, SamGroundObject)
            and getattr(n.target, "id", None) in self.suppressed
            for n in self.nominations
        )
        return (
            self.composer.rollback_allowed
            and not self.composer.opener_targets
            and not sam_attacked
        )

    def _choose_rollback_openers(self, force: bool = False) -> None:
        """Item 6: against a dense IADS even the outermost SAM sites are
        beyond the rollback allowance's route weight, so no DEAD is ever
        acceptable and the IADS is never thinned. When that happens, the
        least-defended sites (``opener_packages``, by route threat) may be
        attacked up to ``opener_limit``: the rollback has to start
        somewhere.

        The check uses the straight-line route; the planned routes are often
        heavier. ``force`` names the openers without the check, for when the
        first offensive pass attacked no SAM site at all."""
        from game.theater.theatergroundobject import SamGroundObject

        self.composer.opener_targets = set()
        if not self.composer.rollback_allowed:
            return
        allowance = self.profile.get("risk", "rollback_allowance", {}) or {}
        count = int(allowance.get("opener_packages", 2))
        if count <= 0:
            return
        max_weight = float(allowance.get("max_route_weight", 0))
        weighed: list[tuple[float, Any]] = []
        for nomination in self.nominations:
            target = nomination.target
            if nomination.priority <= 0 or not isinstance(target, SamGroundObject):
                continue
            threat = self.composer.threat_for(target, exclude=target)
            weighed.append((threat.sam_weight, target))
        if not weighed:
            return
        weighed.sort(key=lambda pair: pair[0])
        if not force and weighed[0][0] <= max_weight:
            # The normal allowance can start the rollback.
            return
        self.composer.opener_targets = {t.id for _, t in weighed[:count]}
        names = ", ".join(t.name for _, t in weighed[:count])
        logging.info(
            f"JFACC {self.player}: no SAM site within the rollback allowance "
            f"(lightest route weight {weighed[0][0]:.1f}); opening on {names}"
        )

    def _route_guard_ships(self) -> set[int]:
        """Air defense ships whose envelope (plus 5 nm) reaches the straight
        route from our nearest base to a nominated target."""
        from shapely.geometry import LineString, Point as ShapelyPoint

        ships = [
            n.target
            for n in self.nominations
            if n.priority > 0 and _air_defense_ship(n.target)
        ]
        if not ships:
            return set()
        routes = []
        for nomination in self.nominations:
            if nomination.priority <= 0 or _air_defense_ship(nomination.target):
                continue
            origin = self.composer.origin_for(nomination.target)
            if origin is None:
                continue
            start = origin.position  # type: ignore[attr-defined]
            end = nomination.target.position
            routes.append(LineString([(start.x, start.y), (end.x, end.y)]))
        guarding: set[int] = set()
        for ship in ships:
            reach = ship.max_threat_range().meters + 5 * 1852  # type: ignore[attr-defined]
            point = ShapelyPoint(ship.position.x, ship.position.y)
            if any(route.distance(point) <= reach for route in routes):
                guarding.add(id(ship))
        return guarding

    def _plan_jiptl(self) -> None:
        from game.theater.theatergroundobject import SamGroundObject

        # H-hour sequencing (item 2): suppression is planned first, in the
        # first wave, so the strikes of the next wave can fly through the SEAD
        # corridors it opens instead of each needing its own HARM escort.
        # Air defense ships are suppression too: a frigate's missiles cover
        # the routes past it, so it is attacked in the suppression wave with
        # the DEAD instead of by a later anti-ship strike.
        # A ship covering the way to this period's targets goes first among
        # them: it is a small package and every later route is safer for it.
        openers = self.composer.opener_targets
        guarding = self._route_guard_ships()
        ordered = sorted(
            self.nominations,
            key=lambda n: (
                0 if getattr(n.target, "id", None) in openers else 1,
                0 if n.category is Category.SEAD or _air_defense_ship(n.target) else 1,
                0 if id(n.target) in guarding else 1,
            ),
        )
        for nomination in ordered:
            if nomination.priority <= 0 or nomination.key in self.planned_keys:
                continue
            category = nomination.category
            if self.apportionment.remaining(category) <= 0:
                continue
            if not self.coalition.air_wing.can_auto_plan(nomination.mission):
                continue
            ad_ship = _air_defense_ship(nomination.target)
            tot = self._strike_tot(
                nomination.target.position, Category.SEAD if ad_ship else category
            )
            if tot is None:
                continue
            request = self._offensive_request(nomination, tot=tot)
            cost = sum(f.count for f in request.flights if f.required)
            if not self.apportionment.can_afford(category, cost):
                continue
            composed = self._commit(request, tot, category)
            if composed is not None:
                self._note_push_spend(category, composed)
                self._mark_planned(nomination)
                if isinstance(nomination.target, SamGroundObject) or ad_ship:
                    self.suppressed[nomination.target.id] = (  # type: ignore[attr-defined]
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

    def _apply_experience(self) -> None:
        from . import experience

        config = experience.ExperienceConfig.from_profile(
            self.profile.section("risk").get("experience")
        )
        self.composer.experience = {
            kind: experience.factor(self.side, kind, config)
            for kind in (experience.STRIKE, experience.STATION)
        }

    def _record(self) -> None:
        from . import experience

        side = self.side
        experience.note_plan(side, self.coalition.ato.packages)
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


def _air_defense_ship(target: object) -> bool:
    """An enemy ship group whose air defense counts in the route threat."""
    from game.theater.theatergroundobject import NavalGroundObject

    from .targetclass import sam_weight

    if not isinstance(target, NavalGroundObject):
        return False
    try:
        return sam_weight(target) > 0
    except Exception:
        return False
