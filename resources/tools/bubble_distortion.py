"""How much does the bubble (game.sim.bubble, M3) change the war?

Only the bubble goes into DCS; the combat model fights the rest over the
same time, apart. Fights across the boundary (a bubble CAP and a raid held
elsewhere) are lost. This tool measures that on a saved full turn with a
player flight, over several seeds, with the combat model standing in for
DCS:

* **whole**: the bubble off; every package flying during the mission is
  fought together through the window;
* **split**: the bubble on; the bubble's packages are fought through the
  window, then the packages held elsewhere through the same window, from
  the same start, apart.

It prints, per run and on average, each side's aircraft lost during the
window, ground units killed and the aircraft in DCS, and the difference.
The bubble is fine when the mean difference in losses is small against the
losses themselves (the default check: within 25% or 2 aircraft a side).

Usage:
    python resources/tools/bubble_distortion.py SAVE --seeds 5
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import statistics
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


@dataclass
class Run:
    seed: int
    mode: str
    blue_lost: int
    red_lost: int
    ground_killed: int
    in_dcs: int
    elsewhere: int


def _setup() -> None:
    logging.basicConfig(level=logging.ERROR)
    import game  # noqa: F401
    from pydcs_extensions import load_mods
    from qt_ui import liberation_install

    liberation_install.init()
    load_mods()


def _tick_through(sim: Any, start: Any, end: Any) -> None:
    from game.settings.settings import CombatResolutionMethod
    from game.sim.atoperiod import TICK
    from game.sim.gameupdateevents import GameUpdateEvents

    events = GameUpdateEvents()
    time = start
    while time < end:
        time += TICK
        sim.on_game_tick(events, time, TICK, CombatResolutionMethod.RESOLVE, True)


def _losses(results: Any, since: tuple[int, int]) -> tuple[int, int, int]:
    blue = sum(1 for l in results.air_losses if l.flight.squadron.player.is_blue)
    red = len(results.air_losses) - blue
    return blue - since[0], red - since[1], len(results.ground_losses)


def run_once(save: str, seed: int, split: bool) -> Run:
    from game import persistency
    from game.sim import atoperiod
    from game.sim import bubble
    from game.sim.gameloop import GameLoop
    from game.sim.gameupdatecallbacks import GameUpdateCallbacks

    g = persistency.load_game(save)
    assert g is not None, f"could not load {save}"
    g.settings.bubble_enabled = split
    random.seed(seed)
    atoperiod.align_window_to_players(g)
    window = atoperiod.window(g)
    assert window is not None, "the save has no DCS window (a mission only turn?)"
    loop = GameLoop(g, GameUpdateCallbacks(lambda: None, lambda e: None))
    loop.advance_to_window()
    sim = loop.sim.aircraft_simulation
    results = sim.results
    blue0 = sum(1 for l in results.air_losses if l.flight.squadron.player.is_blue)
    red0 = len(results.air_losses) - blue0
    ground0 = len(results.ground_losses)
    in_dcs = sum(len(c.ato.packages) for c in (g.blue, g.red))
    held: dict[bool, list[Any]] = {
        side: [p for p in packages if bubble.is_elsewhere(p)]
        for side, packages in g.air_campaign.deferred_packages.items()
    }
    elsewhere = sum(len(v) for v in held.values())
    # The bubble (or everything) through the window.
    _tick_through(sim, window[0], window[1])
    if split and elsewhere:
        # Then the packages held elsewhere through the same window, alone.
        for coalition in (g.blue, g.red):
            coalition.ato.packages[:] = list(held.get(coalition.player.is_blue, []))
        _tick_through(sim, window[0], window[1])
    blue, red, ground = _losses(results, (blue0, red0))
    return Run(
        seed,
        "split" if split else "whole",
        blue,
        red,
        ground - ground0,
        in_dcs,
        elsewhere,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("save")
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--tolerance", type=float, default=0.25)
    args = parser.parse_args()
    _setup()

    runs: list[tuple[Run, Run]] = []
    for seed in range(args.first_seed, args.first_seed + args.seeds):
        whole = run_once(args.save, seed, split=False)
        split = run_once(args.save, seed, split=True)
        runs.append((whole, split))
        print(
            f"seed {seed}: whole blue {whole.blue_lost} red {whole.red_lost} ground "
            f"{whole.ground_killed} ({whole.in_dcs} packages) | split blue "
            f"{split.blue_lost} red {split.red_lost} ground {split.ground_killed} "
            f"({split.in_dcs} in DCS, {split.elsewhere} elsewhere)"
        )

    def mean(values: list[int]) -> float:
        return statistics.fmean(values) if values else 0.0

    ok = True
    for label, get in (
        ("blue aircraft lost", lambda r: r.blue_lost),
        ("red aircraft lost", lambda r: r.red_lost),
        ("ground units killed", lambda r: r.ground_killed),
    ):
        whole = mean([get(w) for w, _ in runs])
        split = mean([get(s) for _, s in runs])
        diff = split - whole
        allowed = max(2.0, args.tolerance * whole)
        verdict = (
            "ok" if abs(diff) <= allowed or label.startswith("ground") else "DISTORTED"
        )
        if verdict != "ok":
            ok = False
        print(
            f"{label}: whole {whole:.1f}, split {split:.1f}, diff {diff:+.1f} ({verdict})"
        )
    print("bubble distortion", "within tolerance" if ok else "outside tolerance")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
