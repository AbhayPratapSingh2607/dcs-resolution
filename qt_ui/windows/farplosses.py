"""Tells the player when one of their dynamic FARPs is lost at the end of a turn."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from PySide6.QtWidgets import QMessageBox, QWidget

from game import Game


def lost_farp_messages(
    game: Game, before: dict[str, str], infos_before: int
) -> list[str]:
    """Messages for the player FARPs in `before` (id -> name) that no longer exist,
    taken from the info panel entries added since `infos_before`."""
    remaining = {str(farp.id) for farp in game.blue.farps.farps}
    lost = [name for farp_id, name in before.items() if farp_id not in remaining]
    new_infos = game.informations[infos_before:]
    messages = []
    for name in lost:
        info = next((i for i in new_infos if i.title.startswith(f"{name} ")), None)
        messages.append(info.title if info is not None else f"{name} was lost")
    return messages


@contextmanager
def report_lost_farps(game: Optional[Game], parent: QWidget) -> Iterator[None]:
    """Shows a popup listing the player's FARPs lost while the block ran.

    Threatened FARPs are only reported in the info panel.
    """
    if game is None:
        yield
        return
    before = {str(farp.id): farp.name for farp in game.blue.farps.farps}
    infos_before = len(game.informations)
    yield
    messages = lost_farp_messages(game, before, infos_before)
    if not messages:
        return
    QMessageBox.warning(
        parent,
        "FARP lost" if len(messages) == 1 else "FARPs lost",
        "\n\n".join(f"{m}." if not m.endswith(".") else m for m in messages),
    )
