"""The "Your flight" card (P3) at the top of the ATO panel: the flight the
plan fragged you to, with its package, target and TOT; the next offers; and
the preference behind them. Picking an offer moves you there. Putting
yourself in any flight by hand still works and updates the card."""

from __future__ import annotations

import logging
from html import escape
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from game.ato.flight import Flight
from game.server import EventStream
from game.sim import GameUpdateEvents
from qt_ui.models import GameModel

#: How many other offers the card lists.
OFFERS = 8


class YourFlightCard(QGroupBox):
    package_selected = Signal(object)

    def __init__(self, game_model: GameModel) -> None:
        super().__init__("Your flight")
        self.game_model = game_model
        layout = QVBoxLayout()
        self.setLayout(layout)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        self.summary.setOpenExternalLinks(False)
        self.summary.linkActivated.connect(self._on_link)
        layout.addWidget(self.summary)
        self.reason = QLabel()
        self.reason.setWordWrap(True)
        self.reason.setStyleSheet("color: #e0b050;")
        layout.addWidget(self.reason)
        row = QHBoxLayout()
        self.offers = QComboBox()
        self.offers.setToolTip("The next best flights from the plan for you")
        row.addWidget(self.offers, 1)
        self.take = QPushButton("Take")
        self.take.setToolTip("Put yourself in this flight instead")
        self.take.clicked.connect(self._on_take)
        row.addWidget(self.take)
        self.preference = QPushButton("Preference…")
        self.preference.setToolTip("Your squadron or mission type")
        self.preference.clicked.connect(self._on_preference)
        row.addWidget(self.preference)
        layout.addLayout(row)
        self.refresh()

    # --------------------------------------------------------------- data

    @property
    def game(self):  # type: ignore[no-untyped-def]
        return self.game_model.game

    def refresh(self, game: object = None) -> None:
        from game.commander.jfacc.seat import (
            fragged_flight,
            preference_of,
            preferred_squadron,
            rank_offers,
            why_no_match,
        )

        game = game if game is not None else self.game
        if game is None or getattr(game, "turn", 0) == 0:
            self.setVisible(False)
            return
        try:
            flight = fragged_flight(game)  # type: ignore[arg-type]
            offers = rank_offers(game)  # type: ignore[arg-type]
            reason = why_no_match(game)  # type: ignore[arg-type]
            preference = preference_of(game)  # type: ignore[arg-type]
            squadron = preferred_squadron(game, preference)  # type: ignore[arg-type]
        except Exception:
            logging.exception("Could not rank the player's offers")
            self.setVisible(False)
            return
        self.setVisible(True)
        if flight is not None:
            package = flight.package
            self.summary.setText(
                f"<b>{escape(flight.squadron.name)}</b> · "
                f"{flight.count}× {escape(flight.unit_type.display_name)} "
                f"{escape(flight.flight_type.value)} · "
                f"<a href='select'>{escape(package.package_description)} "
                f"{escape(package.target.name)}</a> · TOT {package.time_over_target:%H:%M}"
            )
        else:
            self.summary.setText(
                "<i>No flight fragged.</i> Take one below, or put yourself in any "
                "flight from the Flights panel."
            )
        pref = []
        if squadron is not None:
            pref.append(squadron.name)
        if preference.mission_type is not None:
            pref.append(preference.mission_type.value)
        self.preference.setText(
            "Preference: " + ", ".join(pref) if pref else "Preference…"
        )
        self.reason.setText(reason)
        self.reason.setVisible(bool(reason))
        self.offers.clear()
        current = flight
        for offer in offers:
            if offer.flight is current:
                continue
            self.offers.addItem(offer.describe(), offer.flight)
            if self.offers.count() >= OFFERS:
                break
        self.offers.setEnabled(self.offers.count() > 0)
        self.take.setEnabled(self.offers.count() > 0)

    # ------------------------------------------------------------ actions

    def _on_link(self, _link: str) -> None:
        from game.commander.jfacc.seat import fragged_flight

        game = self.game
        if game is None:
            return
        flight = fragged_flight(game)
        if flight is not None:
            self.package_selected.emit(flight.package)

    def _on_take(self) -> None:
        from game.commander.jfacc.seat import frag
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal

        game = self.game
        flight: Optional[Flight] = self.offers.currentData()
        if game is None or flight is None:
            return
        if not frag(game, flight):
            QMessageBox.warning(self, "No pilot", "That flight has no pilot to give you.")
            return
        EventStream.put_nowait(GameUpdateEvents().update_flight(flight))
        GameUpdateSignal.get_instance().updateGame(game)
        self.package_selected.emit(flight.package)

    def _on_preference(self) -> None:
        from game.commander.jfacc.seat import auto_frag, auto_frag_enabled, unfrag
        from qt_ui.windows.GameUpdateSignal import GameUpdateSignal
        from qt_ui.windows.QPlayerSeatDialog import QPlayerSeatDialog

        game = self.game
        if game is None:
            return
        if QPlayerSeatDialog(game, self).exec():
            if auto_frag_enabled(game):
                # Re-frag by the new preference.
                unfrag(game)
                auto_frag(game)
            GameUpdateSignal.get_instance().updateGame(game)
