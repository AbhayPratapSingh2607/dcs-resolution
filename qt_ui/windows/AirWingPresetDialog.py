"""Dialog for picking an air wing preset and previewing where its squadrons go."""

from __future__ import annotations

import html
from collections import defaultdict
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
    PresetPlacer,
    PresetPlan,
)
from game.coalition import Coalition
from game.theater import ControlPoint


class AirWingPresetDialog(QDialog):
    def __init__(
        self,
        game: Game,
        coalition: Coalition,
        aircraft_present: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.game = game
        self.coalition = coalition
        self.aircraft_present = aircraft_present
        self.plan: Optional[PresetPlan] = None

        side = "Blue" if coalition.player.is_blue else "Red"
        self.setWindowTitle(f"Apply Air Wing Preset ({side})")
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout()
        self.setLayout(layout)

        intro = QLabel(
            "Pick a preset to build this side's air wing. Squadrons are placed on "
            "the carriers, LHAs and airfields this side owns. Presets made for this "
            f"side and closest to the campaign year ({game.date.year}) are listed "
            "first."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        body = QHBoxLayout()
        layout.addLayout(body, stretch=1)

        self.preset_list = QListWidget()
        self.preset_list.setMinimumWidth(280)
        body.addWidget(self.preset_list)

        right = QVBoxLayout()
        body.addLayout(right, stretch=1)
        self.description = QLabel()
        self.description.setWordWrap(True)
        right.addWidget(self.description)
        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        right.addWidget(self.preview, stretch=1)

        self.replace_checkbox = QCheckBox("Replace existing squadrons")
        self.replace_checkbox.setChecked(True)
        self.replace_checkbox.setToolTip(
            "When unchecked, the preset's squadrons are added to the current ones."
        )
        layout.addWidget(self.replace_checkbox)

        self.add_missing_checkbox = QCheckBox("Add aircraft missing from the faction")
        self.add_missing_checkbox.setToolTip(
            "Lets the preset use aircraft the faction doesn't normally have. Only "
            "this campaign's copy of the faction is changed."
        )
        layout.addWidget(self.add_missing_checkbox)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            self.accept
        )
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        def other_side(preset: AirWingPreset) -> bool:
            return preset.side is not None and preset.side.lower() != side.lower()

        # This side's presets first, then closest to the campaign year.
        presets = sorted(
            AirWingPresetLoader.load_all(),
            key=lambda p: (other_side(p), *p.sort_key(game.date.year)),
        )
        for preset in presets:
            label = preset.name
            if other_side(preset):
                label += f"  [{preset.side}]"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, preset)
            item.setToolTip(str(preset.path) if preset.path else "")
            self.preset_list.addItem(item)

        self.preset_list.currentItemChanged.connect(lambda *_: self.update_preview())
        self.replace_checkbox.toggled.connect(lambda *_: self.update_preview())
        self.add_missing_checkbox.toggled.connect(lambda *_: self.update_preview())
        if presets:
            self.preset_list.setCurrentRow(0)
        else:
            self.preview.setHtml(
                "No presets found in resources/airwing_presets or "
                "Saved Games/Retribution/AirWingPresets."
            )
        self.update_preview()

    @property
    def replace_existing(self) -> bool:
        return self.replace_checkbox.isChecked()

    @property
    def selected_preset(self) -> Optional[AirWingPreset]:
        item: Optional[QListWidgetItem] = self.preset_list.currentItem()
        if item is None:
            return None
        preset: AirWingPreset = item.data(Qt.ItemDataRole.UserRole)
        return preset

    def update_preview(self) -> None:
        preset = self.selected_preset
        apply_button = self.buttons.button(QDialogButtonBox.StandardButton.Apply)
        if preset is None:
            self.plan = None
            apply_button.setEnabled(False)
            return
        self.description.setText(
            f"<b>{html.escape(preset.name)}</b>"
            + (f" — era {preset.era}" if preset.era else "")
            + (f"<br/>{html.escape(preset.description)}" if preset.description else "")
        )
        self.plan = PresetPlacer(
            self.game,
            self.coalition,
            add_missing_aircraft=self.add_missing_checkbox.isChecked(),
            replace_existing=self.replace_existing,
        ).resolve(preset)
        apply_button.setEnabled(bool(self.plan.placements))
        self.preview.setHtml(self.preview_html(self.plan))

    def preview_html(self, plan: PresetPlan) -> str:
        by_base: dict[ControlPoint, list[str]] = defaultdict(list)
        for placed in plan.placements:
            config = placed.config
            details = [config.primary.value, f"size {config.max_size}"]
            if not self.aircraft_present:
                details.append(f"buy {config.aircraft_to_buy}")
            if config.country:
                details.append(config.country)
            name = config.squadron or config.name
            label = f"{placed.aircraft}" + (f" — {name}" if name else "")
            by_base[placed.base].append(
                f"{html.escape(label)} <i>({html.escape(', '.join(details))})</i>"
            )

        parts = []
        for base, lines in by_base.items():
            parts.append(f"<b>{html.escape(base.name)}</b><ul>")
            parts.extend(f"<li>{line}</li>" for line in lines)
            parts.append("</ul>")

        budget = self.coalition.budget
        if self.aircraft_present:
            parts.append(
                "<p>Squadrons start full, so aircraft are free and buy counts are "
                "ignored.</p>"
            )
        else:
            colour = "red" if plan.total_cost > budget else "inherit"
            parts.append(
                f"<p>Starting aircraft: {plan.total_aircraft}, cost "
                f"<span style='color:{colour}'>${plan.total_cost}M</span> of the "
                f"${budget:.0f}M starting budget.</p>"
            )
            if plan.total_cost > budget:
                parts.append(
                    "<p>Not enough money for every aircraft: purchases are spread "
                    "evenly over the squadrons until the money runs out.</p>"
                )

        if plan.missing_aircraft:
            names = ", ".join(sorted(str(a) for a in plan.missing_aircraft))
            parts.append(f"<p>Added to the faction: {html.escape(names)}</p>")
        if plan.warnings:
            parts.append("<p style='color:orange'><b>Warnings</b></p><ul>")
            parts.extend(
                f"<li style='color:orange'>{html.escape(w)}</li>" for w in plan.warnings
            )
            parts.append("</ul>")
        return "".join(parts)
