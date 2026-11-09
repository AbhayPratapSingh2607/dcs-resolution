"""Ground support layout: CAS lines over the FLOT and kill boxes beyond it.

* CAS: fronts with troops in contact get CAS lines. The main-effort front gets
  more lines than supporting fronts. The available CAS sorties are spread
  across the period as vulnerability windows, so troops have air cover all
  day instead of a single surge.
* Kill boxes: known enemy forces between the FLOT and the kill box depth are
  grouped into boxes of the profile's size. Each box with targets gets a kill
  box interdiction (KI) flight that searches the box and attacks what it finds.
  Deeper targets are left to air interdiction from the target list.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .targets import TargetNomination

if TYPE_CHECKING:
    from game.theater import FrontLine

NM = 1852.0


@dataclass
class KillBox:
    name: str
    front: FrontLine
    nominations: list[TargetNomination] = field(default_factory=list)

    @property
    def priority(self) -> float:
        return sum(n.priority for n in self.nominations)

    @property
    def lead(self) -> TargetNomination:
        return max(self.nominations, key=lambda n: n.priority)


def kill_boxes(
    nominations: list[TargetNomination],
    fronts: list[FrontLine],
    box_nm: float,
    max_depth_nm: float,
    max_boxes: int,
) -> list[KillBox]:
    """Group fielded-force nominations near the fronts into kill boxes."""
    from .profile import TargetSystem

    if not fronts:
        return []
    boxes: dict[tuple[str, int, int], KillBox] = {}
    for nomination in nominations:
        if nomination.system is not TargetSystem.FIELDED:
            continue
        if nomination.priority <= 0:
            continue
        target = nomination.target
        front = min(fronts, key=lambda f: f.position.distance_to_point(target.position))
        distance = front.position.distance_to_point(target.position)
        if distance > max_depth_nm * NM:
            continue
        # Grid aligned on the front's position.
        dx = (target.position.x - front.position.x) / (box_nm * NM)
        dy = (target.position.y - front.position.y) / (box_nm * NM)
        key = (front.name, math.floor(dx), math.floor(dy))
        box = boxes.get(key)
        if box is None:
            letter = chr(ord("A") + (len(boxes) % 26))
            box = KillBox(f"Kill box {letter}{len(boxes) // 26 + 1}", front)
            boxes[key] = box
        box.nominations.append(nomination)
    ranked = sorted(boxes.values(), key=lambda b: -b.priority)
    return ranked[:max_boxes]


def cas_lines(
    fronts_in_contact: list[FrontLine],
    main_effort: FrontLine | None,
    main_lines: int,
    supporting_lines: int,
) -> list[FrontLine]:
    """One entry per CAS line; the main effort appears more than once."""
    lines: list[FrontLine] = []
    for front in fronts_in_contact:
        count = main_lines if front is main_effort else supporting_lines
        lines.extend([front] * max(0, count))
    return lines
