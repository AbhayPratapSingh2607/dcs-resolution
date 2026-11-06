"""A weapon selector that opens a menu grouped like the DCS mission editor's.

The mission editor sorts a station's stores into category submenus (AA missiles,
fuel tanks, pods...), and gathers variants of the same store (the CJS Super
Hornet's "[ STA 05 | CHEEK | TGPMNT ] - 1x AN/ASQ-228 ATFLIR" and the stock
"AN/ASQ-228 ATFLIR") into a submenu of their own.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Optional

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QComboBox, QMenu, QWidget

from game.data.weapons import Weapon, WeaponType

AA_MISSILES = "AA Missiles"
AG_MISSILES = "AG Missiles"
GUIDED_BOMBS = "Guided Bombs"
BOMBS = "Bombs"
ROCKETS = "Rockets"
FUEL_TANKS = "Fuel Tanks"
PODS = "Pods"
OTHER = "Other"

#: Menu order, as in the mission editor.
CATEGORIES = [
    AA_MISSILES,
    AG_MISSILES,
    GUIDED_BOMBS,
    BOMBS,
    ROCKETS,
    FUEL_TANKS,
    PODS,
    OTHER,
]

#: Name patterns per category, tried in this order (first match wins).
_PATTERNS = [
    (FUEL_TANKS, r"\bFPU|FUEL|\bGAL\b|Tank\b|Drop Tank"),
    (AA_MISSILES, r"\bC?AIM-|CATM-(9|120)|Sidewinder|AMRAAM|Sparrow|Gunslinger"),
    (
        PODS,
        r"\bPod\b|\bALQ|\bAWW|\bASQ|\bAAQ|ATFLIR|LITENING|TCTS|Smoke|AA-?42R"
        r"|Refuel|WRA\b",
    ),
    (
        AG_MISSILES,
        r"\bC?AGM-|\bCATM-65|\bADM-|Maverick|HARM|Harpoon|SLAM|JSOW|TALD|Decoy",
    ),
    (GUIDED_BOMBS, r"\bGBU-|JDAM|Paveway|Walleye"),
    (ROCKETS, r"\bLAU-(10|61|68|131)\b|Zuni|Hydra|Rocket|FFAR|APKWS|\bRKT"),
    (BOMBS, r"\bMK-?\s?\d|\bCBU-|\bBDU-|Rockeye|Snakeye|Bomb"),
]

_TYPE_CATEGORIES = {
    WeaponType.TGP: PODS,
    WeaponType.JAMMER: PODS,
    WeaponType.OFFENSIVE_JAMMER: PODS,
    WeaponType.ARM: AG_MISSILES,
    WeaponType.DECOY: AG_MISSILES,
    WeaponType.LGB: GUIDED_BOMBS,
}


def display_name(weapon: Weapon) -> str:
    """The weapon's name without the tabs and padding some mods use to line it
    up in the mission editor."""
    return re.sub(r"\s+", " ", weapon.name).strip()


def store_name(weapon: Weapon) -> str:
    """The store itself, without a station/rack prefix or count: "[ STA 05 | CHEEK
    | TGPMNT ] - 1x AN/ASQ-228 ATFLIR - Targeting Pod" -> "AN/ASQ-228 ATFLIR -
    Targeting Pod"."""
    name = display_name(weapon)
    name = re.sub(r"^\[[^\]]*\]\s*-?\s*", "", name)
    name = re.sub(r"^\d+\s*x\s*", "", name, flags=re.I)
    return name.strip() or display_name(weapon)


def category(weapon: Weapon) -> str:
    """The mission editor-style category of the weapon."""
    known = _TYPE_CATEGORIES.get(weapon.weapon_group.type)
    if known is not None:
        return known
    name = store_name(weapon)
    for name_category, pattern in _PATTERNS:
        if re.search(pattern, name, flags=re.I):
            return name_category
    return OTHER


def _group_key(weapon: Weapon) -> str:
    """Stores that are variants of each other (same store, different rack or
    count) share a key."""
    name = store_name(weapon)
    # Drop parenthesised notes such as "(AI Only)" or "(Modern Missiles Mod
    # Required)" so they group with the plain store, and the " - " separators
    # mods use inconsistently ("Sparrow - Semi-Active" vs "Sparrow Semi-Active").
    name = re.sub(r"\s*[,(].*$", "", name)
    name = re.sub(r"\s+-\s+", " ", name)
    return re.sub(r"\s+", " ", name).strip().lower()


class CategorizedWeaponCombo(QComboBox):
    """A combo box of weapons whose popup is a categorised menu.

    Items are added with ``addItem(text, weapon)`` as usual; the item with
    ``None`` data is shown at the top of the menu.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._menu: Optional[QMenu] = None

    def select_data(self, data: object) -> bool:
        """Selects the item holding ``data``. Returns whether one was found."""
        for index in range(self.count()):
            if self.itemData(index) == data:
                self.setCurrentIndex(index)
                return True
        return False

    def showPopup(self) -> None:
        menu = QMenu(self)
        by_category: dict[str, list[int]] = defaultdict(list)
        for index in range(self.count()):
            weapon = self.itemData(index)
            if isinstance(weapon, Weapon):
                by_category[category(weapon)].append(index)
            else:
                self._add_action(menu, index)
        if by_category:
            menu.addSeparator()
        for name in CATEGORIES:
            indices = by_category.get(name)
            if not indices:
                continue
            submenu = menu.addMenu(f"{name} ({len(indices)})")
            groups: dict[str, list[int]] = defaultdict(list)
            for index in indices:
                groups[_group_key(self.itemData(index))].append(index)
            for _, group in sorted(groups.items()):
                if len(group) == 1:
                    self._add_action(submenu, group[0])
                    continue
                first = self.itemData(group[0])
                variants = submenu.addMenu(f"{store_name(first)} ({len(group)})")
                for index in sorted(group, key=self.itemText):
                    self._add_action(variants, index)
        self._menu = menu
        menu.aboutToHide.connect(self.hidePopup)
        menu.popup(self.mapToGlobal(self.rect().bottomLeft()))

    def hidePopup(self) -> None:
        self._menu = None
        super().hidePopup()

    def _add_action(self, menu: QMenu, index: int) -> QAction:
        action = menu.addAction(self.itemText(index))
        action.setCheckable(True)
        action.setChecked(index == self.currentIndex())
        action.triggered.connect(lambda _=False, i=index: self.setCurrentIndex(i))
        return action
