"""Loadouts are listed by their payload's mission editor label."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from game.ato.loadouts import Loadout


def make_aircraft(payloads: dict[str, dict[str, Any]]) -> Any:
    aircraft = MagicMock()
    aircraft.dcs_unit_type.load_payloads.return_value = payloads
    return aircraft


def test_display_name_uses_the_payloads_label() -> None:
    aircraft = make_aircraft(
        {
            "AIM-9X*2, AIM-120C*2, FUEL*1": {
                "displayName": "- USN Adv. Extended Range CAP (AIM-9X*2, AIM-120C*2)"
            }
        }
    )

    assert (
        Loadout.display_name(aircraft, "AIM-9X*2, AIM-120C*2, FUEL*1")
        == "USN Adv. Extended Range CAP (AIM-9X*2, AIM-120C*2)"
    )


def test_display_name_falls_back_to_the_name() -> None:
    aircraft = make_aircraft({"Retribution CAS": {}, "Blank": {"displayName": " - "}})

    assert Loadout.display_name(aircraft, "Retribution CAS") == "Retribution CAS"
    assert Loadout.display_name(aircraft, "Blank") == "Blank"
    assert Loadout.display_name(aircraft, "Unknown") == "Unknown"
