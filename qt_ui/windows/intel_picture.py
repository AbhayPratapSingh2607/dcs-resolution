"""The "Intel picture" page of the Intelligence window: national resolve,
front-line morale, our intelligence capability, and every enemy site we know
about with how we know it."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from game.game import Game
from game.warfare.intel_report import IntelReport, build_intel_report


class SortableItem(QTableWidgetItem):
    """Shows text, sorts by a number."""

    def __init__(self, text: str, key: float) -> None:
        super().__init__(text)
        self.key = key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, SortableItem):
            return self.key < other.key
        return super().__lt__(other)  # type: ignore[misc]


CONTACT_COLUMNS = (
    "Site",
    "Base",
    "Type",
    "Status",
    "Source",
    "Last seen",
    "Confidence",
    "Position error",
)


class IntelPictureTab(QWidget):
    def __init__(self, game: Game) -> None:
        super().__init__()
        report = build_intel_report(game)
        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self._situation(report))
        if report.isr is None:
            layout.addWidget(QLabel("Fog of war is off: every enemy site is known."))
            layout.addStretch(1)
            return
        layout.addWidget(self._contacts(report), stretch=1)

    @staticmethod
    def _situation(report: IntelReport) -> QGroupBox:
        box = QGroupBox("Situation")
        grid = QGridLayout()
        box.setLayout(grid)
        rows: list[tuple[str, str]] = []
        if report.own_resolve is not None:
            rows.append(
                (
                    "Resolve (us / them):",
                    f"{report.own_resolve} / {report.enemy_resolve}",
                )
            )
            if report.collateral_incidents:
                rows.append(
                    ("Civilian casualty incidents:", str(report.collateral_incidents))
                )
        for front in report.fronts:
            rows.append(
                (f"Front morale, {front.base} vs {front.enemy_base}:", front.morale)
            )
        if report.isr is not None:
            rows.append(("Reconnaissance and surveillance:", f"{report.isr}%"))
            if report.humint is not None:
                rows.append(
                    (
                        "Agency reliability (human / signals):",
                        f"{report.humint}% / {report.sigint}%",
                    )
                )
            known = len(report.contacts)
            rows.append(
                (
                    "Enemy sites known:",
                    f"{known} ({report.confirmed} confirmed, "
                    f"{report.believed_destroyed} believed destroyed)",
                )
            )
            if report.by_source:
                rows.append(
                    (
                        "Latest source per site:",
                        ", ".join(
                            f"{n} {s}" for s, n in report.by_source.most_common()
                        ),
                    )
                )
        if not rows:
            rows.append(("", "Intelligence and morale are turned off in settings."))
        for row, (label, value) in enumerate(rows):
            grid.addWidget(QLabel(label), row, 0)
            value_label = QLabel(value)
            value_label.setWordWrap(True)
            grid.addWidget(value_label, row, 1)
        grid.setColumnStretch(1, 1)
        return box

    @staticmethod
    def _contacts(report: IntelReport) -> QGroupBox:
        box = QGroupBox("Known enemy sites")
        layout = QVBoxLayout()
        box.setLayout(layout)
        if not report.contacts:
            layout.addWidget(QLabel("No enemy sites detected yet."))
            return box
        table = QTableWidget(len(report.contacts), len(CONTACT_COLUMNS))
        table.setHorizontalHeaderLabels(CONTACT_COLUMNS)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        for row, contact in enumerate(report.contacts):
            items = (
                QTableWidgetItem(contact.name),
                QTableWidgetItem(contact.base),
                QTableWidgetItem(contact.kind),
                QTableWidgetItem(contact.status),
                QTableWidgetItem(contact.source),
                SortableItem(contact.last_seen, contact.last_seen_turn),
                SortableItem(f"{contact.confidence}%", contact.confidence),
                SortableItem(
                    contact.position_error,
                    0 if contact.status == "confirmed" else contact.uncertainty_km,
                ),
            )
            for column, item in enumerate(items):
                table.setItem(row, column, item)
        header = table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        # Sortable by clicking a header, but start in the report's order
        # (most recently seen first).
        header.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        table.setSortingEnabled(True)
        layout.addWidget(table)
        return box
