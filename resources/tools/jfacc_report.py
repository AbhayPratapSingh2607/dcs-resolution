"""Print what the air campaign (JFACC) planner tasked this turn, for both sides.

Usage:
    .venv/Scripts/python resources/tools/jfacc_report.py [--campaign black_sea]
        [--blue "USA 2020"] [--red "[CH] Russia 2020"] [--load save.retribution]
        [--turns 1]

Generates (or loads) a campaign, advances to the first planned turn and
prints, per side: the phase and intent, the MOEs, apportionment against
sorties planned, the packages on the timeline with their composition and
rationale, the top of the JIPTL and the packages that were scrubbed and why.
With --turns N > 1 the turns in between are fought by the combat model.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "resources" / "tools"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", default="black_sea")
    parser.add_argument("--blue", default="USA 2020")
    parser.add_argument("--red", default="[CH] Russia 2020")
    parser.add_argument("--date", default=None)
    parser.add_argument("--load", default=None)
    parser.add_argument("--turns", type=int, default=1)
    parser.add_argument("--jiptl", type=int, default=12, help="JIPTL lines shown")
    parser.add_argument("--quiet-packages", action="store_true")
    return parser.parse_args()


def describe_side(game: Any, coalition: Any, args: argparse.Namespace) -> None:
    side = game.air_campaign.maybe_side(coalition.player.is_blue)
    name = "BLUE" if coalition.player.is_blue else "RED"
    print(f"\n######## {name}: {coalition.faction.name}")
    if side is None or not side.history:
        print("  (legacy planner)")
        packages = coalition.ato.packages
        print(f"  {len(packages)} packages, {sum(len(p.flights) for p in packages)} flights")
        return
    print(f"  Phase: {side.phase.title} (since turn {side.phase_since_turn})")
    if side.history:
        last = side.history[-1]
        print(f"  Last change: turn {last.turn} -> {last.phase.value}: {last.reason}")
    print(f"  Intent: {side.intent}")
    moes = ", ".join(f"{k}={v:.2f}" for k, v in side.moes.items())
    print(f"  MOEs: {moes}")
    print(f"  Sorties available: {side.total_sorties}")
    for category, quota in side.apportioned.items():
        used = side.planned.get(category, 0)
        print(f"    {category.title:28} quota {quota:3}  planned {used:3}")
    start = game.conditions.start_time
    packages = sorted(coalition.ato.packages, key=lambda p: p.time_over_target)
    by_task: Counter[str] = Counter()
    total_aircraft = 0
    print(f"  Packages: {len(packages)}")
    for package in packages:
        offset = (package.time_over_target - start).total_seconds() / 60
        comp = ", ".join(f"{f.count}x{f.flight_type.value}" for f in package.flights)
        aircraft = sum(f.count for f in package.flights)
        total_aircraft += aircraft
        by_task[package.primary_task.value] += 1
        if not args.quiet_packages:
            print(f"    T+{offset:5.0f}m {package.target.name[:34]:34} [{comp}]")
            rationale = getattr(package, "planning_rationale", "")
            if rationale:
                print(f"             {rationale[:200]}")
    print(f"  Aircraft sorties: {total_aircraft}; by primary task: {dict(by_task)}")
    print(f"  JIPTL (top {args.jiptl} of {len(side.jiptl)}):")
    for line in side.jiptl[: args.jiptl]:
        mark = "*" if line.planned else " "
        print(
            f"   {mark}{line.rank:3} {line.name[:30]:30} {line.system.value:8} "
            f"{line.target_class:11} p={line.priority:.2f} conf={line.confidence:.2f} "
            f"assessed={line.assessed_effect:.0%}/{line.desired_effect:.0%} {line.status}"
        )
    reasons: Counter[str] = Counter(why.split(" (")[0] for _, why in side.scrubbed)
    print(f"  Scrubbed: {len(side.scrubbed)}")
    for why, count in reasons.most_common(8):
        print(f"    {count:3} x {why}")


def main() -> None:
    args = parse_args()
    import campaign_e2e

    campaign_e2e.setup()
    game = campaign_e2e.load_game(args.load) if args.load else campaign_e2e.new_game(args)
    if game.turn == 0:
        game.pass_turn(no_action=True)
    errors = campaign_e2e.ErrorCounter()
    import logging

    logging.getLogger().addHandler(errors)
    for _ in range(args.turns - 1):
        campaign_e2e.run_turn(game, errors, False)
    print(f"=== Turn {game.turn}, {game.conditions.start_time:%Y-%m-%d %H:%M} "
          f"({game.current_turn_time_of_day.value})")
    for coalition in (game.blue, game.red):
        describe_side(game, coalition, args)
    for record in errors.records:
        print(f"ERROR: {record.getMessage()[:300]}")


if __name__ == "__main__":
    main()
