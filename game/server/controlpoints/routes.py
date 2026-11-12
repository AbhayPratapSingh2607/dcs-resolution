from uuid import UUID

from dcs import Point
from dcs.mapping import LatLng
from fastapi import APIRouter, Body, Depends, HTTPException, status
from starlette.responses import Response

from game import Game
from game.theater.dynamicfarp import DynamicFarp, FarpKind
from game.theater.player import Player
from .models import ControlPointJs, FarpSiteCheckJs, NewFarpJs
from ..dependencies import GameContext, QtCallbacks, QtContext
from ..leaflet import LeafletPoint

router: APIRouter = APIRouter(prefix="/control-points")


@router.get(
    "/", operation_id="list_control_points", response_model=list[ControlPointJs]
)
def list_control_points(
    game: Game = Depends(GameContext.require),
) -> list[ControlPointJs]:
    return ControlPointJs.all_in_game(game)


def _parse_farp_kind(kind: str) -> FarpKind:
    try:
        return FarpKind(kind)
    except ValueError:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, detail=f"Unknown FARP kind: {kind}"
        )


@router.get(
    "/farp-site-check",
    operation_id="check_farp_site",
    response_model=FarpSiteCheckJs,
)
def check_farp_site(
    lat: float, lng: float, kind: str, game: Game = Depends(GameContext.require)
) -> FarpSiteCheckJs:
    point = Point.from_latlng(LatLng(lat, lng), game.theater.terrain)
    check = game.blue.farps.check_site(point, _parse_farp_kind(kind))
    return FarpSiteCheckJs(valid=check.valid, reasons=check.reasons, cost=check.cost)


@router.post(
    "/farps",
    operation_id="establish_farp",
    response_model=ControlPointJs,
)
def establish_farp(
    farp: NewFarpJs = Body(..., title="farp"),
    game: Game = Depends(GameContext.require),
    qt: QtCallbacks = Depends(QtContext.get),
) -> ControlPointJs:
    point = Point.from_latlng(
        LatLng(farp.position.lat, farp.position.lng), game.theater.terrain
    )
    kind = _parse_farp_kind(farp.kind)
    manager = game.blue.farps
    check = manager.check_site(point, kind)
    if not check.valid:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=" ".join(check.reasons))

    from .. import EventStream

    with EventStream.event_context() as events:
        cp = manager.establish(point, kind, events)
    qt.budget_changed()
    # The FARP's setup flight is a new package in the player's ATO.
    qt.ato_changed()
    if kind is FarpKind.RESCUE_KING:
        # Open its menu so the player can choose the helicopters.
        qt.show_control_point_info(cp)
    return ControlPointJs.for_control_point(cp)


@router.get(
    "/{cp_id}", operation_id="get_control_point_by_id", response_model=ControlPointJs
)
def get_control_point(
    cp_id: UUID, game: Game = Depends(GameContext.require)
) -> ControlPointJs:
    cp = game.theater.find_control_point_by_id(cp_id)
    if cp is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Game has no control point with ID {cp_id}",
        )
    return ControlPointJs.for_control_point(cp)


@router.get(
    "/{cp_id}/destination-in-range",
    operation_id="control_point_destination_in_range",
    response_model=bool,
)
def destination_in_range(
    cp_id: UUID, lat: float, lng: float, game: Game = Depends(GameContext.require)
) -> bool:
    cp = game.theater.find_control_point_by_id(cp_id)
    if cp is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Game has no control point with ID {cp_id}",
        )

    point = Point.from_latlng(LatLng(lat, lng), game.theater.terrain)
    return cp.destination_in_range(point)


@router.put(
    "/{cp_id}/destination",
    operation_id="set_control_point_destination",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def set_destination(
    cp_id: UUID,
    destination: LeafletPoint = Body(..., title="destination"),
    game: Game = Depends(GameContext.require),
) -> None:
    cp = game.theater.find_control_point_by_id(cp_id)
    if cp is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Game has no control point with ID {cp_id}",
        )
    if not cp.moveable:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"{cp} is not mobile")
    if not cp.captured.is_blue:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"{cp} is not owned by the player"
        )

    point = Point.from_latlng(
        LatLng(destination.lat, destination.lng), game.theater.terrain
    )
    if not cp.destination_in_range(point):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move {cp} more than "
            f"{cp.max_move_distance.nautical_miles}nm.",
        )
    if (
        cp.is_fleet
        and game.theater.landmap
        and game.theater.landmap.land_inbetween(cp.position, point)
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot move {cp} over land.",
        )
    cp.target_position = point
    from .. import EventStream

    with EventStream.event_context() as events:
        events.update_control_point(cp)


@router.put(
    "/{cp_id}/cancel-travel",
    operation_id="clear_control_point_destination",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def cancel_travel(cp_id: UUID, game: Game = Depends(GameContext.require)) -> None:
    cp = game.theater.find_control_point_by_id(cp_id)
    if cp is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Game has no control point with ID {cp_id}",
        )
    if not cp.moveable:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail=f"{cp} is not mobile")
    if not cp.captured.is_blue:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"{cp} is not owned by the player"
        )

    cp.target_position = None
    from .. import EventStream

    with EventStream.event_context() as events:
        events.update_control_point(cp)


@router.delete(
    "/{cp_id}/farp",
    operation_id="dismantle_farp",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def dismantle_farp(
    cp_id: UUID,
    game: Game = Depends(GameContext.require),
    qt: QtCallbacks = Depends(QtContext.get),
) -> None:
    try:
        cp = game.theater.find_control_point_by_id(cp_id)
    except KeyError:
        cp = None
    if not isinstance(cp, DynamicFarp):
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            detail=f"Game has no dynamic FARP with ID {cp_id}",
        )
    if not cp.captured.is_blue:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail=f"{cp} is not owned by the player"
        )
    from .. import EventStream

    with EventStream.event_context() as events:
        game.blue.farps.dismantle(cp, events)
    qt.budget_changed()
    # Dismantling removes the FARP's setup flight and flights using the FARP.
    qt.ato_changed()
