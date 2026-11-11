"""DEAD needs weapons that hit a site with its radar off: anti-radiation
missiles alone make a SEAD flight, not a DEAD one. A Growler DEAD with only
HARMs against an SA-6 in Skynet's ambush got nothing to home on, dropped
its attack tasks and flew home."""

from __future__ import annotations

from game.commander.jfacc.weaponeering import Conditions, _loadout_ok

DAY = Conditions(night=False, low_cloud=False, visibility_km=20)
ALLOWED = ["gps", "laser", "unguided"]


def test_anti_radiation_alone_is_not_a_dead_loadout() -> None:
    assert not _loadout_ok({"anti_radiation"}, ALLOWED, DAY, kinetic=True)
    assert _loadout_ok({"anti_radiation", "gps"}, ALLOWED, DAY, kinetic=True)
    assert _loadout_ok({"gps"}, ALLOWED, DAY, kinetic=True)


def test_anti_radiation_still_counts_for_other_attacks() -> None:
    assert _loadout_ok({"anti_radiation"}, ALLOWED, DAY)
