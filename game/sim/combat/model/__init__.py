"""Factor-based combat model used to auto-resolve combat while fast forwarding.

See the module docstrings of :mod:`.airtoair`, :mod:`.airdefense`,
:mod:`.attack` and :mod:`.groundbattle` for what each part simulates.
"""

from .engine import CombatModel

__all__ = ["CombatModel"]
