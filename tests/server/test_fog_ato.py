"""The enemy's ATO and air campaign plan follow the fog of war setting
(game/server/fogofwar.py)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from game.server.fogofwar import opfor_plan_visible
from game.settings.settings import FogOfWar


def _game(mode: FogOfWar, intel: bool = True) -> Any:
    return SimpleNamespace(
        settings=SimpleNamespace(fog_of_war=mode),
        war_state=SimpleNamespace(intel_enabled=lambda game: intel),
    )


@pytest.mark.parametrize(
    "mode,visible",
    [(FogOfWar.OFF, True), (FogOfWar.SOFT, False), (FogOfWar.STRICT, False)],
)
def test_opfor_plan_follows_fog_setting(mode: FogOfWar, visible: bool) -> None:
    assert opfor_plan_visible(_game(mode)) is visible


def test_opfor_plan_visible_without_intel() -> None:
    # The intel layer off means no fog of war at all.
    assert opfor_plan_visible(_game(FogOfWar.STRICT, intel=False))
    assert opfor_plan_visible(None)


def test_fog_and_intel_settings_reload_the_map() -> None:
    """Changing what the map may show must make the map reload everything
    (Settings sends the full game state again), or it keeps showing routes
    hidden and sites unconfirmed from before the change."""
    from game.settings.settings import Settings

    fields = {
        name: description
        for page in Settings.pages()
        for section in Settings.sections(page)
        for name, description in Settings.fields(page, section)
    }
    assert fields["fog_of_war"].causes_expensive_game_update
    assert fields["intel_enabled"].causes_expensive_game_update
