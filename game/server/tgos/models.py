from __future__ import annotations

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel

from game.data.groups import GroupTask
from game.server.leaflet import LeafletPoint
from game.theater.theatergroundobject import ShipGroundObject

if TYPE_CHECKING:
    from game import Game
    from game.theater import TheaterGroundObject


class TgoJs(BaseModel):
    id: UUID
    name: str
    control_point_name: str
    category: str
    blue: bool
    position: LeafletPoint
    units: list[str]  # TODO: Event stream
    threat_ranges: list[float]  # TODO: Event stream
    detection_ranges: list[float]  # TODO: Event stream
    dead: bool  # TODO: Event stream
    sidc: str  # TODO: Event stream
    task: Optional[GroupTask]
    mobile: bool
    destination: Optional[LeafletPoint]
    #: Fog of war: blue knows this site exists.
    known: bool = True
    #: Fog of war: position, units and ranges are unconfirmed estimates.
    estimated: bool = False
    #: Fog of war: radius of the uncertainty about the position, meters.
    uncertainty_m: float = 0.0
    #: Fog of war: how blue detected this enemy site.
    detection: Optional[str] = None

    class Config:
        title = "Tgo"

    @staticmethod
    def visible(tgo: TheaterGroundObject) -> bool:
        from game.server.fogofwar import game_of, tgo_view

        return tgo_view(game_of(tgo), tgo) is not None

    @staticmethod
    def for_tgo(tgo: TheaterGroundObject) -> TgoJs:
        import dataclasses

        from game.server.fogofwar import detection_summary, game_of, tgo_view
        from game.sidc import Status

        game = game_of(tgo)
        view = tgo_view(game, tgo)
        detection = detection_summary(game, tgo)
        threat_ranges = [group.max_threat_range().meters for group in tgo.groups]
        detection_ranges = [group.max_detection_range().meters for group in tgo.groups]
        units = [unit.display_name for unit in tgo.units]
        position = tgo.position
        dead = tgo.is_dead
        sidc = tgo.sidc()
        estimated = False
        uncertainty = 0.0
        known = True
        if view is not None and not view.confirmed:
            # Show blue's estimate, not the truth.
            known = view.known
            estimated = True
            position = view.position
            uncertainty = view.uncertainty_m
            dead = view.believed_dead
            units = []
            threat_ranges = []
            detection_ranges = []
            sidc = dataclasses.replace(sidc, status=Status.PLANNED_ANTICIPATED_SUSPECT)
        if tgo.control_point.captured.is_blue:
            blue = True
        else:
            blue = False
        mobile = isinstance(tgo, ShipGroundObject) and blue
        destination: Optional[LeafletPoint] = None
        if (
            isinstance(tgo, ShipGroundObject)
            and blue
            and tgo.target_position is not None
        ):
            destination = LeafletPoint.from_latlng(tgo.target_position.latlng())
        return TgoJs(
            id=tgo.id,
            name=tgo.name,
            control_point_name=tgo.control_point.name,
            category=tgo.category,
            blue=blue,
            position=position.latlng(),
            units=units,
            threat_ranges=threat_ranges,
            detection_ranges=detection_ranges,
            dead=dead,
            sidc=str(sidc),
            task=tgo.groups[0].ground_object.task if tgo.groups else None,
            mobile=mobile,
            destination=destination,
            known=known,
            estimated=estimated,
            uncertainty_m=uncertainty,
            detection=detection,
        )

    @staticmethod
    def all_in_game(game: Game) -> list[TgoJs]:
        tgos = []
        for control_point in game.theater.controlpoints:
            for tgo in control_point.connected_objectives:
                if not tgo.is_control_point and TgoJs.visible(tgo):
                    tgos.append(TgoJs.for_tgo(tgo))
        tgos.extend(TgoJs.phantoms(game))
        return tgos

    @staticmethod
    def phantoms(game: Game) -> list[TgoJs]:
        """Enemy sites blue has been told about that may not exist. They look
        exactly like any other unconfirmed report."""
        import dataclasses

        from dcs import Point

        from game.server.fogofwar import fog_mode
        from game.settings.settings import FogOfWar
        from game.sidc import Status
        from game.theater.player import Player
        from game.theater.theatergroundobject import IadsGroundObject
        from game.warfare.intel import IntelSource

        if fog_mode(game) is FogOfWar.OFF:
            return []
        picture = game.war_state.picture(game, Player.BLUE)
        if not picture.phantoms:
            return []
        template = next(
            (
                tgo
                for cp in game.theater.control_points_for(Player.RED)
                for tgo in cp.ground_objects
                if isinstance(tgo, IadsGroundObject)
            ),
            None,
        )
        if template is None:
            return []
        sidc = dataclasses.replace(
            template.sidc(), status=Status.PLANNED_ANTICIPATED_SUSPECT
        )
        phantoms = []
        for phantom in picture.phantoms.values():
            position = Point(phantom.x, phantom.y, game.theater.terrain)
            nearest = min(
                game.theater.control_points_for(Player.RED),
                key=lambda cp: cp.position.distance_to_point(position),
            )
            phantoms.append(
                TgoJs(
                    id=phantom.id,
                    name=f"Reported {phantom.kind} site",
                    control_point_name=nearest.name,
                    category="aa",
                    blue=False,
                    position=position.latlng(),
                    units=[],
                    threat_ranges=[],
                    detection_ranges=[],
                    dead=False,
                    sidc=str(sidc),
                    task=None,
                    mobile=False,
                    destination=None,
                    known=True,
                    estimated=True,
                    uncertainty_m=phantom.error_m,
                    detection=f"Detected via {IntelSource.AGENT.value}, "
                    f"turn {phantom.reported_turn}, "
                    f"confidence {round(phantom.confidence * 100)}%",
                )
            )
        return phantoms
