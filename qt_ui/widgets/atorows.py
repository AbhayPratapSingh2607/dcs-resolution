"""Grouped package rows and flight rows for the ATO sidebar.

Packages are sorted by mission group (qt_ui.atopresentation.GROUPS) and TOT
through AtoGroupProxy, which also hides collapsed groups and folds (W4): a
routine line with its reliefs, or a category's packages before or after
the main push, show as one row until opened with a click on their badge.
The first row of each group carries a header band. Rows are painted, not
laid out as text: a colour bar for the group, the package title and TOT on
the first line, the composition and badges (players, DCS window, missing
pilots, risk) on the second.
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QModelIndex, QRect, QSize, QSortFilterProxyModel, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QIcon, QPainter, QPen
from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from game.ato import Flight, Package
from qt_ui import atopresentation as ap
from qt_ui.delegates import painter_context
from qt_ui.models import AtoModel, GameModel, PackageModel

HMARGIN = 6
VMARGIN = 4
HEADER_HEIGHT = 22
BAR_WIDTH = 4
DIM = QColor("#9aa7b2")
TEXT = QColor("#e6ebef")


class AtoGroupProxy(QSortFilterProxyModel):
    """Packages sorted by group then TOT; collapsed groups and the members
    of closed folds are filtered out."""

    def __init__(self) -> None:
        super().__init__()
        self.hidden: set[str] = set()
        #: Folding on (the default) or every package shown.
        self.folding = True
        self.folds: dict[int, ap.Fold] = {}
        self.open_folds: set[str] = set()
        self.setDynamicSortFilter(True)

    def set_hidden(self, key: str, hidden: bool) -> None:
        if hidden:
            self.hidden.add(key)
        else:
            self.hidden.discard(key)
        self.invalidateFilter()

    def refold(self, game: object, packages: list[Package], blue: bool = True) -> None:
        """Recompute the folds for the packages shown."""
        push = ap.main_push(game, blue) if game is not None else None  # type: ignore[arg-type]
        elsewhere = ap.elsewhere_ids(game) if game is not None else set()  # type: ignore[arg-type]
        self.folds = ap.folds(packages, push, elsewhere)
        keys = {fold.key for fold in self.folds.values()}
        self.open_folds &= keys
        self.invalidateFilter()

    def set_folding(self, folding: bool) -> None:
        self.folding = folding
        self.invalidateFilter()

    def fold_of(self, package: Package) -> Optional[ap.Fold]:
        if not self.folding:
            return None
        return self.folds.get(id(package))

    def is_open(self, fold: ap.Fold) -> bool:
        return fold.key in self.open_folds

    def toggle_fold(self, fold: ap.Fold) -> None:
        if fold.key in self.open_folds:
            self.open_folds.discard(fold.key)
        else:
            self.open_folds.add(fold.key)
        self.invalidateFilter()

    def open_fold_for(self, package: Package) -> None:
        fold = self.fold_of(package)
        if fold is not None and not self.is_open(fold):
            self.open_folds.add(fold.key)
            self.invalidateFilter()

    def package(self, index: QModelIndex) -> Package:
        return index.data(AtoModel.PackageRole)

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if model is None:
            return False
        package = model.index(source_row, 0, source_parent).data(AtoModel.PackageRole)
        if package is None:
            return False
        if ap.package_group(package).key in self.hidden:
            return False
        fold = self.fold_of(package)
        if fold is None or self.is_open(fold):
            return True
        return fold.representative is package

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        a = left.data(AtoModel.PackageRole)
        b = right.data(AtoModel.PackageRole)
        if a is None or b is None:
            return False
        return ap.sort_key(a) < ap.sort_key(b)


def _badge(painter: QPainter, right: int, top: int, height: int, text: str, color: QColor, metrics: QFontMetrics) -> int:
    """Draws a rounded badge ending at `right`; returns its left edge."""
    width = metrics.horizontalAdvance(text) + 10
    rect = QRect(right - width, top, width, height)
    with painter_context(painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(QColor("#ffffff")))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)
    return rect.left() - 4


FOLD_TAB_COLOR = QColor("#4f5f6f")


def _fold_tab(painter: QPainter, rect: QRect, fold_open: bool, count: int, metrics: QFontMetrics) -> None:
    """The open/close tab of a fold: its own strip on the card's right edge,
    the arrow above the count."""
    with painter_context(painter):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(FOLD_TAB_COLOR))
        painter.drawRoundedRect(rect, 4, 4)
        painter.setPen(QPen(QColor("#ffffff")))
        half = rect.height() // 2
        painter.drawText(
            QRect(rect.left(), rect.top(), rect.width(), half),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            "▾" if fold_open else "▸",
        )
        painter.drawText(
            QRect(rect.left(), rect.top() + half, rect.width(), rect.height() - half),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            str(count),
        )


class PackageRowDelegate(QStyledItemDelegate):
    def __init__(self, game_model: GameModel) -> None:
        super().__init__()
        self.game_model = game_model
        #: Where each row's fold badge was painted, by package id, so the
        #: list can toggle the fold on a click there.
        self.fold_badges: dict[int, QRect] = {}

    @staticmethod
    def package(index: QModelIndex) -> Optional[Package]:
        return index.data(AtoModel.PackageRole)

    @staticmethod
    def fold_state(index: QModelIndex) -> tuple[Optional[ap.Fold], bool]:
        """The package's fold and whether it is open, from the proxy."""
        model = index.model()
        package = index.data(AtoModel.PackageRole)
        if not isinstance(model, AtoGroupProxy) or package is None:
            return None, True
        fold = model.fold_of(package)
        if fold is None:
            return None, True
        return fold, model.is_open(fold)

    @staticmethod
    def fonts(option: QStyleOptionViewItem) -> tuple[QFont, QFont, QFont]:
        title = QFont(option.font)
        title.setPointSize(10)
        title.setBold(True)
        body = QFont(option.font)
        body.setPointSize(9)
        small = QFont(option.font)
        small.setPointSize(8)
        return title, body, small

    def is_group_start(self, index: QModelIndex) -> bool:
        if index.row() == 0:
            return True
        previous = index.sibling(index.row() - 1, 0)
        a, b = self.package(previous), self.package(index)
        if a is None or b is None:
            return True
        return ap.package_group(a).key != ap.package_group(b).key

    def group_stats(self, index: QModelIndex) -> tuple[int, int]:
        model = index.model()
        package = self.package(index)
        if model is None or package is None:
            return 0, 0
        key = ap.package_group(package).key
        packages = sorties = 0
        for row in range(model.rowCount()):
            other = model.index(row, 0).data(AtoModel.PackageRole)
            if other is not None and ap.package_group(other).key == key:
                packages += 1
                sorties += ap.sorties(other)
        return packages, sorties

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        title, body, _ = self.fonts(option)
        height = QFontMetrics(title).height() + QFontMetrics(body).height() + 3 * VMARGIN
        if self.is_group_start(index):
            height += HEADER_HEIGHT
        return QSize(260, height)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        package = self.package(index)
        if package is None:
            return
        game = self.game_model.game
        group = ap.package_group(package)
        color = QColor(group.color)
        title_font, body_font, small_font = self.fonts(option)
        rect = QRect(option.rect)

        if self.is_group_start(index):
            header = QRect(rect.left(), rect.top(), rect.width(), HEADER_HEIGHT)
            rect.setTop(rect.top() + HEADER_HEIGHT)
            packages, sorties = self.group_stats(index)
            with painter_context(painter):
                band = QColor(color)
                band.setAlpha(110)
                painter.fillRect(header, band)
                painter.fillRect(QRect(header.left(), header.bottom() - 1, header.width(), 2), color)
                font = QFont(small_font)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QPen(QColor("#ffffff")))
                painter.drawText(
                    header.adjusted(HMARGIN, 0, -HMARGIN, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    group.label.upper(),
                )
                painter.setFont(small_font)
                painter.drawText(
                    header.adjusted(HMARGIN, 0, -HMARGIN, 0),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                    f"{packages} pkg · {sorties} sorties",
                )

        # Selection and hover background for the package part only.
        body_option = QStyleOptionViewItem(option)
        body_option.rect = rect
        super().paint(painter, body_option, QModelIndex())

        with painter_context(painter):
            painter.fillRect(QRect(rect.left(), rect.top() + 2, BAR_WIDTH, rect.height() - 4), color)
            inner = rect.adjusted(BAR_WIDTH + HMARGIN, VMARGIN, -HMARGIN, -VMARGIN)
            title_metrics = QFontMetrics(title_font)
            body_metrics = QFontMetrics(body_font)
            small_metrics = QFontMetrics(small_font)

            fold, fold_open = self.fold_state(index)
            self.fold_badges.pop(id(package), None)
            if fold is not None and (not fold_open or fold.representative is package):
                # The fold's open/close tab: a strip of its own on the right
                # edge, not one of the badges. A closed fold shows it on its one
                # row; an open fold on its first row.
                painter.setFont(small_font)
                tab_width = small_metrics.horizontalAdvance(str(max(fold.count, 99))) + 12
                tab = QRect(inner.right() - tab_width + 1, inner.top(), tab_width, inner.height())
                _fold_tab(painter, tab, fold_open, fold.count, small_metrics)
                self.fold_badges[id(package)] = tab
                inner.setRight(tab.left() - 6)

            line1 = QRect(inner.left(), inner.top(), inner.width(), title_metrics.height())
            line2 = QRect(inner.left(), line1.bottom() + VMARGIN, inner.width(), body_metrics.height())

            if fold is not None and not fold_open:
                # A closed fold: one row for the line or the wave.
                painter.setFont(title_font)
                painter.setPen(QPen(TEXT))
                painter.drawText(
                    line1,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    title_metrics.elidedText(fold.label, Qt.TextElideMode.ElideRight, max(line1.width(), 20)),
                )
                painter.setFont(body_font)
                painter.setPen(QPen(DIM))
                painter.drawText(
                    line2,
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                    body_metrics.elidedText(fold.summary(), Qt.TextElideMode.ElideRight, max(line2.width(), 20)),
                )
                return

            # Line 1: TOT on the right, title elided to fit.
            tot = f"TOT {ap.fmt(package.time_over_target)}"
            offset = ap.offset_text(game, package.time_over_target) if game else ""
            painter.setFont(small_font)
            painter.setPen(QPen(DIM))
            offset_width = small_metrics.horizontalAdvance(offset)
            painter.drawText(line1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, offset)
            painter.setFont(title_font)
            painter.setPen(QPen(TEXT))
            tot_rect = line1.adjusted(0, 0, -(offset_width + 6), 0)
            painter.drawText(tot_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, tot)
            title_room = tot_rect.width() - title_metrics.horizontalAdvance(tot) - 10
            painter.drawText(
                line1,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                title_metrics.elidedText(ap.title(package), Qt.TextElideMode.ElideRight, max(title_room, 20)),
            )

            # Line 2: badges on the right, composition elided in the rest.
            painter.setFont(small_font)
            right = line2.right()
            badge_height = min(line2.height(), small_metrics.height() + 2)
            top = line2.top() + (line2.height() - badge_height) // 2
            risk = ap.risk_badge(package)
            if risk is not None:
                right = _badge(painter, right, top, badge_height, risk.text, QColor(risk.color), small_metrics)
            missing = sum(f.missing_pilots for f in package.flights)
            if missing:
                right = _badge(painter, right, top, badge_height, f"{missing} no crew", QColor("#9e3232"), small_metrics)
            if game is not None and ap.in_dcs_window(game, package):
                right = _badge(painter, right, top, badge_height, "DCS", QColor("#3592c4"), small_metrics)
            clients = sum(f.client_count for f in package.flights)
            if clients:
                right = _badge(painter, right, top, badge_height, f"{clients} player", QColor("#82a466"), small_metrics)
            if getattr(package, "pinned", False):
                right = _badge(painter, right, top, badge_height, "pinned", QColor("#7a6a3c"), small_metrics)
            painter.setFont(body_font)
            painter.setPen(QPen(DIM))
            painter.drawText(
                QRect(line2.left(), line2.top(), right - line2.left(), line2.height()),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                body_metrics.elidedText(
                    ap.composition(package), Qt.TextElideMode.ElideRight, max(right - line2.left(), 20)
                ),
            )

    def helpEvent(self, event, view, option, index) -> bool:  # type: ignore[no-untyped-def]
        package = self.package(index)
        game = self.game_model.game
        if package is not None and game is not None:
            from PySide6.QtWidgets import QToolTip

            fold, fold_open = self.fold_state(index)
            if fold is not None and not fold_open:
                from html import escape

                lines = [f"<b>{escape(fold.label)}</b>", escape(fold.summary())]
                for member in fold.packages[:12]:
                    lines.append(f"{ap.fmt(member.time_over_target)} {escape(ap.title(member))}")
                if fold.count > 12:
                    lines.append(f"and {fold.count - 12} more")
                lines.append("<i>Click the ▸ tab on the right to open</i>")
                QToolTip.showText(event.globalPos(), "<br/>".join(lines), view)
                return True
            QToolTip.showText(event.globalPos(), ap.package_tooltip(game, package), view)
            return True
        return super().helpEvent(event, view, option, index)


class FlightRowDelegate(QStyledItemDelegate):
    """Flight rows: aircraft icon, role tag, size, callsign, key times."""

    def __init__(self, package: Package) -> None:
        super().__init__()
        self.package = package

    @staticmethod
    def flight(index: QModelIndex) -> Optional[Flight]:
        return index.data(PackageModel.FlightRole)

    @staticmethod
    def fonts(option: QStyleOptionViewItem) -> tuple[QFont, QFont]:
        main = QFont(option.font)
        main.setPointSize(10)
        main.setBold(True)
        small = QFont(option.font)
        small.setPointSize(8)
        return main, small

    @staticmethod
    def icon_size(option: QStyleOptionViewItem) -> QSize:
        size = option.decorationSize
        return size if isinstance(size, QSize) else QSize(0, 0)

    def lines(self, flight: Flight) -> int:
        return 3 if not flight.state.is_waiting_for_start or flight.reused_airframes else 2

    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex) -> QSize:
        flight = self.flight(index)
        main, small = self.fonts(option)
        lines = self.lines(flight) if flight is not None else 2
        height = QFontMetrics(main).height() + (lines - 1) * QFontMetrics(small).height()
        height += (lines + 1) * VMARGIN
        return QSize(260, max(height, self.icon_size(option).height() + 2 * VMARGIN))

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        super().paint(painter, option, QModelIndex())
        flight = self.flight(index)
        if flight is None:
            return
        main_font, small_font = self.fonts(option)
        main_metrics = QFontMetrics(main_font)
        small_metrics = QFontMetrics(small_font)
        rect = option.rect.adjusted(HMARGIN, VMARGIN, -HMARGIN, -VMARGIN)
        with painter_context(painter):
            icon: Optional[QIcon] = index.data(Qt.ItemDataRole.DecorationRole)
            icon_size = self.icon_size(option)
            if icon is not None and icon_size.width():
                icon.paint(
                    painter,
                    QRect(rect.left(), rect.top(), icon_size.width(), icon_size.height()),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                )
                rect = rect.adjusted(icon_size.width() + HMARGIN, 0, 0, 0)

            # Line 1: role tag, size and aircraft, callsign; player badges right.
            line1 = QRect(rect.left(), rect.top(), rect.width(), main_metrics.height())
            painter.setFont(small_font)
            support = ap.is_support(flight)
            role = ap.flight_role(flight)
            tag_color = QColor("#5b6b79") if support else QColor(ap.package_group(self.package).color)
            tag_width = small_metrics.horizontalAdvance(role) + 10
            tag = QRect(line1.left(), line1.top() + 1, tag_width, line1.height() - 2)
            with painter_context(painter):
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(tag_color))
                painter.drawRoundedRect(tag, 4, 4)
                painter.setPen(QPen(QColor("#ffffff")))
                painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, role)
            right = line1.right()
            badge_height = small_metrics.height() + 2
            top = line1.top() + (line1.height() - badge_height) // 2
            if flight.missing_pilots:
                right = _badge(painter, right, top, badge_height, f"{flight.missing_pilots} no crew", QColor("#9e3232"), small_metrics)
            if flight.client_count:
                right = _badge(painter, right, top, badge_height, f"{flight.client_count} player", QColor("#82a466"), small_metrics)
            callsign = getattr(flight, "callsign", None)
            name = f"{flight.count}× {ap.short_aircraft_name(flight)}"
            if callsign is not None and getattr(callsign, "name", None):
                name += f"  {callsign.name} {callsign.nr or 1}"
            if flight.custom_name:
                name += f"  ({flight.custom_name})"
            painter.setFont(main_font)
            painter.setPen(QPen(TEXT))
            text_rect = QRect(tag.right() + 6, line1.top(), right - tag.right() - 6, line1.height())
            painter.drawText(
                text_rect,
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                main_metrics.elidedText(name, Qt.TextElideMode.ElideRight, max(text_rect.width(), 20)),
            )

            # Line 2: key times. Line 3: route and state.
            painter.setFont(small_font)
            painter.setPen(QPen(DIM))
            y = line1.bottom() + VMARGIN
            line2 = QRect(rect.left(), y, rect.width(), small_metrics.height())
            painter.drawText(line2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, ap.flight_times_text(flight))
            if self.lines(flight) == 3:
                line3 = QRect(rect.left(), line2.bottom() + VMARGIN, rect.width(), small_metrics.height())
                parts = []
                if not flight.state.is_waiting_for_start:
                    parts.append(flight.state.description.title())
                if flight.reused_airframes:
                    parts.append("2nd sortie (same airframes)")
                painter.drawText(line3, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, " · ".join(parts))
            route = flight.departure.name
            if flight.arrival != flight.departure:
                route += f" → {flight.arrival.name}"
            painter.drawText(line2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, route)
