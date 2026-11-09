"""Runs a campaign end to end without the UI, resolving every turn with the
fast-forward combat model.

Generates a new campaign (or loads a save), then for each turn: plans it,
fights the whole turn with the combat model, commits the results the same way
the app does (losses, CSAR, intel, morale), and passes the turn. Prints an
after-action report per turn and checks invariants:

* no errors are logged by game code while simulating or committing,
* no front line loses (almost) everything in one turn,
* no side loses an implausible share of the aircraft it flew,
* the game still saves (pickles) after every turn.

For sides planned by the doctrine-driven JFACC planner it also reports the
campaign phase, the sortie mix, package sizes and second sorties, and the
loss rate per sortie against the doctrine's attrition limit (a warning when
it runs far above it).

Exits with status 1 when a check fails.

Examples (from the repository root, with the project venv):

    .venv/Scripts/python resources/tools/campaign_e2e.py --turns 3
    .venv/Scripts/python resources/tools/campaign_e2e.py --campaign Caucasus_Multi_Georgia \\
        --blue "Bluefor Modern" --red "Russia 2010" --date 2010-06-01 --turns 5 --seed 7
    .venv/Scripts/python resources/tools/campaign_e2e.py --load "path/to/save.retribution" \\
        --turns 2 --save out.retribution --json report.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import pickle
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

#: A front this size or larger must not lose more than this share in a turn.
FRONT_MIN_SIZE = 10
FRONT_MAX_LOSS = 0.9
#: Share of the aircraft a side flew that it may lose in one turn.
AIR_MAX_LOSS = 0.35


class ErrorCounter(logging.Handler):
    """Counts errors logged by game code (not pydcs' payload parse noise)."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("pydcs"):
            return
        self.records.append(record)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--campaign", default="black_sea", help="campaign file stem")
    parser.add_argument("--blue", default="USA 2020")
    parser.add_argument("--red", default="[CH] Russia 2020")
    parser.add_argument("--date", default=None, help="start date, YYYY-MM-DD")
    parser.add_argument("--load", default=None, help="save game to start from")
    parser.add_argument("--turns", type=int, default=3)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--save", default=None, help="write the final game here")
    parser.add_argument("--json", default=None, help="write per-turn metrics here")
    parser.add_argument("--no-csar", action="store_true", help="turn CSAR off")
    parser.add_argument(
        "--verbose", action="store_true", help="also print the full combat log"
    )
    return parser.parse_args()


def setup() -> None:
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
    logging.getLogger("pydcs").setLevel(logging.CRITICAL)
    import game  # noqa: F401  (import order matters)
    from pydcs_extensions import load_mods
    from qt_ui import liberation_install

    if liberation_install.init():
        sys.exit("Run the app once first to configure the DCS folders.")
    load_mods()


def new_game(args: argparse.Namespace) -> Any:
    from qt_ui.main import create_game

    campaign = ROOT / "resources" / "campaigns" / f"{args.campaign}.yaml"
    if not campaign.exists():
        sys.exit(f"No campaign {campaign}")
    start = datetime.fromisoformat(args.date) if args.date else None
    if start is None:
        from game.campaignloader import Campaign

        start = Campaign.from_file(campaign).recommended_start_date or datetime(
            2005, 6, 1
        )
        if not isinstance(start, datetime):
            start = datetime(start.year, start.month, start.day)
    return create_game(
        campaign,
        args.blue,
        args.red,
        False,  # supercarrier
        True,  # auto procurement
        False,  # inverted
        False,  # cheats
        start,
        False,  # restrict weapons by date
        False,  # advanced IADS
        True,  # squadrons start full
    )


def load_game(path: str) -> Any:
    from game import persistency

    loaded = persistency.load_game(path)
    if loaded is None:
        sys.exit(f"Could not load {path}")
    return loaded


def front_sizes(game: Any) -> dict[str, tuple[int, int]]:
    sizes = {}
    for front in game.theater.conflicts():
        blue = game.ground_planners.get(front.blue_cp.id)
        red = game.ground_planners.get(front.red_cp.id)
        blue_n = sum(
            g.size for g in (blue.units_per_cp.get(front.red_cp.id, []) if blue else [])
        )
        red_n = sum(
            g.size for g in (red.units_per_cp.get(front.blue_cp.id, []) if red else [])
        )
        sizes[front.name] = (blue_n, red_n)
    return sizes


def aircraft_flown(game: Any) -> dict[bool, int]:
    flown = {True: 0, False: 0}
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            for flight in package.flights:
                flown[coalition.player.is_blue] += flight.count
    return flown


#: Warn when a JFACC side's loss rate runs this many times above its limit.
JFACC_LOSS_TOLERANCE = 3.0


def jfacc_plan_metrics(game: Any) -> dict[str, Any]:
    """What the JFACC planner tasked this turn, per side using it."""
    from collections import Counter

    metrics: dict[str, Any] = {}
    for coalition in (game.blue, game.red):
        side = game.air_campaign.maybe_side(coalition.player.is_blue)
        if side is None or not side.history:
            continue
        mix: Counter[str] = Counter()
        sizes: list[int] = []
        reused = 0
        risks: list[float] = []
        for package in coalition.ato.packages:
            n = sum(f.count for f in package.flights)
            sizes.append(n)
            for flight in package.flights:
                mix[flight.flight_type.value] += flight.count
                reused += getattr(flight, "reused_airframes", 0)
            risk = getattr(package, "planning_risk", None)
            if risk:
                risks.append(float(risk["estimate"]))
        metrics["blue" if coalition.player.is_blue else "red"] = {
            "phase": side.phase.value,
            "intent": side.intent,
            "sorties_available": side.total_sorties,
            "apportioned": {c.value: n for c, n in side.apportioned.items()},
            "planned": {c.value: n for c, n in side.planned.items()},
            "sortie_mix": dict(mix.most_common()),
            "packages": len(sizes),
            "mean_package_size": round(sum(sizes) / len(sizes), 1) if sizes else 0,
            "max_package_size": max(sizes, default=0),
            "second_sorties": reused,
            "mean_estimated_risk": round(sum(risks) / len(risks), 4) if risks else 0,
            "scrubbed": len(side.scrubbed),
            "modifiers": sorted(side.modifiers),
            "raids": list(side.raids),
            "enemy_sorties_seen": side.enemy_sorties_seen,
            "learned_axes": _learned_axes(game, coalition.player, side),
            "iads_moves": list(getattr(side, "iads_moves", [])),
            "qra": list(side.qra),
            "iads_orders": dict(
                __import__("collections").Counter(getattr(side, "iads_orders", {}).values())
            ),
        }
    return metrics


def _learned_axes(game: Any, player: Any, side: Any) -> list[str]:
    from game.commander.jfacc.observations import ObservationLog

    log = ObservationLog(side)
    result = []
    for cp in game.theater.control_points_for(player):
        for axis in log.axes(cp, max_axes=1):
            result.append(f"{cp.name} {axis.heading:03.0f} ({axis.mass:.0f})")
    return result


def jfacc_limit(game: Any, blue: bool) -> float:
    from game.commander.jfacc.planner import profile_for
    from game.theater.player import Player

    profile = profile_for(game, Player.BLUE if blue else Player.RED)
    if profile is None:
        return 0.0
    override = getattr(game.settings, "jfacc_attrition_limit_override", 0)
    return override / 100 if override else profile.attrition_limit


def run_turn(game: Any, errors: ErrorCounter, verbose: bool) -> dict[str, Any]:
    from game.settings.settings import FastForwardStopCondition
    from game.sim.aftaction import AfterActionReport
    from game.sim.gameloop import GameLoop
    from game.sim.gameupdatecallbacks import GameUpdateCallbacks
    from game.theater.player import Player

    turn = game.turn
    fronts_before = front_sizes(game)
    flown = aircraft_flown(game)
    owners_before = {cp.name: cp.captured.name for cp in game.theater.controlpoints}
    errors_before = len(errors.records)
    jfacc = jfacc_plan_metrics(game)
    jfacc_limits = {name: jfacc_limit(game, name == "blue") for name in jfacc}

    game.settings.fast_forward_stop_condition = FastForwardStopCondition.END_OF_TURN
    started = time.time()
    loop = GameLoop(game, GameUpdateCallbacks(lambda: None, lambda e: None))
    loop.run_to_first_contact()
    debriefing = loop.sim.debrief_simulated()
    simulated_s = time.time() - started
    # Ground alerts count as flown only when the GCI scrambled them.
    scrambles = {True: 0, False: 0}
    gci = getattr(loop.sim.aircraft_simulation, "gci", None)
    for _, blue, alert_flight, _ in getattr(gci, "scrambles", []):
        scrambles[blue] += 1
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            for f in package.flights:
                if getattr(f, "alert", False) and not getattr(f, "alert_released", False):
                    flown[coalition.player.is_blue] -= f.count
    for name, m in jfacc.items():
        m["scrambles"] = scrambles[name == "blue"]
    loop.complete_with_results(debriefing)
    report = AfterActionReport.from_debriefing(debriefing)
    game.pass_turn()

    failures: list[str] = []
    warnings: list[str] = []
    new_errors = errors.records[errors_before:]
    for record in new_errors:
        failures.append(f"error logged: {record.getMessage()[:200]}")

    front_losses = {}
    for name, (blue_n, red_n) in fronts_before.items():
        blue_lost = sum(
            n for base, n in report.blue.front_line_by_base.items() if base in name
        )
        red_lost = sum(
            n for base, n in report.red.front_line_by_base.items() if base in name
        )
        front_losses[name] = {
            "blue": [blue_lost, blue_n],
            "red": [red_lost, red_n],
        }
        for side, lost, size in (("blue", blue_lost, blue_n), ("red", red_lost, red_n)):
            if size >= FRONT_MIN_SIZE and lost > FRONT_MAX_LOSS * size:
                failures.append(f"{name}: {side} lost {lost} of {size} in one turn")

    for side, player in (("blue", Player.BLUE), ("red", Player.RED)):
        lost = debriefing.loss_counts(player).aircraft
        total = flown[player.is_blue]
        if total >= 8 and lost > AIR_MAX_LOSS * total:
            warnings.append(f"{side} lost {lost} of {total} aircraft flown")

    try:
        pickle.dumps(game)
    except Exception as ex:  # noqa: BLE001
        failures.append(f"game no longer pickles: {ex}")

    for name, metrics in jfacc.items():
        player = Player.BLUE if name == "blue" else Player.RED
        lost = debriefing.loss_counts(player).aircraft
        total = flown[player.is_blue]
        rate = lost / total if total else 0.0
        metrics["loss_rate"] = round(rate, 4)
        metrics["attrition_limit"] = jfacc_limits[name]
        limit = jfacc_limits[name]
        if total >= 8 and limit > 0 and rate > JFACC_LOSS_TOLERANCE * limit:
            warnings.append(
                f"{name} JFACC loss rate {rate:.1%} per sortie, "
                f"limit {limit:.1%}"
            )

    captured = [
        cp.name
        for cp in game.theater.controlpoints
        if owners_before.get(cp.name) != cp.captured.name
    ]

    print(f"\n=== Turn {turn} ({simulated_s:.0f}s to simulate) ===")
    print(f"Aircraft flown: blue {flown[True]}, red {flown[False]}")
    print(report.to_text())
    if captured:
        print("Bases changing hands:", ", ".join(captured))
    for name, losses in front_losses.items():
        b, r = losses["blue"], losses["red"]
        print(f"Front {name}: blue lost {b[0]}/{b[1]}, red lost {r[0]}/{r[1]}")
    for name, m in jfacc.items():
        print(
            f"JFACC {name}: {m['phase']}, {m['packages']} packages "
            f"(mean {m['mean_package_size']}, max {m['max_package_size']} aircraft), "
            f"{m['second_sorties']} second sorties, {m['scrubbed']} scrubbed, "
            f"est. risk {m['mean_estimated_risk']:.1%}, "
            f"actual {m['loss_rate']:.1%} (limit {m['attrition_limit']:.1%})"
        )
        print("  planned:", ", ".join(f"{k} {v}/{m['apportioned'].get(k, 0)}" for k, v in m["planned"].items()))
        print("  mix:", ", ".join(f"{v} {k}" for k, v in m["sortie_mix"].items()))
        if m["modifiers"] or m["raids"]:
            print(f"  modifiers: {', '.join(m['modifiers']) or '-'}; raids: {', '.join(m['raids']) or '-'}")
        if m.get("qra") or m.get("scrambles"):
            print(f"  ground alert: {len(m.get('qra', []))} pairs held, {m.get('scrambles', 0)} scrambled")
        if m["iads_moves"] or m["iads_orders"]:
            orders = ", ".join(f"{n} {o}" for o, n in m["iads_orders"].items()) or "-"
            print(f"  IADS: {orders}; moves: {'; '.join(m['iads_moves']) or '-'}")
        if m["learned_axes"]:
            print(
                f"  learned axes (saw {m['enemy_sorties_seen']} enemy aircraft): "
                + ", ".join(m["learned_axes"][:6])
            )
    if verbose:
        print("Combat log:")
        for entry in debriefing.simulation_log:
            print("  ", entry)
    for w in warnings:
        print("WARN", w)
    for f in failures:
        print("FAIL", f)

    return {
        "turn": turn,
        "simulated_seconds": round(simulated_s, 1),
        "aircraft_flown": {"blue": flown[True], "red": flown[False]},
        "aircraft_lost": {
            "blue": report.blue.aircraft_lost,
            "red": report.red.aircraft_lost,
        },
        "aircraft_by_cause": {
            "blue": dict(report.blue.aircraft_by_cause),
            "red": dict(report.red.aircraft_by_cause),
        },
        "crews": {"blue": dict(report.blue.crew), "red": dict(report.red.crew)},
        "fronts": front_losses,
        "jfacc": jfacc,
        "bases_captured": captured,
        "events": [f"{h}: {t}" for h, t in report.events],
        "warnings": warnings,
        "failures": failures,
    }


def main() -> int:
    args = parse_args()
    if args.seed is not None:
        random.seed(args.seed)
    setup()
    errors = ErrorCounter()
    logging.getLogger().addHandler(errors)

    started = time.time()
    game = load_game(args.load) if args.load else new_game(args)
    if args.no_csar:
        game.settings.csar_enabled = False
        game.settings.csar_enabled_red = False
    if game.turn == 0:
        game.pass_turn(no_action=True)
    print(
        f"{game.blue.faction.name} vs {game.red.faction.name} on "
        f"{game.theater.terrain.name}, turn {game.turn} "
        f"(ready in {time.time() - started:.0f}s)"
    )

    turns = []
    for _ in range(args.turns):
        turns.append(run_turn(game, errors, args.verbose))

    failed = sum(len(t["failures"]) for t in turns)
    warned = sum(len(t["warnings"]) for t in turns)
    print(f"\n{len(turns)} turns: {failed} failures, {warned} warnings")
    if args.save:
        from game import persistency

        game.savepath = str(Path(args.save).resolve())
        if persistency.save_game(game):
            print("Saved to", game.savepath, "(open it in the app to inspect)")
        else:
            failed += 1
            print("FAIL could not save the game")
    if args.json:
        Path(args.json).write_text(json.dumps(turns, indent=2, default=str))
        print("Metrics written to", args.json)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
