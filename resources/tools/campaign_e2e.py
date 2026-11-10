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
import re
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
    parser.add_argument(
        "--hash-seed",
        default="0",
        help="PYTHONHASHSEED to run under, so set iteration order (and the plan) "
        "repeats between runs; 'random' leaves it to Python",
    )
    parser.add_argument("--save", default=None, help="write the final game here")
    parser.add_argument("--json", default=None, help="write per-turn metrics here")
    parser.add_argument("--no-csar", action="store_true", help="turn CSAR off")
    parser.add_argument(
        "--turn-model",
        choices=["full", "mission-only"],
        default=None,
        help="'full': every turn is a 6 hour air war (settings: Mission only "
        "off); 'mission-only': each turn plans one mission plus a lead-in. "
        "Default: whatever the settings default is",
    )
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


def _near_misses(scrubbed: list[tuple[str, str]], count: int = 3) -> list[str]:
    """The attrition scrubs closest to their limit: what would fly next."""
    found = []
    for name, why in scrubbed:
        est = re.search(r"([\d.]+)% per sortie", str(why))
        limit = re.search(r"limit ([\d.]+)%", str(why))
        weight = re.search(r"SAM weight ([\d.]+)", str(why))
        if est and limit:
            ratio = float(est.group(1)) / max(float(limit.group(1)), 0.01)
            found.append(
                (
                    ratio,
                    f"{name} {est.group(1)}%/{limit.group(1)}%"
                    + (f" w{weight.group(1)}" if weight else ""),
                )
            )
    found.sort()
    return [text for _, text in found[:count]]


def push_metrics(side: Any, packages: list[Any]) -> dict[str, Any]:
    """The side's main push and how much of its offensive effort is in it."""
    from game.commander.jfacc.planner import is_offensive_package

    push = getattr(side, "push", None)
    offensive = [p for p in packages if is_offensive_package(p)]
    in_push = (
        [p for p in offensive if push[0] <= p.time_over_target < push[1]]
        if push
        else []
    )
    before = (
        [p for p in offensive if p.time_over_target < push[0]] if push else []
    )
    return {
        "start": push[0].isoformat() if push else None,
        "end": push[1].isoformat() if push else None,
        "offensive_packages": len(offensive),
        "in_push": len(in_push),
        "before_push": len(before),
        "share": round(len(in_push) / len(offensive), 2) if offensive else 0.0,
    }


def folded_rows(side: Any, packages: list[Any]) -> int:
    """Rows the ATO list shows with its folds closed (W4), from the Qt-free
    presentation helpers."""
    from qt_ui.atopresentation import folded_rows as rows

    return rows(packages, getattr(side, "push", None))


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
        estimated = 0
        for package in coalition.ato.packages:
            n = sum(f.count for f in package.flights)
            sizes.append(n)
            for flight in package.flights:
                mix[flight.flight_type.value] += flight.count
                reused += getattr(flight, "reused_airframes", 0)
            risk = getattr(package, "planning_risk", None)
            if risk:
                # Weighted by sorties, like the actual loss rate.
                risks.extend([float(risk["estimate"])] * n)
                estimated += 1
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
            "estimated_packages": estimated,
            "scrubbed": len(side.scrubbed),
            "near_misses": _near_misses(side.scrubbed),
            "scrub_reasons": dict(
                Counter(
                    re.sub(r"\(.*", "", re.sub(r"[\d.]+%?", "#", str(why))).strip()
                    for _, why in side.scrubbed
                ).most_common(6)
            ),
            "modifiers": sorted(side.modifiers),
            "raids": list(side.raids),
            "enemy_sorties_seen": side.enemy_sorties_seen,
            "learned_axes": _learned_axes(game, coalition.player, side),
            "iads_moves": list(getattr(side, "iads_moves", [])),
            "qra": list(side.qra),
            "push": push_metrics(side, list(coalition.ato.packages)),
            "list_rows_folded": folded_rows(side, list(coalition.ato.packages)),
            "iads_orders": dict(
                __import__("collections").Counter(
                    getattr(side, "iads_orders", {}).values()
                )
            ),
        }
    return metrics


def period_metrics(game: Any) -> dict[str, Any]:
    """The turn's ATO period and DCS window (game.sim.atoperiod), or {} for
    a legacy turn."""
    from game.sim import atoperiod

    bounds = atoperiod.period(game)
    if bounds is None:
        return {}
    window = atoperiod.window(game)
    return {
        "model": "mission-only" if atoperiod.is_focused(game) else "full",
        "start": bounds[0].isoformat(),
        "end": bounds[1].isoformat(),
        "hours": round((bounds[1] - bounds[0]).total_seconds() / 3600, 2),
        "window_start": window[0].isoformat() if window else None,
        "window_end": window[1].isoformat() if window else None,
    }


def blue_briefing(game: Any) -> str:
    """Blue's turn briefing as the DCS briefing shows it ("" without the
    air campaign planner)."""
    from game.commander.jfacc.briefing import turn_summary

    try:
        summary = turn_summary(game, blue=True)
    except Exception as ex:  # noqa: BLE001
        return f"(briefing failed: {ex})"
    return summary.as_text() if summary is not None else ""


def describe_period(info: dict[str, Any]) -> str:
    if not info:
        return ""
    start = datetime.fromisoformat(info["start"])
    end = datetime.fromisoformat(info["end"])
    text = f"Period ({info['model']}): {start:%H:%M}-{end:%H:%M} ({info['hours']} h)"
    if info.get("window_start"):
        ws = datetime.fromisoformat(info["window_start"])
        we = datetime.fromisoformat(info["window_end"])
        text += f"; DCS window {ws:%H:%M}-{we:%H:%M}"
    return text


def _learned_axes(game: Any, player: Any, side: Any) -> list[str]:
    from game.commander.jfacc.observations import ObservationLog

    log = ObservationLog(side)
    result = []
    for cp in game.theater.control_points_for(player):
        for axis in log.axes(cp, max_axes=1):
            result.append(f"{cp.name} {axis.heading:03.0f} ({axis.mass:.0f})")
    return result


def flights_by_task(game: Any) -> dict[bool, list[tuple[Any, str, int, float]]]:
    """(flight, task, aircraft, estimated loss rate) for every flight planned,
    before the turn is flown. Ground alerts are left out (they fly only if
    scrambled)."""
    result: dict[bool, list[tuple[Any, str, int, float]]] = {True: [], False: []}
    for coalition in (game.blue, game.red):
        for package in coalition.ato.packages:
            risk = getattr(package, "planning_risk", None) or {}
            estimate = float(risk.get("estimate", -1))
            for flight in package.flights:
                if getattr(flight, "alert", False):
                    continue
                task = flight.flight_type.value
                if getattr(flight, "returning", False):
                    task += " (returning)"
                result[coalition.player.is_blue].append(
                    (flight, task, flight.count, estimate)
                )
    return result


def losses_by_task(
    flights: list[tuple[Any, str, int, float]], debriefing: Any, blue: bool
) -> dict[str, dict[str, float]]:
    """Aircraft flown and lost per task, with the mean planning estimate of
    the packages they flew in (-1 when none had one)."""
    lost_by_flight: dict[int, int] = {}
    losses = debriefing.air_losses.player if blue else debriefing.air_losses.enemy
    for loss in losses:
        lost_by_flight[id(loss.flight)] = lost_by_flight.get(id(loss.flight), 0) + 1
    table: dict[str, dict[str, float]] = {}
    for flight, task, count, estimate in flights:
        row = table.setdefault(
            task, {"flown": 0, "lost": 0, "est_sum": 0.0, "est_n": 0}
        )
        row["flown"] += count
        row["lost"] += lost_by_flight.get(id(flight), 0)
        if estimate >= 0:
            row["est_sum"] += estimate * count
            row["est_n"] += count
    return {
        task: {
            "flown": row["flown"],
            "lost": row["lost"],
            "estimate": round(row["est_sum"] / row["est_n"], 4) if row["est_n"] else -1,
        }
        for task, row in sorted(table.items(), key=lambda kv: -kv[1]["flown"])
    }


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
    planned_flights = flights_by_task(game)
    owners_before = {cp.name: cp.captured.name for cp in game.theater.controlpoints}
    errors_before = len(errors.records)
    jfacc = jfacc_plan_metrics(game)
    jfacc_limits = {name: jfacc_limit(game, name == "blue") for name in jfacc}
    period_info = period_metrics(game)
    period_text = describe_period(period_info)
    briefing_text = blue_briefing(game)

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
                if getattr(f, "alert", False) and not getattr(
                    f, "alert_released", False
                ):
                    flown[coalition.player.is_blue] -= f.count
    for name, m in jfacc.items():
        m["scrambles"] = scrambles[name == "blue"]
        m["by_task"] = losses_by_task(
            planned_flights[name == "blue"], debriefing, name == "blue"
        )
    loop.complete_with_results(debriefing)
    # Where each front stands once the turn's results are committed
    # (before the next turn's strength recovery): blue's share of the two bases'
    # strength (1 = pushed to red's base, 0 = pushed to blue's base).
    front_position = {}
    for front in game.theater.conflicts():
        blue_s, red_s = front.blue_cp.base.strength, front.red_cp.base.strength
        front_position[front.name] = (
            round(blue_s / (blue_s + red_s), 3) if blue_s + red_s else 0.5
        )
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
                f"{name} JFACC loss rate {rate:.1%} per sortie, " f"limit {limit:.1%}"
            )

    captured = [
        cp.name
        for cp in game.theater.controlpoints
        if owners_before.get(cp.name) != cp.captured.name
    ]

    print(f"\n=== Turn {turn} ({simulated_s:.0f}s to simulate) ===")
    if period_text:
        print(period_text)
    if briefing_text:
        print("Briefing:")
        for line in briefing_text.splitlines():
            print("  " + line)
    print(f"Aircraft flown: blue {flown[True]}, red {flown[False]}")
    print(report.to_text())
    if captured:
        print("Bases changing hands:", ", ".join(captured))
    for name, position in front_position.items():
        print(
            f"Front {name} position: {position:.2f} (0 = at blue's base, 1 = at red's)"
        )
    for name, losses in front_losses.items():
        b, r = losses["blue"], losses["red"]
        print(f"Front {name}: blue lost {b[0]}/{b[1]}, red lost {r[0]}/{r[1]}")
    for name, m in jfacc.items():
        print(
            f"JFACC {name}: {m['phase']}, {m['packages']} packages "
            f"(mean {m['mean_package_size']}, max {m['max_package_size']} aircraft), "
            f"{m['second_sorties']} second sorties, {m['scrubbed']} scrubbed, "
            f"est. risk {m['mean_estimated_risk']:.1%} "
            f"({m.get('estimated_packages', 0)}/{m['packages']} packages estimated), "
            f"actual {m['loss_rate']:.1%} (limit {m['attrition_limit']:.1%})"
        )
        print(
            "  planned:",
            ", ".join(
                f"{k} {v}/{m['apportioned'].get(k, 0)}" for k, v in m["planned"].items()
            ),
        )
        print("  mix:", ", ".join(f"{v} {k}" for k, v in m["sortie_mix"].items()))
        by_task = m.get("by_task") or {}
        if by_task:
            print(
                "  lost by task:",
                ", ".join(
                    f"{task} {int(r['lost'])}/{int(r['flown'])}"
                    + (f" (est {r['estimate']:.1%})" if r["estimate"] >= 0 else "")
                    for task, r in by_task.items()
                ),
            )
        if m.get("scrub_reasons"):
            print(
                "  scrubbed for:",
                "; ".join(f"{n}x {why}" for why, n in m["scrub_reasons"].items()),
            )
        if m.get("near_misses"):
            print("  closest to flying:", ", ".join(m["near_misses"]))
        if m["modifiers"] or m["raids"]:
            print(
                f"  modifiers: {', '.join(m['modifiers']) or '-'}; raids: {', '.join(m['raids']) or '-'}"
            )
        if m.get("qra") or m.get("scrambles"):
            print(
                f"  ground alert: {len(m.get('qra', []))} pairs held, {m.get('scrambles', 0)} scrambled"
            )
        if m.get("list_rows_folded") is not None:
            print(f"  ATO list: {m['list_rows_folded']} rows folded, {m['packages']} open")
        push = m.get("push") or {}
        if push.get("start"):
            ps = datetime.fromisoformat(push["start"])
            pe = datetime.fromisoformat(push["end"])
            print(
                f"  main push {ps:%H:%M}-{pe:%H:%M}: {push['in_push']}/"
                f"{push['offensive_packages']} offensive packages in it "
                f"({push['share']:.0%}), {push['before_push']} before it"
            )
        elif push:
            print(
                f"  no main push: {push['offensive_packages']} offensive packages "
                "spread over the period"
            )
        if m["iads_moves"] or m["iads_orders"]:
            orders = ", ".join(f"{n} {o}" for o, n in m["iads_orders"].items()) or "-"
            print(f"  IADS: {orders}; moves: {'; '.join(m['iads_moves']) or '-'}")
        if m["learned_axes"]:
            print(
                f"  learned axes (saw {m['enemy_sorties_seen']} enemy aircraft): "
                + ", ".join(m["learned_axes"][:6])
            )
    pushes = {
        name: m.get("push") or {} for name, m in jfacc.items() if m.get("push", {}).get("start")
    }
    if len(pushes) == 2:
        b, r = pushes["blue"], pushes["red"]
        overlap = min(
            datetime.fromisoformat(b["end"]), datetime.fromisoformat(r["end"])
        ) - max(datetime.fromisoformat(b["start"]), datetime.fromisoformat(r["start"]))
        minutes = int(overlap.total_seconds() // 60)
        print(
            "Main pushes overlap by "
            + (f"{minutes} minutes" if minutes > 0 else "nothing")
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
        "period": period_info,
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
        "front_position": front_position,
        "bases_captured_by": {
            cp.name: ("blue" if cp.captured.is_blue else "red")
            for cp in game.theater.controlpoints
            if cp.name in captured
        },
        "events": [f"{h}: {t}" for h, t in report.events],
        "warnings": warnings,
        "failures": failures,
    }


def main() -> int:
    # Target names can be non-ASCII; a redirected Windows console is cp1252.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = parse_args()
    if args.hash_seed != "random" and os.environ.get("PYTHONHASHSEED") != args.hash_seed:
        # String hashing is randomized per process, which changes set order
        # and with it the plan. Re-run with a fixed seed so runs repeat.
        import subprocess

        env = dict(os.environ, PYTHONHASHSEED=args.hash_seed)
        return subprocess.call([sys.executable, *sys.argv], env=env)
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
    if args.turn_model is not None:
        game.settings.focused_turns = args.turn_model == "mission-only"
    print(
        "Turn model:",
        "mission only" if game.settings.focused_turns else "full 6 hour turn",
    )
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
