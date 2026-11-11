"""Campaign-level war state: intelligence pictures and morale.

Held by :attr:`Game.war_state`. Updated after each mission from the debriefing
(:meth:`WarState.after_mission`) and once per turn (:meth:`WarState.end_turn`).
"""

from __future__ import annotations

import logging
import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Optional, TYPE_CHECKING

from .doctrine import CombatDoctrine, for_faction_obj
from .intel import IntelPicture, IntelSource, enemy_ground_objects, is_mobile, tgo_by_id
from .morale import MoraleState

if TYPE_CHECKING:
    from uuid import UUID

    from game import Game
    from game.squadrons import Squadron
    from game.ato import Flight
    from game.coalition import Coalition
    from game.debriefing import Debriefing
    from game.theater import TheaterGroundObject
    from game.theater.player import Player


@dataclass(frozen=True)
class IntelEvent:
    """Something a side learned during the simulation."""

    observer_blue: bool
    tgo_id: object
    quality: float
    source: IntelSource


@dataclass(frozen=True)
class CombatCredit:
    """Something a flight achieved or suffered, for squadron morale."""

    flight: Flight
    kind: str  # air_kill | strike_success | abort | cas_kill | arm_attack
    tgo_id: object = None


@dataclass
class WarState:
    intel: dict[bool, IntelPicture] = field(default_factory=dict)
    morale: MoraleState = field(default_factory=MoraleState)
    seed: int = field(default_factory=lambda: random.randrange(2**31))
    #: Squadrons that flew in the last mission (for rest-based recovery).
    flown_squadrons: set[object] = field(default_factory=set)
    #: Decoys beside each site, as offsets (dx, dy) from it (game.warfare.deception).
    deception: dict[object, list[tuple[float, float]]] = field(default_factory=dict)
    #: Civilian casualty incidents caused by each side (blue -> count).
    collateral_incidents: dict[bool, int] = field(default_factory=dict)
    #: Turn for which agency warnings have been issued to the player.
    warnings_turn: int = -1

    def __setstate__(self, state: dict[str, object]) -> None:
        # Fill fields added after the save was made.
        self.__dict__.update({**WarState().__dict__, **state})

    # ------------------------------------------------------------------ access

    def rng(self, game: Game, salt: str) -> random.Random:
        return random.Random(f"{self.seed}:{game.turn}:{salt}")

    @staticmethod
    def doctrine(game: Game, player: Player) -> CombatDoctrine:
        return for_faction_obj(game.coalition_for(player).faction)

    @staticmethod
    def intel_enabled(game: Game) -> bool:
        return bool(getattr(game.settings, "intel_enabled", True))

    @staticmethod
    def morale_enabled(game: Game) -> bool:
        return bool(getattr(game.settings, "morale_enabled", True))

    def picture(self, game: Game, viewer: Player) -> IntelPicture:
        """The viewer's intelligence picture of its enemy."""
        picture = self.intel.get(viewer.is_blue)
        if picture is None or not picture.initialized:
            doctrine = self.doctrine(game, viewer)
            picture = IntelPicture(isr=doctrine.isr)
            self.intel[viewer.is_blue] = picture
            picture.initialize(
                game, viewer, doctrine.prewar_mobile, self.rng(game, f"prewar{viewer}")
            )
        return picture

    def knows(self, game: Game, viewer: Player, tgo: TheaterGroundObject) -> bool:
        if not self.intel_enabled(game):
            return True
        return self.picture(game, viewer).knows(tgo)

    def believed_alive(
        self, game: Game, viewer: Player, tgo: TheaterGroundObject
    ) -> bool:
        if not self.intel_enabled(game):
            return not tgo.is_dead
        return self.picture(game, viewer).believed_alive(tgo)

    # ------------------------------------------------------------------ mission

    def after_mission(self, game: Game, debriefing: Debriefing) -> None:
        try:
            if self.intel_enabled(game):
                self._update_intel(game, debriefing)
            if self.morale_enabled(game):
                self._update_morale(game, debriefing)
        except Exception:
            logging.exception("Failed to update war state after mission")

    def _flights_flown(self, game: Game, debriefing: Debriefing) -> list[Flight]:
        flights = list(getattr(debriefing, "flights_flown", []) or [])
        if not flights:
            for coalition in (game.blue, game.red):
                for package in coalition.ato.packages:
                    flights.extend(package.flights)
        return flights

    def _update_intel(self, game: Game, debriefing: Debriefing) -> None:
        from game.ato.flighttype import FlightType
        from game.theater.player import Player

        turn = game.turn
        rng = self.rng(game, "intel")
        flights = self._flights_flown(game, debriefing)
        recon_targets: dict[bool, set[UUID]] = defaultdict(set)
        attacked: dict[bool, set[UUID]] = defaultdict(set)

        for flight in flights:
            viewer = flight.squadron.player
            picture = self.picture(game, viewer)
            target = flight.package.target
            target_tgos = _target_tgos(target)
            if flight.flight_type is FlightType.AEWC:
                self._elint_sweep(game, viewer, flight, picture, rng)
                continue
            for target_tgo in target_tgos:
                if target_tgo.control_point.captured is viewer:
                    continue
                if flight.flight_type.name == "RECON":
                    picture.observe(target_tgo, 0.95, IntelSource.RECON, turn, rng)
                    recon_targets[viewer.is_blue].add(target_tgo.id)
                elif flight.flight_type.is_air_to_ground:
                    picture.observe(
                        target_tgo,
                        0.45 + 0.3 * picture.isr,
                        IntelSource.STRIKE,
                        turn,
                        rng,
                    )
                    attacked[viewer.is_blue].add(target_tgo.id)
            # Things seen along the route.
            self._route_sightings(game, viewer, flight, picture, rng)

        # Early warning radars listen for emitters every turn.
        for viewer in (Player.BLUE, Player.RED):
            self._ewr_sweep(game, viewer, self.picture(game, viewer), rng)

        # Events from the fast-forward simulation.
        for event in getattr(debriefing, "intel_events", []) or []:
            viewer = Player.BLUE if event.observer_blue else Player.RED
            tgo = tgo_by_id(game, event.tgo_id)
            if tgo is None or tgo.control_point.captured is viewer:
                continue
            self.picture(game, viewer).observe(
                tgo, event.quality, event.source, turn, rng
            )

        # Battle damage assessment.
        for mapping in debriefing.ground_object_losses:
            unit = mapping.theater_unit
            tgo = unit.ground_object
            viewer = tgo.control_point.captured.opponent
            picture = self.picture(game, viewer)
            if tgo.id in recon_targets[viewer.is_blue]:
                reliability = 1.0
            else:
                reliability = 0.55 + 0.35 * picture.isr
            picture.report_kill(tgo, unit.id, reliability, rng)
        for blue, tgo_ids in attacked.items():
            viewer = Player.BLUE if blue else Player.RED
            picture = self.picture(game, viewer)
            for tgo_id in tgo_ids:
                tgo = tgo_by_id(game, tgo_id)
                if tgo is not None and tgo_id not in recon_targets[blue]:
                    picture.overclaim(tgo, 0.15 * (1 - picture.isr), rng)

        # Mobile sites that fired relocate.
        fired = [
            e
            for e in getattr(debriefing, "intel_events", []) or []
            if e.source is IntelSource.ENGAGEMENT
        ]
        managed: dict[bool, bool] = {}
        for event in fired:
            tgo = tgo_by_id(game, event.tgo_id)
            if tgo is None or not is_mobile(tgo):
                continue
            owner = tgo.control_point.captured
            if owner.is_blue not in managed:
                from game.commander.jfacc.iads import manages_iads

                managed[owner.is_blue] = manages_iads(game, owner)
            if managed[owner.is_blue]:
                # The side's IADS management moves its sites for real
                # (game.commander.jfacc.iads.reposition_iads).
                continue
            if self.doctrine(game, owner).shoot_and_scoot and rng.random() < 0.5:
                viewer = Player.BLUE if event.observer_blue else Player.RED
                self.picture(game, viewer).scooted(tgo)

    def _elint_sweep(
        self,
        game: Game,
        viewer: Player,
        flight: Flight,
        picture: IntelPicture,
        rng: random.Random,
    ) -> None:
        """AWACS listening for radar emitters from its orbit."""
        from game.sim.combat.model.profiles import CombatProfiles

        profile = CombatProfiles.instance().aircraft(flight.unit_type)
        reach_m = max(profile.awacs_km, 250) * 1000 * 0.8
        waypoints = [w.position for w in flight.flight_plan.waypoints]
        for tgo in enemy_ground_objects(game, viewer):
            if tgo.is_dead or not getattr(tgo, "has_live_radar_sam", False):
                continue
            if any(w.distance_to_point(tgo.position) <= reach_m for w in waypoints):
                picture.observe(
                    tgo, 0.3 + 0.35 * picture.isr, IntelSource.ELINT, game.turn, rng
                )

    def _ewr_sweep(
        self, game: Game, viewer: Player, picture: IntelPicture, rng: random.Random
    ) -> None:
        from game.theater.theatergroundobject import EwrGroundObject

        ewrs = [
            tgo
            for cp in game.theater.control_points_for(viewer)
            for tgo in cp.ground_objects
            if isinstance(tgo, EwrGroundObject) and not tgo.is_dead
        ]
        if not ewrs:
            return
        for tgo in enemy_ground_objects(game, viewer):
            if tgo.is_dead or not getattr(tgo, "has_live_radar_sam", False):
                continue
            for ewr in ewrs:
                reach = ewr.max_detection_range().meters * 0.8
                if ewr.position.distance_to_point(tgo.position) <= reach:
                    picture.observe(
                        tgo,
                        0.15 + 0.25 * picture.isr,
                        IntelSource.ELINT,
                        game.turn,
                        rng,
                    )
                    break

    def _route_sightings(
        self,
        game: Game,
        viewer: Player,
        flight: Flight,
        picture: IntelPicture,
        rng: random.Random,
    ) -> None:
        try:
            waypoints = [w.position for w in flight.flight_plan.waypoints]
        except Exception:
            return
        for tgo in enemy_ground_objects(game, viewer):
            if tgo.is_dead:
                continue
            if any(w.distance_to_point(tgo.position) <= 12000 for w in waypoints):
                if rng.random() < 0.5:
                    picture.observe(tgo, 0.25, IntelSource.VISUAL, game.turn, rng)
                    from .deception import maybe_fooled

                    maybe_fooled(game, self, picture, tgo, IntelSource.VISUAL, rng)

    def _update_morale(self, game: Game, debriefing: Debriefing) -> None:
        from game.theater.player import Player

        morale = self.morale
        flights = self._flights_flown(game, debriefing)
        self.flown_squadrons = {f.squadron.id for f in flights}

        # Squadrons: losses and achievements.
        losses: Counter[object] = Counter()
        pilots: Counter[object] = Counter()
        squadrons: dict[object, Squadron] = {}
        for loss in debriefing.air_losses.losses:
            squadron = loss.flight.squadron
            squadrons[squadron.id] = squadron
            losses[squadron.id] += 1
            if loss.pilot is not None:
                pilots[squadron.id] += 1
        for squadron_id, lost in losses.items():
            squadron = squadrons[squadron_id]
            size = max(squadron.owned_aircraft + lost, 4)
            scale = 8 / size
            delta = -(0.06 * lost + 0.03 * pilots[squadron_id]) * scale
            value = morale.adjust_squadron(squadron, max(delta, -0.35))
            if value < 0.35:
                game.message(
                    "Squadron morale",
                    f"{squadron} is badly shaken after losing {lost} aircraft "
                    f"(morale {value:.0%}).",
                )
        for credit in getattr(debriefing, "combat_credits", []) or []:
            delta = {
                "air_kill": 0.04,
                "strike_success": 0.03,
                "cas_kill": 0.005,
                "abort": -0.04,
            }.get(credit.kind, 0.0)
            if delta:
                morale.adjust_squadron(credit.flight.squadron, delta)
        for flight in flights:
            if flight.squadron.id not in losses and flight.alive:
                morale.adjust_squadron(flight.squadron, 0.01)

        # Fronts: casualty exchange and air support.
        cas_support: Counter[bool] = Counter(
            c.flight.squadron.player.is_blue
            for c in getattr(debriefing, "combat_credits", []) or []
            if c.kind == "cas_kill"
        )
        for front_line in game.theater.conflicts():
            blue_cp, red_cp = front_line.blue_cp, front_line.red_cp
            blue_cas = debriefing.casualty_count(blue_cp)
            red_cas = debriefing.casualty_count(red_cp)
            total = max(blue_cas + red_cas, 4)
            morale.adjust_front(
                blue_cp,
                0.3 * (red_cas - blue_cas) / total + min(0.1, 0.01 * cas_support[True]),
            )
            morale.adjust_front(
                red_cp,
                0.3 * (blue_cas - red_cas) / total
                + min(0.1, 0.01 * cas_support[False]),
            )
            for cp in (blue_cp, red_cp):
                if cp.base.total_armor < 6:
                    morale.adjust_front(cp, -0.05)  # Nothing left in reserve.

        # SAM crews: watching neighbours die, being hunted by ARMs.
        hit_sites: set[object] = set()
        for mapping in debriefing.ground_object_losses:
            tgo = mapping.theater_unit.ground_object
            if tgo.has_aa or tgo.is_dead:
                hit_sites.add(tgo.id)
        for site_id in hit_sites:
            site = tgo_by_id(game, site_id)  # type: ignore[arg-type]
            if site is None:
                continue
            for cp in game.theater.control_points_for(site.control_point.captured):
                for other in cp.ground_objects:
                    if other is site or not other.has_aa:
                        continue
                    if other.position.distance_to_point(site.position) <= 40000:
                        morale.adjust_sam_crew(other, -0.1)
        for credit in getattr(debriefing, "combat_credits", []) or []:
            if credit.kind == "arm_attack" and credit.tgo_id is not None:
                site = tgo_by_id(game, credit.tgo_id)
                if site is not None:
                    morale.adjust_sam_crew(site, -0.06)

        # Civilian casualties: the striking side pays at home, the enemy
        # gains a propaganda boost.
        incidents: Counter[bool] = Counter(
            blue for blue in getattr(debriefing, "collateral_events", []) or []
        )
        for blue, count in incidents.items():
            striker = Player.BLUE if blue else Player.RED
            self.collateral_incidents[blue] = (
                self.collateral_incidents.get(blue, 0) + count
            )
            sensitivity = self.doctrine(game, striker).collateral_sensitivity
            morale.adjust_resolve(striker, -min(0.06, 0.015 * sensitivity * count))
            morale.adjust_resolve(striker.opponent, min(0.03, 0.005 * count))
            side = "Our" if blue else "Enemy"
            game.message(
                "Collateral damage",
                f"{side} strikes caused {count} reported civilian casualty "
                f"incident{'s' if count > 1 else ''}.",
            )

        # National resolve.
        if getattr(game.settings, "war_weariness_enabled", True):
            # Losses have already been committed: add them back so the peak
            # reflects the force that went into this battle.
            self._update_peaks(
                game,
                extra_aircraft={
                    True: len(debriefing.air_losses.player),
                    False: len(debriefing.air_losses.enemy),
                },
                extra_armor={
                    True: len(debriefing.ground_losses.player_front_line),
                    False: len(debriefing.ground_losses.enemy_front_line),
                },
            )
            for player in (Player.BLUE, Player.RED):
                blue = player.is_blue
                aircraft_lost = len(
                    debriefing.air_losses.player
                    if blue
                    else debriefing.air_losses.enemy
                )
                ground_lost = len(
                    debriefing.ground_losses.player_front_line
                    if blue
                    else debriefing.ground_losses.enemy_front_line
                )
                bases_lost = sum(
                    1
                    for c in debriefing.base_captures
                    if c.captured_by_player is not player
                    and c.control_point.captured is player
                )
                bases_won = sum(
                    1
                    for c in debriefing.base_captures
                    if c.captured_by_player is player
                )
                peak_air = max(morale.peak_aircraft.get(blue, 1), 1)
                peak_armor = max(morale.peak_armor.get(blue, 1), 1)
                enemy_aircraft_lost = len(
                    debriefing.air_losses.enemy
                    if blue
                    else debriefing.air_losses.player
                )
                enemy_ground_lost = len(
                    debriefing.ground_losses.enemy_front_line
                    if blue
                    else debriefing.ground_losses.player_front_line
                )
                # Visible success sustains the will to fight.
                winning = (
                    enemy_aircraft_lost * 4 + enemy_ground_lost
                    > (aircraft_lost * 4 + ground_lost) * 1.5
                )
                delta = (
                    -(
                        1.0 * aircraft_lost / peak_air
                        + 0.5 * ground_lost / peak_armor
                        + 0.05 * bases_lost
                    )
                    + 0.04 * bases_won
                    + (0.03 if winning else 0.0)
                )
                # A nation's will erodes over weeks, not in an afternoon.
                delta = max(delta, -0.08)
                before = morale.national_resolve(player)
                after = morale.adjust_resolve(player, delta)
                if before >= 0.5 > after:
                    side = "Our" if blue else "Enemy"
                    game.message(
                        "War-weariness",
                        f"{side} resolve is faltering after sustained losses.",
                    )

    def _update_peaks(
        self,
        game: Game,
        extra_aircraft: Optional[dict[bool, int]] = None,
        extra_armor: Optional[dict[bool, int]] = None,
    ) -> None:
        from game.theater.player import Player

        for player in (Player.BLUE, Player.RED):
            coalition = game.coalition_for(player)
            blue = player.is_blue
            aircraft = sum(
                s.owned_aircraft for s in coalition.air_wing.iter_squadrons()
            )
            armor = sum(
                cp.base.total_armor for cp in game.theater.control_points_for(player)
            )
            aircraft += (extra_aircraft or {}).get(blue, 0)
            armor += (extra_armor or {}).get(blue, 0)
            self.morale.peak_aircraft[blue] = max(
                self.morale.peak_aircraft.get(blue, 0), aircraft
            )
            self.morale.peak_armor[blue] = max(
                self.morale.peak_armor.get(blue, 0), armor
            )

    # ------------------------------------------------------------------ turn

    def end_turn(self, game: Game) -> None:
        try:
            self._end_turn(game)
        except Exception:
            logging.exception("Failed to update war state at end of turn")

    def _end_turn(self, game: Game) -> None:
        from game.theater.player import Player

        if self.intel_enabled(game):
            # The pre-war picture and reconnaissance (game.opening) are fresh
            # at Begin Campaign; the strategic round runs right after them (T6).
            if game.turn > 1:
                for player in (Player.BLUE, Player.RED):
                    self.picture(game, player).decay(game, game.turn)
            self._strategic_intel(game)
        if not self.morale_enabled(game):
            return
        morale = self.morale
        self._update_peaks(game)
        for player in (Player.BLUE, Player.RED):
            coalition = game.coalition_for(player)
            baseline = morale.baseline(
                self.doctrine(game, player).morale_baseline, player
            )
            for squadron in coalition.air_wing.iter_squadrons():
                rate = 0.05 if squadron.id in self.flown_squadrons else 0.1
                morale.squadrons[squadron.id] = morale.recover(
                    morale.squadron(squadron), baseline, rate
                )
            for cp in game.theater.control_points_for(player):
                morale.fronts[cp.id] = morale.recover(morale.front(cp), baseline, 0.06)
                for tgo in cp.ground_objects:
                    if tgo.has_aa and tgo.id in morale.sam_crews:
                        morale.sam_crews[tgo.id] = morale.recover(
                            morale.sam_crew(tgo), baseline, 0.06
                        )
            if getattr(game.settings, "war_weariness_enabled", True):
                morale.adjust_resolve(player, 0.01)
        self._surrenders(game)
        self.flown_squadrons = set()

    def _strategic_intel(self, game: Game) -> None:
        """Decoys, satellites and agencies, once per turn."""
        from game.theater.player import Player
        from .agencies import run_agencies
        from .deception import place_decoys
        from .satellites import run_satellites, summarize

        place_decoys(game, self)
        if not getattr(game.settings, "space_and_agency_intel", True):
            return
        for player in (Player.BLUE, Player.RED):
            rng = self.rng(game, f"strategic{player}")
            reports = run_satellites(game, self, player, rng)
            agency = run_agencies(game, self, player, rng)
            if player.is_blue:
                if reports:
                    game.message("Satellite reconnaissance", summarize(reports) + ".")
                if agency.tips_true + agency.tips_false:
                    game.message(
                        "Agency report",
                        f"{agency.tips_true + agency.tips_false} reports of enemy "
                        "sites received; reliability varies.",
                    )

    def after_planning(self, game: Game) -> None:
        """Once both sides have planned: agency warnings for the player."""
        try:
            if self.intel_enabled(game):
                from .agencies import warn_player

                warn_player(game, self)
        except Exception:
            logging.exception("Failed to issue agency warnings")

    def _surrenders(self, game: Game) -> None:
        """Front-line forces whose morale has collapsed lose units without a
        fight: desertion and surrender."""
        rng = self.rng(game, "surrender")
        for front_line in game.theater.conflicts():
            for cp in (front_line.blue_cp, front_line.red_cp):
                if self.morale.front(cp) >= 0.15:
                    continue
                lost = 0
                for unit_type, count in list(cp.base.armor.items()):
                    surrendered = sum(1 for _ in range(count) if rng.random() < 0.08)
                    if surrendered:
                        cp.base.armor[unit_type] -= surrendered
                        lost += surrendered
                if lost:
                    game.message(
                        "Front collapse",
                        f"Demoralised forces at {cp.name} lost {lost} vehicles to "
                        "desertion and surrender.",
                    )

    def apply_readiness(self, game: Game, coalition: Coalition) -> None:
        """Squadrons whose morale has collapsed stand some aircraft down."""
        if not self.morale_enabled(game):
            return
        for squadron in coalition.air_wing.iter_squadrons():
            value = self.morale.squadron(squadron)
            if value >= 0.3:
                continue
            stood_down = int(squadron.untasked_aircraft * (0.3 - value) * 2)
            if stood_down > 0:
                squadron.untasked_aircraft -= min(
                    stood_down, squadron.untasked_aircraft
                )

    def income_factor(self, game: Game, player: Player) -> float:
        if not self.morale_enabled(game) or not getattr(
            game.settings, "war_weariness_enabled", True
        ):
            return 1.0
        return 0.6 + 0.4 * self.morale.national_resolve(player)


def _target_tgos(target: object) -> Iterable[TheaterGroundObject]:
    from game.theater import ControlPoint, TheaterGroundObject

    if isinstance(target, TheaterGroundObject):
        return [target]
    if isinstance(target, ControlPoint):
        return list(target.ground_objects)
    return []
