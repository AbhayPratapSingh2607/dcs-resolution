"""Runs campaign_e2e.py over several seeds and scenarios and checks the air
campaign planners against historical and competitive bands.

Each scenario is played for its number of turns from several seeds (the
fast-forward is random, so one run proves little), in parallel worker
processes. Per run it reads campaign_e2e's per-turn JSON; per scenario it
checks the band:

* ``iraq``, ``iran`` (Desert Storm-like, a client state against the US):
  blue's exchange ratio (red aircraft lost per blue aircraft lost) at least
  5, and red takes no base.
* ``peer`` (Russia 2010 against a 2005 US force): exchange ratio between
  0.5 and 2.5, and the front stays contested (neither side takes more than
  one base).
* ``red_wins`` (Russia against Georgia 2008): red takes a base within 6
  turns in at least 3 of 5 seeds.

Each run also reports where its fronts ended (``front_position`` in
campaign_e2e's JSON: 0 = at blue's base, 1 = at red's).

Usage:
    python resources/tools/campaign_matrix.py --scenarios iraq peer --seeds 5 \\
        --workers 2 --out %TEMP%/matrix
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[2]
E2E = ROOT / "resources" / "tools" / "campaign_e2e.py"


@dataclass
class Scenario:
    name: str
    blue: str
    red: str
    date: str
    turns: int
    band: str
    check: Callable[[list["RunResult"]], tuple[bool, str]]
    campaign: Optional[str] = None


@dataclass
class RunResult:
    scenario: str
    seed: int
    ok: bool
    turns: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""

    def lost(self, side: str) -> int:
        return sum(t["aircraft_lost"][side] for t in self.turns)

    def flown(self, side: str) -> int:
        return sum(t["aircraft_flown"][side] for t in self.turns)

    def bases_taken(self, side: str, within: Optional[int] = None) -> int:
        taken = 0
        for index, turn in enumerate(self.turns):
            if within is not None and index >= within:
                break
            taken += sum(1 for who in turn.get("bases_captured_by", {}).values() if who == side)
        return taken

    def front_positions(self) -> list[float]:
        """Each front's position after the last turn (0 = at blue's base)."""
        if not self.turns:
            return []
        return list(self.turns[-1].get("front_position", {}).values())

    @property
    def exchange_ratio(self) -> float:
        """Red aircraft lost per blue aircraft lost."""
        return self.lost("red") / max(1, self.lost("blue"))

    def scrambles(self, side: str) -> int:
        return sum(t["jfacc"].get(side, {}).get("scrambles", 0) for t in self.turns)

    def raids(self, side: str) -> int:
        return sum(len(t["jfacc"].get(side, {}).get("raids", [])) for t in self.turns)

    def moves(self, side: str) -> int:
        return sum(len(t["jfacc"].get(side, {}).get("iads_moves", [])) for t in self.turns)

    def phases(self, side: str) -> list[str]:
        result: list[str] = []
        for t in self.turns:
            phase = t["jfacc"].get(side, {}).get("phase")
            if phase and (not result or result[-1] != phase):
                result.append(phase)
        return result


def _completed(runs: list[RunResult]) -> list[RunResult]:
    return [r for r in runs if r.ok and r.turns]


def lopsided(runs: list[RunResult]) -> tuple[bool, str]:
    done = _completed(runs)
    if not done:
        return False, "no completed runs"
    ratios = [r.exchange_ratio for r in done]
    red_bases = sum(r.bases_taken("red") for r in done)
    ok = min(ratios) >= 5.0 and red_bases == 0
    return ok, (
        f"exchange ratio {min(ratios):.1f}-{max(ratios):.1f} (need >= 5), "
        f"red took {red_bases} bases (need 0)"
    )


def contested(runs: list[RunResult]) -> tuple[bool, str]:
    done = _completed(runs)
    if not done:
        return False, "no completed runs"
    ratios = sorted(r.exchange_ratio for r in done)
    median = ratios[len(ratios) // 2]
    worst_bases = max(max(r.bases_taken("blue"), r.bases_taken("red")) for r in done)
    ok = 0.5 <= median <= 2.5 and worst_bases <= 1
    return ok, (
        f"exchange ratio median {median:.2f} (range {ratios[0]:.2f}-{ratios[-1]:.2f}, "
        f"need 0.5-2.5), most bases taken by one side in a run {worst_bases} (need <= 1)"
    )


def red_can_win(runs: list[RunResult]) -> tuple[bool, str]:
    done = _completed(runs)
    if not done:
        return False, "no completed runs"
    wins = sum(1 for r in done if r.bases_taken("red", within=6) >= 1)
    need = max(1, round(0.6 * len(done)))
    return wins >= need, (
        f"red took a base within 6 turns in {wins} of {len(done)} runs (need {need})"
    )


SCENARIOS = {
    s.name: s
    for s in [
        Scenario("iraq", "USA 1990", "Iraq 1991", "1991-01-17", 8, "Desert Storm", lopsided),
        Scenario("iran", "USA 2005", "Iran 2015", "2015-06-01", 8, "client vs US", lopsided),
        Scenario("peer", "USA 2005", "Russia 2010", "2010-06-01", 8, "peer fight", contested),
        Scenario(
            "red_wins", "Georgia 2008", "Russia 2010", "2008-08-08", 6, "red can win", red_can_win
        ),
    ]
}


def run_one(scenario: Scenario, seed: int, out: Path) -> RunResult:
    stem = f"{scenario.name}_{seed}"
    json_path = out / f"{stem}.json"
    log_path = out / f"{stem}.log"
    command = [
        sys.executable,
        "-u",
        str(E2E),
        "--turns",
        str(scenario.turns),
        "--seed",
        str(seed),
        "--blue",
        scenario.blue,
        "--red",
        scenario.red,
        "--date",
        scenario.date,
        "--json",
        str(json_path),
    ]
    if scenario.campaign:
        command += ["--campaign", scenario.campaign]
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
    if not json_path.exists():
        return RunResult(scenario.name, seed, False, error=f"no metrics (exit {process.returncode}), see {log_path}")
    turns = json.loads(json_path.read_text(encoding="utf-8"))
    return RunResult(scenario.name, seed, True, turns)


def describe(run: RunResult) -> str:
    if not run.ok:
        return f"  seed {run.seed}: FAILED {run.error}"
    return (
        f"  seed {run.seed}: lost blue {run.lost('blue')}/{run.flown('blue')}, "
        f"red {run.lost('red')}/{run.flown('red')} (ratio {run.exchange_ratio:.2f}); "
        f"bases blue {run.bases_taken('blue')}, red {run.bases_taken('red')}; "
        f"red raids {run.raids('red')}, scrambles {run.scrambles('red')}, "
        f"SAM moves {run.moves('red')}; red phases {' > '.join(run.phases('red')) or '-'}; "
        f"fronts {', '.join(f'{p:.2f}' for p in run.front_positions()) or '-'}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenarios", nargs="+", default=list(SCENARIOS), choices=list(SCENARIOS))
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--first-seed", type=int, default=1)
    parser.add_argument("--turns", type=int, default=None, help="override every scenario's turns")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--out", default=str(ROOT / "matrix_out"))
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    jobs = []
    for name in args.scenarios:
        scenario = SCENARIOS[name]
        if args.turns is not None:
            scenario = Scenario(**{**scenario.__dict__, "turns": args.turns})
        for seed in range(args.first_seed, args.first_seed + args.seeds):
            jobs.append((scenario, seed))
    started = time.time()
    print(f"{len(jobs)} runs on {args.workers} workers, output in {out}")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda job: run_one(job[0], job[1], out), jobs))

    summary: dict[str, Any] = {}
    passed = 0
    for name in args.scenarios:
        scenario = SCENARIOS[name]
        runs = [r for r in results if r.scenario == name]
        ok, why = scenario.check(runs)
        passed += ok
        print(f"\n{'PASS' if ok else 'FAIL'} {name} ({scenario.band}): {why}")
        for run in runs:
            print(describe(run))
        summary[name] = {"pass": ok, "why": why, "runs": [describe(r) for r in runs]}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n{passed}/{len(args.scenarios)} scenarios in band ({(time.time() - started) / 60:.0f} min)")
    return 0 if passed == len(args.scenarios) else 1


if __name__ == "__main__":
    sys.exit(main())
