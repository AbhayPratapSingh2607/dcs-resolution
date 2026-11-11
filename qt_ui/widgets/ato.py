"""Widgets for displaying air tasking orders."""

import logging
from copy import deepcopy
from typing import Optional

from PySide6.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QSize,
    Qt,
)
from PySide6.QtGui import (
    QContextMenuEvent,
    QAction,
    QKeyEvent,
)
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListView,
    QMenu,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QMessageBox,
    QCheckBox,
    QTabWidget,
    QTextBrowser,
    QWidget,
)

from game.ato.flight import Flight
from game.ato.package import Package
from game.server import EventStream
from game.sim import GameUpdateEvents
from .QLabeledWidget import QLabeledWidget
from .atorows import AtoGroupProxy, FlightRowDelegate, PackageRowDelegate
from .. import atopresentation as ap
from ..windows.atotimeline import AtoTimelineDialog
from ..models import AtoModel, GameModel, NullListModel, PackageModel

#: Shown above the package list before the campaign begins.
PRE_WAR_NOTE = (
    "Pre-war posture: this plan is never flown. Begin Campaign plans turn 1, "
    "when hostilities start."
)


class QFlightList(QListView):
    """List view for displaying the flights of a package."""

    def __init__(
        self, game_model: GameModel, package_model: Optional[PackageModel]
    ) -> None:
        super().__init__()
        self.game_model = game_model
        self.package_model = package_model
        self.set_package(package_model)
        if package_model is not None:
            self.setItemDelegate(FlightRowDelegate(package_model.package))
        self.setIconSize(QSize(91, 24))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.doubleClicked.connect(self.on_double_click)

    def set_package(self, model: Optional[PackageModel]) -> None:
        """Sets the package model to display."""
        if model is None:
            self.disconnect_model()
        else:
            self.package_model = model
            self.setItemDelegate(FlightRowDelegate(model.package))
            self.setModel(model)
            # noinspection PyUnresolvedReferences
            model.deleted.connect(self.disconnect_model)
            self.selectionModel().setCurrentIndex(
                model.index(0, 0, QModelIndex()),
                QItemSelectionModel.SelectionFlag.Select,
            )

    def disconnect_model(self) -> None:
        """Clears the listview of any model attachments.

        Displays an empty list until set_package is called with a valid model.
        """
        model = self.model()
        if model is not None and isinstance(model, PackageModel):
            model.deleted.disconnect(self.disconnect_model)
        self.setModel(NullListModel())

    @property
    def selected_item(self) -> Optional[Flight]:
        """Returns the selected flight, if any."""
        index = self.currentIndex()
        if not index.isValid():
            return None
        return self.package_model.flight_at_index(index)

    def on_double_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.edit_flight(index)

    def edit_flight(self, index: QModelIndex) -> None:
        from qt_ui.dialogs import Dialog

        Dialog.open_edit_flight_dialog(
            self.package_model,
            self.package_model.flight_at_index(index),
            parent=self.window(),
        )

    def clone_flight(self, index: QModelIndex) -> None:
        flight = self.package_model.flight_at_index(index)
        try:
            clone = Flight.clone_flight(flight)
        except ValueError as ve:
            QMessageBox.critical(
                None,
                "Can't clone flight!",
                f"Insufficient aircraft to clone flight:\n\n{ve}",
            )
            return
        self.package_model.add_flight(clone)
        clone.flight_plan.layout = deepcopy(flight.flight_plan.layout)
        EventStream.put_nowait(GameUpdateEvents().new_flight(clone))

    def cancel_or_abort_flight(self, index: QModelIndex) -> None:
        self.package_model.cancel_or_abort_flight_at_index(index)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.indexAt(event.pos())

        menu = QMenu("Menu")

        edit_action = QAction("Edit")
        edit_action.triggered.connect(lambda: self.edit_flight(index))
        menu.addAction(edit_action)

        delete_action = QAction(f"Delete")
        delete_action.triggered.connect(lambda: self.cancel_or_abort_flight(index))
        menu.addAction(delete_action)

        menu.exec_(event.globalPos())


class QFlightPanel(QGroupBox):
    """The flight display portion of the ATO panel.

    Displays the flights assigned to the selected package, and includes edit and
    delete buttons for flight management.
    """

    def __init__(
        self, game_model: GameModel, package_model: Optional[PackageModel] = None
    ) -> None:
        super().__init__("Flights")
        self.game_model = game_model
        self.package_model = package_model

        self.vbox = QVBoxLayout()
        self.setLayout(self.vbox)

        self.tip = QLabel("Double-click a flight to edit it.")
        self.tip.setProperty("style", "small")
        self.tip.setToolTip(
            "To add flights to a package, edit the package by double clicking "
            "it or pressing the edit button."
        )
        self.vbox.addWidget(self.tip)

        self.flight_list = QFlightList(game_model, package_model)
        self.vbox.addWidget(self.flight_list)

        self.button_row = QHBoxLayout()
        self.vbox.addLayout(self.button_row)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.on_edit)
        self.button_row.addWidget(self.edit_button)

        self.clone_button = QPushButton("Clone")
        self.clone_button.setProperty("style", "btn-success")
        self.clone_button.clicked.connect(self.on_clone)
        self.button_row.addWidget(self.clone_button)

        self.delete_button = QPushButton("Cancel")
        self.delete_button.setProperty("style", "btn-danger")
        self.delete_button.clicked.connect(self.on_cancel_flight)
        self.button_row.addWidget(self.delete_button)

        self.selection_changed.connect(self.on_selection_changed)
        self.on_selection_changed()

    def set_package(self, model: Optional[PackageModel]) -> None:
        """Sets the package model to display."""
        self.package_model = model
        self.flight_list.set_package(model)
        self.selection_changed.connect(self.on_selection_changed)
        self.on_selection_changed()

    @property
    def selection_changed(self):
        """Returns the signal emitted when the flight selection changes."""
        return self.flight_list.selectionModel().selectionChanged

    def on_selection_changed(self) -> None:
        """Updates the status of the edit and delete buttons."""
        index = self.flight_list.currentIndex()
        enabled = index.isValid()
        self.edit_button.setEnabled(enabled)
        self.clone_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.change_map_flight_selection(index)
        delete_text = "Cancel"
        if (flight := self.flight_list.selected_item) is not None:
            if not flight.state.cancelable:
                delete_text = "Abort"
        self.delete_button.setText(delete_text)

    def change_map_flight_selection(self, index: QModelIndex) -> None:
        events = GameUpdateEvents()
        if not index.isValid():
            events.deselect_flight()
        else:
            events.select_flight(self.package_model.flight_at_index(index))
        EventStream.put_nowait(events)

    def on_edit(self) -> None:
        """Opens the flight edit dialog."""
        index = self.flight_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot edit flight when no flight is selected.")
            return
        self.flight_list.edit_flight(index)

    def on_clone(self) -> None:
        index = self.flight_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot clone flight when no flight is selected.")
            return
        self.flight_list.clone_flight(index)

    def on_cancel_flight(self) -> None:
        """Removes the selected flight from the package."""
        index = self.flight_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot delete flight when no flight is selected.")
            return
        self.flight_list.cancel_or_abort_flight(index)


class QPackageList(QListView):
    """List view for displaying the packages of an ATO.

    Shows the ATO through an AtoGroupProxy: grouped by mission category, in
    TOT order, with collapsed categories hidden. Indices of the view are proxy
    indices; AtoModel calls take source indices (see source()).
    """

    def __init__(self, game_model: GameModel, model: AtoModel) -> None:
        super().__init__()
        self.ato_model = model
        self.proxy = AtoGroupProxy()
        self.proxy.setSourceModel(model)
        self.proxy.sort(0)
        self.setModel(self.proxy)
        self.row_delegate = PackageRowDelegate(game_model)
        self.setItemDelegate(self.row_delegate)
        self.setIconSize(QSize(0, 0))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setMouseTracking(True)
        self.model().rowsInserted.connect(self.on_new_packages)
        self.doubleClicked.connect(self.on_double_click)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # A click on a row's fold badge opens or closes the fold.
        index = self.indexAt(event.pos())
        if index.isValid() and event.button() == Qt.MouseButton.LeftButton:
            package = self.ato_model.package_at_index(self.source(index))
            badge = self.row_delegate.fold_badges.get(id(package))
            fold = self.proxy.fold_of(package)
            if badge is not None and fold is not None and badge.contains(event.pos()):
                self.proxy.toggle_fold(fold)
                event.accept()
                return
        super().mousePressEvent(event)

    def set_ato_model(self, model: AtoModel) -> None:
        self.ato_model = model
        self.proxy.setSourceModel(model)
        self.proxy.sort(0)

    def source(self, index: QModelIndex) -> QModelIndex:
        if index.model() is self.proxy:
            return self.proxy.mapToSource(index)
        return index

    def view_index(self, package: Package) -> QModelIndex:
        """The view index of a package, unhiding its group if needed."""
        packages = list(self.ato_model.ato.packages)
        if package not in packages:
            return QModelIndex()
        key = ap.package_group(package).key
        if key in self.proxy.hidden:
            self.proxy.set_hidden(key, False)
        self.proxy.open_fold_for(package)
        return self.proxy.mapFromSource(
            self.ato_model.index(packages.index(package), 0)
        )

    def select_package(self, package: Package) -> None:
        index = self.view_index(package)
        if index.isValid():
            self.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect
            )
            self.scrollTo(index)

    @property
    def selected_item(self) -> Optional[Package]:
        """Returns the selected package, if any."""
        index = self.currentIndex()
        if not index.isValid():
            return None
        return self.ato_model.package_at_index(self.source(index))

    def edit_package(self, index: QModelIndex) -> None:
        from qt_ui.dialogs import Dialog

        Dialog.open_edit_package_dialog(
            self.ato_model.get_package_model(self.source(index))
        )

    def clone_package(self, index: QModelIndex) -> None:
        package_model = self.ato_model.get_package_model(self.source(index))
        try:
            clone = Package.clone_package(package_model.package)
        except ValueError as ve:
            QMessageBox.critical(
                None,
                "Can't clone package!",
                f"Insufficient aircraft to clone package:\n\n{ve}",
            )
            return
        self.ato_model.add_package(clone)
        events = GameUpdateEvents()
        for f in clone.flights:
            events.new_flight(f)
        EventStream.put_nowait(events)

    def delete_package(self, index: QModelIndex) -> None:
        self.ato_model.cancel_or_abort_package_at_index(self.source(index))

    def on_new_packages(self, _parent: QModelIndex, first: int, _last: int) -> None:
        # Select the newly created pacakges. This should only ever happen due to
        # the player saving a new package, so selecting it helps them view/edit
        # it faster.
        self.selectionModel().setCurrentIndex(
            self.model().index(first, 0), QItemSelectionModel.SelectionFlag.Select
        )

    def on_double_click(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        self.edit_package(index)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        index = self.indexAt(event.pos())
        if not index.isValid():
            return

        menu = QMenu("Menu")

        edit_action = QAction("Edit")
        edit_action.triggered.connect(lambda: self.edit_package(index))
        menu.addAction(edit_action)

        delete_action = QAction(f"Delete")
        delete_action.triggered.connect(lambda: self.delete_package(index))
        menu.addAction(delete_action)

        package = self.ato_model.package_at_index(self.source(index))
        pin_action = QAction("Keep in my mission")
        pin_action.setCheckable(True)
        pin_action.setChecked(bool(getattr(package, "pinned", False)))
        pin_action.setToolTip(
            "A pinned package is always in the DCS mission, whatever is left out "
            "around your flight."
        )
        pin_action.toggled.connect(lambda on: self.set_pinned(package, on))
        menu.addAction(pin_action)

        flights = [f for f in package.flights if f.unit_type.flyable]
        if flights:
            take_action = QAction("Take this flight")
            take_action.setToolTip("Put yourself in this package's first flight")
            take_action.triggered.connect(lambda: self.take_flight(flights[0]))
            menu.addAction(take_action)

        menu.exec_(event.globalPos())

    def set_pinned(self, package: Package, pinned: bool) -> None:
        package.pinned = pinned
        self.viewport().update()

    def take_flight(self, flight: Flight) -> None:
        from game.commander.jfacc.seat import frag
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        game = self.ato_model.game
        if game is None:
            return
        if not frag(game, flight):
            QMessageBox.warning(
                self, "No pilot", "That flight has no pilot to give you."
            )
            return
        EventStream.put_nowait(GameUpdateEvents().update_flight(flight))
        GameUpdateSignal.get_instance().updateGame(game)
        self.select_package(flight.package)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # Delete/Supr cancels (deletes) the selected package, so several can be
        # cleared in a row without reaching for the context menu each time.
        if event.key() == Qt.Key.Key_Delete:
            index = self.currentIndex()
            if index.isValid():
                row = index.row()
                self.delete_package(index)
                # Keep a package selected so repeated Delete clears consecutive
                # packages: the same row now holds the next one (clamped to the
                # new last row). If the package wasn't removed (its flights were
                # only aborted, not cancelled), this re-selects it harmlessly.
                remaining = self.model().rowCount()
                if remaining:
                    self.setCurrentIndex(self.model().index(min(row, remaining - 1), 0))
                event.accept()
                return
        super().keyPressEvent(event)


class QPackagePanel(QGroupBox):
    """The package display portion of the ATO panel.

    Displays the package assigned to the player's ATO, and includes edit and
    delete buttons for package management.
    """

    def __init__(self, game_model: GameModel, ato_model: AtoModel) -> None:
        super().__init__("Packages")
        self.ato_model = ato_model
        self.ato_model.layoutChanged.connect(self.on_current_changed)

        self.vbox = QVBoxLayout()
        self.setLayout(self.vbox)

        self.tip = QLabel("Right-click a target on the map to plan a package.")
        self.tip.setProperty("style", "small")
        self.tip.setToolTip(
            "To create a new package, right click the mission target on the "
            "map. To target airbase objectives, use the attack button in the "
            "airbase view.\n\nPackages are grouped by mission category and "
            "sorted by TOT. Click a category chip to hide or show its packages. "
            "Routine lines and the waves outside the main push are folded to "
            "one row each: click a row's badge to open it, or the Fold chip to "
            "show everything. Hover a package for its purpose, risk and flight "
            "times."
        )
        self.vbox.addWidget(self.tip)

        self.chip_grid = QGridLayout()
        self.chip_grid.setSpacing(3)
        self.chips: dict[str, QPushButton] = {}
        self.vbox.addLayout(self.chip_grid)

        self.package_list = QPackageList(game_model, self.ato_model)
        self.vbox.addWidget(self.package_list)
        self.connect_counts(self.ato_model)

        self.button_row = QHBoxLayout()
        self.vbox.addLayout(self.button_row)

        self.edit_button = QPushButton("Edit")
        self.edit_button.clicked.connect(self.on_edit)
        self.button_row.addWidget(self.edit_button)

        self.clone_button = QPushButton("Clone")
        self.clone_button.setProperty("style", "btn-success")
        self.clone_button.clicked.connect(self.on_clone)
        self.button_row.addWidget(self.clone_button)

        self.delete_button = QPushButton("Cancel/abort")
        self.delete_button.setProperty("style", "btn-danger")
        self.delete_button.clicked.connect(self.on_delete)
        self.button_row.addWidget(self.delete_button)

        self.timeline_button = QPushButton("Timeline")
        self.timeline_button.setToolTip("Show the ATO period as a timeline")
        self.timeline_button.clicked.connect(self.timeline_requested)
        self.button_row.addWidget(self.timeline_button)

        self.current_changed.connect(self.on_current_changed)
        self.on_current_changed()
        self.update_chips()

    timeline_requested = Signal()

    CHIPS_PER_ROW = 5

    def connect_counts(self, model: AtoModel) -> None:
        if getattr(model, "_chip_counts_connected", False):
            return
        model._chip_counts_connected = True  # type: ignore[attr-defined]
        for signal in (
            model.rowsInserted,
            model.rowsRemoved,
            model.modelReset,
            model.layoutChanged,
            model.packages_changed,
        ):
            signal.connect(self.update_chips)

    def update_chips(self, *_args: object) -> None:
        """One checkable chip per category present in the ATO, with counts,
        and the Fold chip."""
        counts: dict[str, int] = {}
        packages = list(self.ato_model.ato.packages)
        for package in packages:
            key = ap.package_group(package).key
            counts[key] = counts.get(key, 0) + 1
        proxy = self.package_list.proxy
        game = self.ato_model.game_model.game
        blue = getattr(self.ato_model.game_model, "is_ownfor", True)
        proxy.refold(game, packages, blue)
        hidden = proxy.hidden
        for chip in self.chips.values():
            self.chip_grid.removeWidget(chip)
            chip.deleteLater()
        self.chips = {}
        position = 0
        if proxy.folds:
            folded = proxy.folding
            rows = ap.folded_rows(
                packages,
                ap.main_push(game, blue) if game else None,
                ap.elsewhere_ids(game) if game else None,
            )
            chip = QPushButton(f"Fold {rows}/{len(packages)}" if folded else "Fold off")
            chip.setCheckable(True)
            chip.setChecked(folded)
            chip.setToolTip(
                "Routine lines and the waves outside the main push are one row "
                "each. Click to show every package."
            )
            chip.setStyleSheet(self.chip_style("#4f5f6f"))
            chip.toggled.connect(self.on_fold_toggled)
            self.chip_grid.addWidget(chip, 0, 0)
            self.chips["__fold__"] = chip
            position = 1
        for group in ap.GROUPS:
            if group.key not in counts and group.key not in hidden:
                continue
            chip = QPushButton(f"{group.short} {counts.get(group.key, 0)}")
            chip.setCheckable(True)
            chip.setChecked(group.key not in hidden)
            chip.setToolTip(f"{group.label}: click to hide or show")
            chip.setStyleSheet(self.chip_style(group.color))
            chip.toggled.connect(
                lambda shown, key=group.key: self.on_chip_toggled(key, shown)
            )
            self.chip_grid.addWidget(
                chip, position // self.CHIPS_PER_ROW, position % self.CHIPS_PER_ROW
            )
            self.chips[group.key] = chip
            position += 1

    @staticmethod
    def chip_style(color: str) -> str:
        return (
            "QPushButton { padding: 1px 6px; border-radius: 8px; font-size: 8pt;"
            f" border: 1px solid {color}; background: transparent; color: #9aa7b2; }}"
            f" QPushButton:checked {{ background: {color}; color: white; }}"
        )

    def on_chip_toggled(self, key: str, shown: bool) -> None:
        self.package_list.proxy.set_hidden(key, not shown)

    def on_fold_toggled(self, folded: bool) -> None:
        self.package_list.proxy.set_folding(folded)
        self.update_chips()

    @property
    def current_changed(self):
        """Returns the signal emitted when the flight selection changes."""
        return self.package_list.selectionModel().currentChanged

    def on_current_changed(self) -> None:
        """Updates the status of the edit and delete buttons."""
        index = self.package_list.currentIndex()
        enabled = index.isValid()
        self.edit_button.setEnabled(enabled)
        self.clone_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)
        self.change_map_package_selection(index)

    def change_map_package_selection(self, index: QModelIndex) -> None:
        if not index.isValid():
            EventStream.put_nowait(GameUpdateEvents().deselect_flight())
            return

        package = self.ato_model.get_package_model(self.package_list.source(index))
        if package.rowCount() == 0:
            EventStream.put_nowait(GameUpdateEvents().deselect_flight())
        else:
            EventStream.put_nowait(
                GameUpdateEvents().select_flight(
                    package.flight_at_index(package.index(0))
                )
            )

    def on_edit(self) -> None:
        """Opens the package edit dialog."""
        index = self.package_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot edit package when no package is selected.")
            return
        self.package_list.edit_package(index)

    def on_clone(self) -> None:
        index = self.package_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot clone package when no package is selected.")
            return
        self.package_list.clone_package(index)

    def on_delete(self) -> None:
        """Removes the package from the ATO."""
        index = self.package_list.currentIndex()
        if not index.isValid():
            logging.error(f"Cannot delete package when no package is selected.")
            return
        self.package_list.delete_package(index)

    def enable_buttons(self, enabled: bool) -> None:
        self.edit_button.setEnabled(enabled)
        self.clone_button.setEnabled(enabled)
        self.delete_button.setEnabled(enabled)


#: The left panel's tabs.
PACKAGES_TAB = 0


class QAirTaskingOrderPanel(QSplitter):
    """A split panel for displaying the packages and flights of an ATO.

    Used as the left-bar of the main UI. The top half of the panel displays the
    packages of the player's ATO, and the bottom half displays the flights of
    the selected package.
    """

    def __init__(self, game_model: GameModel) -> None:
        super().__init__(Qt.Orientation.Vertical)
        self.game_model = game_model
        self.ato_model = game_model.ato_model

        # ATO
        self.red_ato_checkbox = QCheckBox()
        self.red_ato_checkbox.toggled.connect(self.on_ato_changed)
        self.red_ato_labeled = QLabeledWidget(
            "Show/Plan OPFOR's ATO: ", self.red_ato_checkbox
        )

        # Before the campaign begins, the ATO shows the pre-war posture plan.
        # It is never flown: Begin Campaign plans turn 1 from scratch.
        self.pre_war_note = QLabel(PRE_WAR_NOTE)
        self.pre_war_note.setWordWrap(True)
        self.pre_war_note.setStyleSheet("color: #e0b050;")
        # The turn briefing (F13): phase, intent, key packages, threats, in
        # full on the Your flight tab under the card.
        self.turn_briefing = QTextBrowser()
        self.turn_briefing.setOpenExternalLinks(False)
        self.turn_briefing.setToolTip(
            "The turn briefing: the opening, the phase and intent, the main push, "
            "key packages, routine lines and the expected threats."
        )
        # Your flight (P3): the flight the plan fragged you to, and the other
        # offers.
        from .yourflight import YourFlightCard

        self.your_flight = YourFlightCard(game_model)
        self.your_flight.package_selected.connect(self.select_package)
        ato_layout = QVBoxLayout()
        ato_layout.addLayout(self.red_ato_labeled)
        ato_layout.addWidget(self.pre_war_note)

        self.ato_group_box = QGroupBox("ATO")
        self.ato_group_box.setLayout(ato_layout)

        self.package_panel = QPackagePanel(game_model, self.ato_model)
        self.package_panel.current_changed.connect(self.on_package_change)

        self.flight_panel = QFlightPanel(game_model)

        # Two tabs, so the packages get the whole height: the ATO (packages
        # and flights) and your flight with the turn's headline and briefing.
        packages = QSplitter(Qt.Orientation.Vertical)
        packages.addWidget(self.ato_group_box)
        packages.addWidget(self.package_panel)
        packages.addWidget(self.flight_panel)
        your_tab = QWidget()
        your_layout = QVBoxLayout(your_tab)
        your_layout.addWidget(self.your_flight)
        your_layout.addWidget(self.turn_briefing, 1)
        self.tabs = QTabWidget()
        self.tabs.addTab(packages, "Packages")
        self.tabs.addTab(your_tab, "Your flight")
        self.addWidget(self.tabs)

        self.timeline_dialog: Optional[AtoTimelineDialog] = None
        self.package_panel.timeline_requested.connect(self.open_timeline)

        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        # Fog of war may have been turned on (Settings) while the enemy's ATO
        # is shown: hide it again.
        GameUpdateSignal.get_instance().gameupdated.connect(self._enforce_fog)
        GameUpdateSignal.get_instance().gameupdated.connect(self._update_pre_war_note)
        self._update_pre_war_note()

    def _update_pre_war_note(self, game: object = None) -> None:
        # The signal carries the game, which may be newer than the model's.
        if game is None:
            game = self.game_model.game
        self.pre_war_note.setVisible(getattr(game, "turn", None) == 0)
        self._update_turn_briefing(game)
        try:
            self.your_flight.refresh(game)
        except Exception:
            logging.exception("Could not refresh the Your flight card")

    def _update_turn_briefing(self, game: object) -> None:
        from qt_ui import atopresentation as ap

        text = None
        if game is not None and getattr(game, "turn", 0) > 0:
            try:
                text = ap.turn_briefing(game)  # type: ignore[arg-type]
            except Exception:
                logging.exception("Could not build the turn briefing")
        self.turn_briefing.setHtml(text or "")
        self.turn_briefing.setVisible(bool(text))

    def _enforce_fog(self, _game: object = None) -> None:
        if self.red_ato_checkbox.isChecked() and not self._opfor_allowed():
            self.red_ato_checkbox.setChecked(False)

    def open_timeline(self) -> None:
        """Opens (or raises) the non-modal ATO timeline window."""
        if self.timeline_dialog is None:
            self.timeline_dialog = AtoTimelineDialog(self.game_model, self.window())
            self.timeline_dialog.package_selected.connect(self.select_package)
        self.timeline_dialog.set_opfor(
            self.red_ato_checkbox.isChecked() and self._opfor_allowed()
        )
        self.timeline_dialog.show()
        self.timeline_dialog.raise_()
        self.timeline_dialog.activateWindow()

    def select_package(self, package: Package) -> None:
        """Selects a package in the sidebar (and so on the map)."""
        self.tabs.setCurrentIndex(PACKAGES_TAB)
        show_opfor = (
            not package.flights[0].blue.is_blue
            if package.flights
            else (self.red_ato_checkbox.isChecked())
        )
        if self.red_ato_checkbox.isChecked() != show_opfor:
            self.red_ato_checkbox.setChecked(show_opfor)
        self.package_panel.package_list.select_package(package)

    def select_flight_on_map(self, flight: Flight) -> None:
        """Selects the package and flight owning the given flight.

        Triggered when the player clicks a flight's route line on the web map.
        """
        self.tabs.setCurrentIndex(PACKAGES_TAB)
        # Make sure the panel is showing the ATO that owns this flight.
        show_opfor = not flight.blue.is_blue
        if self.red_ato_checkbox.isChecked() != show_opfor:
            self.red_ato_checkbox.setChecked(show_opfor)

        if flight.package not in self.ato_model.ato.packages:
            return
        self.package_panel.package_list.select_package(flight.package)

        # Selecting the package synchronously triggers on_package_change, which
        # sets the flight panel's package model. Now select the flight row.
        if flight not in flight.package.flights:
            return
        flight_row = flight.package.flights.index(flight)
        self.flight_panel.flight_list.selectionModel().setCurrentIndex(
            self.flight_panel.flight_list.model().index(flight_row, 0),
            QItemSelectionModel.SelectionFlag.ClearAndSelect,
        )

    def on_package_change(self) -> None:
        """Sets the newly selected flight for display in the bottom panel."""
        index = self.package_panel.package_list.currentIndex()
        if index.isValid():
            self.package_panel.enable_buttons(True)
            self.flight_panel.set_package(
                self.ato_model.get_package_model(
                    self.package_panel.package_list.source(index)
                )
            )
        else:
            self.package_panel.enable_buttons(False)
            self.flight_panel.set_package(None)

    def _opfor_allowed(self) -> bool:
        from game.server.fogofwar import OPFOR_PLAN_HIDDEN, opfor_plan_visible

        allowed = opfor_plan_visible(self.game_model.game)
        self.red_ato_checkbox.setToolTip("" if allowed else OPFOR_PLAN_HIDDEN)
        return allowed

    def on_ato_changed(self) -> None:
        opfor = self.red_ato_checkbox.isChecked()
        if opfor and not self._opfor_allowed():
            # Fog of war: the enemy's ATO stays hidden.
            self.red_ato_checkbox.setChecked(False)
            return
        ato_model = (
            self.game_model.red_ato_model if opfor else self.game_model.ato_model
        )
        ato_model.layoutChanged.connect(self.package_panel.on_current_changed)
        self.ato_model = ato_model
        self.package_panel.ato_model = ato_model
        self.package_panel.package_list.set_ato_model(ato_model)
        self.package_panel.connect_counts(ato_model)
        self.package_panel.update_chips()
        self.package_panel.enable_buttons(False)
        self.flight_panel.flight_list.set_package(None)
        events = GameUpdateEvents().deselect_flight()
        EventStream.put_nowait(events)
        self.game_model.is_ownfor = not opfor
        if self.timeline_dialog is not None:
            self.timeline_dialog.set_opfor(opfor)
