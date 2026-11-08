"""Campaign-level warfare systems: intelligence, morale, IADS health and doctrine.

See :class:`game.warfare.warstate.WarState`. Imports are lazy because this
package is used from low-level modules (planner tasks, the combat model) that
load before the rest of the game.
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .warstate import CombatCredit, IntelEvent, WarState

__all__ = ["CombatCredit", "IntelEvent", "WarState"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from . import warstate

        return getattr(warstate, name)
    raise AttributeError(name)
