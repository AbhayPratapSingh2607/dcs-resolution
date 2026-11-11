"""Presets by location: pick one of the side's bases (ships first, then
airfields closest to farthest from the battle) and fill it from a preset made
for that kind of base. A carrier is offered carrier air wings, an LHA the
ARG's squadrons, an airfield near the battle the front-line groups and one
far from it the rear groups."""

from __future__ import annotations

import html
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.campaignloader.airwingpreset import (
    AirWingPreset,
    AirWingPresetLoader,
    BasePreset,
    BasePresetPlacer,
    PresetPlan,
    RankedBase,
    base_presets_for,
    ranked_bases,
)
from game.coalition import Coalition
from qt_ui.windows.AirWingPresetDialog import preset_plan_html


class BasePresetDialog(QDialog):
    def __init__(
        self,
        game: Game,
        coalition: Coalition,
        aircraft_present: bool,
        parent: Optional[QWidget] = None,
        presets: Optional[list[AirWingPreset]] = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.coalition = coalition
        self.aircraft_present = aircraft_present
        self.plan: Optional[PresetPlan] = None
        self.presets = (
            presets if presets is not None else AirWingPresetLoader.load_all()
        )

        side = "Blue" if coalition.player.is_blue else "Red"
        self.setWindowTitle(f"Presets by Base ({side})")
        self.setMinimumSize(1100, 640)

        layout = QVBoxLayout()
        self.setLayout(layout)
        intro = QLabel(
            "Pick a base, then a preset for it. Carriers and LHAs are offered the "
            "presets made for them. Airfields are ranked closest to farthest from "
            "the battle and split into front, middle and rear thirds; each third "
            "is offered the preset groups made for bases at that distance."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        body = QHBoxLayout()
        layout.addLayout(body, stretch=1)

        self.base_list = QListWidget()
        self.base_list.setMinimumWidth(360)
        body.addWidget(self.base_list, stretch=2)

        self.preset_list = QListWidget()
        self.preset_list.setMinimumWidth(340)
        self.preset_list.setWordWrap(True)
        body.addWidget(self.preset_list, stretch=2)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        body.addWidget(self.preview, stretch=3)

        self.replace_checkbox = QCheckBox("Replace the squadrons at this base")
        self.replace_checkbox.setChecked(True)
        self.replace_checkbox.setToolTip(
            "When unchecked, the preset's squadrons are added to the ones already "
            "based there. Squadrons at other bases are never touched."
        )
        layout.addWidget(self.replace_checkbox)
        self.add_missing_checkbox = QCheckBox("Add aircraft missing from the faction")
        layout.addWidget(self.add_missing_checkbox)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Close
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        for ranked in ranked_bases(game, coalition):
            count = sum(
                1
                for s in coalition.air_wing.iter_squadrons()
                if s.location is ranked.base
            )
            item = QListWidgetItem(
                ranked.label + (f" — {count} squadron(s)" if count else "")
            )
            item.setData(Qt.ItemDataRole.UserRole, ranked)
            self.base_list.addItem(item)

        self.base_list.currentItemChanged.connect(lambda *_: self.update_presets())
        self.preset_list.currentItemChanged.connect(lambda *_: self.update_preview())
        self.replace_checkbox.toggled.connect(lambda *_: self.update_preview())
        self.add_missing_checkbox.toggled.connect(lambda *_: self.update_preview())
        if self.base_list.count():
            self.base_list.setCurrentRow(0)
        self.update_presets()

    @property
    def replace_at_base(self) -> bool:
        return self.replace_checkbox.isChecked()

    @property
    def selected_base(self) -> Optional[RankedBase]:
        item = self.base_list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    @property
    def selected_preset(self) -> Optional[BasePreset]:
        item = self.preset_list.currentItem()
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def update_presets(self) -> None:
        self.preset_list.clear()
        ranked = self.selected_base
        if ranked is not None:
            for base_preset in base_presets_for(
                self.presets, ranked, self.game.date.year
            ):
                item = QListWidgetItem(base_preset.label)
                item.setData(Qt.ItemDataRole.UserRole, base_preset)
                self.preset_list.addItem(item)
            if self.preset_list.count():
                self.preset_list.setCurrentRow(0)
        self.update_preview()

    def update_preview(self) -> None:
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        ranked = self.selected_base
        base_preset = self.selected_preset
        if ranked is None or base_preset is None:
            self.plan = None
            apply_button.setEnabled(False)
            self.preview.setHtml(
                "No preset is made for this kind of base." if ranked is not None else ""
            )
            return
        self.plan = BasePresetPlacer(
            self.game,
            self.coalition,
            ranked.base,
            add_missing_aircraft=self.add_missing_checkbox.isChecked(),
            replace_at_base=self.replace_at_base,
        ).resolve(base_preset.as_preset())
        apply_button.setEnabled(bool(self.plan.placements))
        here = [
            s
            for s in self.coalition.air_wing.iter_squadrons()
            if s.location is ranked.base
        ]
        parts = [f"<p><b>{html.escape(ranked.label)}</b></p>"]
        if base_preset.preset.description:
            parts.append(f"<p><i>{html.escape(base_preset.preset.description)}</i></p>")
        if here:
            verb = "Replaces" if self.replace_at_base else "Joins"
            parts.append(
                f"<p>{verb}: "
                + html.escape(", ".join(f"{s.name} ({s.aircraft})" for s in here))
                + "</p>"
            )
        parts.append(preset_plan_html(self.plan, self.aircraft_present))
        self.preview.setHtml("".join(parts))
