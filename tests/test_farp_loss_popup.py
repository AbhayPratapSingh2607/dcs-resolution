"""The messages shown in the popup when the player loses a FARP."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from game.infos.information import Information
from qt_ui.windows.farplosses import lost_farp_messages


def make_game(farp_ids: list[str], infos: list[Information]) -> Any:
    farps = [SimpleNamespace(id=farp_id) for farp_id in farp_ids]
    return SimpleNamespace(
        blue=SimpleNamespace(farps=SimpleNamespace(farps=farps)),
        informations=infos,
    )


def test_lost_farps_use_their_info_panel_message() -> None:
    old = Information("FARP Anvil is threatened")
    infos = [
        old,
        Information("FARP Hammer is threatened"),
        Information("FARP Anvil lost: the front line moved past it"),
    ]
    game = make_game(["2"], infos)

    messages = lost_farp_messages(
        game, {"1": "FARP Anvil", "2": "FARP Hammer"}, infos_before=1
    )

    # Only the lost FARP is reported; a threatened one stays in the info panel.
    assert messages == ["FARP Anvil lost: the front line moved past it"]


def test_no_popup_when_no_farp_is_lost() -> None:
    game = make_game(["1"], [Information("FARP Anvil is threatened")])

    assert lost_farp_messages(game, {"1": "FARP Anvil"}, infos_before=0) == []
