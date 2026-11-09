"""Air apportionment: how the period's sorties are split across mission types.

The phase gives a target share for each category, with a floor and a
ceiling. First every category is planned up to its share. Sorties a category
couldn't use (no targets, no suitable aircraft) then flow to the other
categories in the profile's overflow order, up to each category's ceiling.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .profile import Category, PhaseSpec, PlanningProfile


@dataclass
class Apportionment:
    total: int
    quota: dict[Category, int]
    ceiling: dict[Category, int]
    used: dict[Category, int] = field(default_factory=dict)
    overflow: bool = False

    @staticmethod
    def for_phase(
        profile: PlanningProfile, spec: PhaseSpec, total_sorties: int
    ) -> Apportionment:
        quota: dict[Category, int] = {}
        ceiling: dict[Category, int] = {}
        for category in Category:
            share = spec.apportionment.get(category)
            if share is None:
                quota[category] = 0
                ceiling[category] = 0
                continue
            target = min(max(share.share, share.min), share.max)
            quota[category] = round(total_sorties * target)
            ceiling[category] = round(total_sorties * share.max)
        return Apportionment(total_sorties, quota, ceiling)

    def used_by(self, category: Category) -> int:
        return self.used.get(category, 0)

    def remaining(self, category: Category) -> int:
        limit = self.ceiling[category] if self.overflow else self.quota[category]
        return max(0, limit - self.used_by(category))

    def total_used(self) -> int:
        return sum(self.used.values())

    def unused(self) -> int:
        return max(0, self.total - self.total_used())

    def can_afford(self, category: Category, sorties: int) -> bool:
        if self.overflow and self.unused() < sorties:
            return False
        # Allow a package to exceed the remaining quota by one element so
        # small quotas still produce a coherent package.
        return self.remaining(category) > 0 and sorties <= self.remaining(category) + 4

    def spend(self, category: Category, sorties: int) -> None:
        self.used[category] = self.used_by(category) + sorties

    def begin_overflow(self) -> None:
        self.overflow = True
