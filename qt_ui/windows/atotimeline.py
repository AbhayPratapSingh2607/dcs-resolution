"""The ATO timeline: a Gantt chart of the ATO period.

One lane per package (continuous lines such as a CAP relief chain share one
lane), grouped by mission category in the sidebar's order and colours. Bars
run from first startup to last landing: thin from startup to takeoff, solid
while airborne, a diamond at the TOT and a lighter band for the time on
station. The DCS window is shaded; packages outside it are dimmed.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPen,
    QPolygonF,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QToolTip,
    QVBoxLayout,
    QWidget,
)

from game import Game
from game.ato import Package
from qt_ui import atopresentation as ap
from qt_ui.models import GameModel

BACKGROUND = QColor("#1e262c")
LANE_ALT = QColor("#232c33")
GRID = QColor("#33404a")
GRID_MINOR = QColor("#2a343c")
TEXT = QColor("#e6ebef")
DIM = QColor("#9aa7b2")
WINDOW = QColor(53, 146, 196, 45)
WINDOW_EDGE = QColor("#3592c4")
PUSH = QColor(217, 162, 58, 40)
PUSH_EDGE = QColor("#d9a23a")
NOW = QColor("#f0c040")


class TimelineWidget(QWidget):
    package_clicked = Signal(object)
    package_double_clicked = Signal(object)

    MIN_PPM = 0.6
    MAX_PPM = 14.0

    def __init__(
        self,
        game_model: Optional[GameModel],
        compact: bool = False,
        parent: Optional[QWidget] = None,
        game: Optional[Game] = None,
    ) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self._game = game
        self.compact = compact
        self.blue = True
        self.px_per_min = 1.6 if compact else 2.6
        self.label_width = 170 if compact else 230
        self.axis_height = 30
        self.header_height = 0 if compact else 18
        self.lane_height = 12 if compact else 22
        self.selected: Optional[Package] = None
        self._hits: list[tuple[QRect, Package]] = []
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.refresh()

    # ----------------------------------------------------------- data

    @property
    def game(self) -> Optional[Game]:
        if self._game is not None:
            return self._game
        return self.game_model.game if self.game_model is not None else None

    def packages(self) -> list[Package]:
        game = self.game
        if game is None:
            return []
        coalition = game.blue if self.blue else game.red
        return list(coalition.ato.packages)

    def bounds(self) -> tuple[datetime, datetime]:
        game = self.game
        if game is None:
            now = datetime(2000, 1, 1)
            return now, now + timedelta(hours=6)
        return ap.period_bounds(game)

    def rows(self) -> list[tuple[str, object]]:
        """("header", Group) and ("lane", Lane) rows in display order."""
        rows: list[tuple[str, object]] = []
        current = None
        for lane in ap.lanes(self.packages()):
            if lane.group.key != current and not self.compact:
                rows.append(("header", lane.group))
            current = lane.group.key
            rows.append(("lane", lane))
        return rows

    def refresh(self, *_args: object) -> None:
        start, end = self.bounds()
        minutes = max((end - start) / timedelta(minutes=1), 60)
        height = self.axis_height + 6
        for kind, item in self.rows():
            height += self.header_height if kind == "header" else self.lane_px(item)  # type: ignore[arg-type]
        self.setMinimumSize(
            QSize(int(self.label_width + minutes * self.px_per_min + 20), height)
        )
        self.updateGeometry()
        self.update()

    def set_blue(self, blue: bool) -> None:
        self.blue = blue
        self.selected = None
        self.refresh()

    def set_zoom(self, px_per_min: float) -> None:
        self.px_per_min = max(self.MIN_PPM, min(self.MAX_PPM, px_per_min))
        self.refresh()

    # --------------------------------------------------------- geometry

    def lane_px(self, lane: ap.Lane) -> int:
        """Relief chains overlap in time, so their packages alternate between
        two tracks in a taller lane."""
        if len(lane.packages) > 1:
            return int(self.lane_height * 1.6)
        return self.lane_height

    def x_for(self, when: datetime) -> float:
        start, _ = self.bounds()
        return self.label_width + (when - start) / timedelta(minutes=1) * self.px_per_min

    # ------------------------------------------------------------ paint

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        game = self.game
        self._hits = []
        if game is None:
            painter.setPen(QPen(DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No game loaded")
            return
        start, end = self.bounds()
        small = QFont(self.font())
        small.setPointSize(8)
        bold = QFont(small)
        bold.setBold(True)
        painter.setFont(small)
        top = self.axis_height
        bottom = self.height()
        right = int(self.x_for(end))

        # Lanes first (backgrounds), then grid and window over them.
        y = top
        lane_rows: list[tuple[int, ap.Lane]] = []
        stripe = False
        for kind, item in self.rows():
            if kind == "header":
                group: ap.Group = item  # type: ignore[assignment]
                band = QColor(group.color)
                band.setAlpha(70)
                painter.fillRect(QRect(0, y, self.width(), self.header_height), band)
                painter.setPen(QPen(TEXT))
                painter.setFont(bold)
                painter.drawText(
                    QRect(6, y, self.label_width, self.header_height),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                    group.label.upper(),
                )
                painter.setFont(small)
                y += self.header_height
                stripe = False
                continue
            lane: ap.Lane = item  # type: ignore[assignment]
            height = self.lane_px(lane)
            if stripe:
                painter.fillRect(QRect(0, y, self.width(), height), LANE_ALT)
            stripe = not stripe
            lane_rows.append((y, lane))
            y += height

        self._paint_grid(painter, start, end, top, bottom, small)

        push = ap.main_push(game, self.blue)
        if push is not None:
            x0, x1 = self.x_for(push[0]), self.x_for(push[1])
            painter.fillRect(QRectF(x0, top, x1 - x0, bottom - top), PUSH)
            painter.setPen(QPen(PUSH_EDGE, 1, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x0, top), QPointF(x0, bottom))
            painter.drawLine(QPointF(x1, top), QPointF(x1, bottom))
            painter.drawText(
                QRectF(x0 + 3, top - 14, max(x1 - x0 - 6, 10), 13),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                "Main push",
            )
        window = ap.dcs_window(game)
        if window is not None:
            x0, x1 = self.x_for(window[0]), self.x_for(window[1])
            painter.fillRect(QRectF(x0, top, x1 - x0, bottom - top), WINDOW)
            painter.setPen(QPen(WINDOW_EDGE, 1))
            painter.drawLine(QPointF(x0, 0), QPointF(x0, bottom))
            painter.drawLine(QPointF(x1, 0), QPointF(x1, bottom))
            painter.drawText(
                QRectF(x0 + 3, 0, max(x1 - x0 - 6, 10), 13),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                "DCS window",
            )

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        metrics = QFontMetrics(small)
        bars_clip = QRect(self.label_width, top, self.width() - self.label_width, bottom - top)
        for y, lane in lane_rows:
            height = self.lane_px(lane)
            painter.setPen(QPen(DIM if not self.compact else TEXT))
            painter.drawText(
                QRect(6 + (6 if not self.compact else 0), y, self.label_width - 16, height),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(lane.label, Qt.TextElideMode.ElideRight, self.label_width - 16),
            )
            painter.save()
            painter.setClipRect(bars_clip)
            if len(lane.packages) == 1:
                self._paint_package(painter, game, lane.packages[0], y, height)
            else:
                track = height / 2
                for i, package in enumerate(lane.packages):
                    self._paint_package(
                        painter, game, package, int(y + (i % 2) * track), int(track) + 1
                    )
            painter.restore()

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.fillRect(QRect(self.label_width - 1, 0, 1, bottom), GRID)
        if right < self.width():
            painter.fillRect(QRect(right, top, 1, bottom - top), GRID)

        now = (
            self.game_model.sim_controller.current_time_in_sim_if_game_loaded
            if self.game_model is not None
            else None
        )
        if now is not None and start <= now <= end:
            x = self.x_for(now)
            painter.setPen(QPen(NOW, 2))
            painter.drawLine(QPointF(x, top - 6), QPointF(x, bottom))

    def _paint_grid(
        self,
        painter: QPainter,
        start: datetime,
        end: datetime,
        top: int,
        bottom: int,
        font: QFont,
    ) -> None:
        minor = 15 if self.px_per_min >= 1.2 else 30
        first = start.replace(minute=0, second=0, microsecond=0)
        tick = first
        while tick <= end:
            if tick >= start:
                x = self.x_for(tick)
                hour = tick.minute == 0
                painter.fillRect(
                    QRectF(x, top if not hour else top - 6, 1, bottom - top),
                    GRID if hour else GRID_MINOR,
                )
                if hour:
                    offset = ap.offset_text(self.game, tick) if self.game else ""  # type: ignore[arg-type]
                    painter.setPen(QPen(TEXT))
                    painter.setFont(font)
                    painter.drawText(
                        QRectF(x + 3, 12, 80, 16),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        f"{tick:%H:%M}",
                    )
                    painter.setPen(QPen(DIM))
                    painter.drawText(
                        QRectF(x + 36, 12, 60, 16),
                        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                        offset.replace(":00", "h"),
                    )
            tick += timedelta(minutes=minor)

    def _paint_package(
        self, painter: QPainter, game: Game, package: Package, y: int, height: int
    ) -> None:
        group = ap.package_group(package)
        color = QColor(group.color)
        in_window = ap.in_dcs_window(game, package)
        dimmed = in_window is False
        if dimmed:
            color.setAlpha(110)
        first, last = ap.package_span(package)
        if first is None:
            return
        takeoffs = [t.takeoff for t in map(ap.key_times, package.flights) if t.takeoff]
        takeoff = min(takeoffs) if takeoffs else first
        last = last or package.time_over_target
        pad = 2 if height < 16 else 4
        bar = QRectF(
            self.x_for(takeoff), y + pad, max(self.x_for(last) - self.x_for(takeoff), 2), height - 2 * pad
        )
        # Startup to takeoff: a thin line.
        painter.setPen(QPen(color, 2))
        mid = y + height / 2
        painter.drawLine(QPointF(self.x_for(first), mid), QPointF(bar.left(), mid))
        # Airborne.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(bar, 3, 3)
        # Time on station.
        for flight in package.flights:
            patrol = ap.key_times(flight).patrol
            if patrol is None or flight is not package.primary_flight:
                continue
            band = QRectF(self.x_for(patrol[0]), bar.top() + 2, self.x_for(patrol[1]) - self.x_for(patrol[0]), bar.height() - 4)
            painter.setBrush(QBrush(QColor(255, 255, 255, 70 if not dimmed else 35)))
            painter.drawRect(band)
        # TOT diamond.
        x = self.x_for(package.time_over_target)
        r = (height - 2 * pad) / 2 + 1
        diamond = QPolygonF([QPointF(x, mid - r), QPointF(x + r, mid), QPointF(x, mid + r), QPointF(x - r, mid)])
        painter.setBrush(QBrush(QColor("#ffffff") if not dimmed else DIM))
        painter.setPen(QPen(QColor("#1e262c"), 1))
        painter.drawPolygon(diamond)
        # Players and selection outlines.
        if any(f.client_count for f in package.flights):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#82e05a"), 2))
            painter.drawRoundedRect(bar.adjusted(-1, -1, 1, 1), 3, 3)
        if package is self.selected:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(bar.adjusted(-2, -2, 2, 2), 3, 3)
        hit = QRectF(self.x_for(first), y, self.x_for(last) - self.x_for(first), height)
        self._hits.append((hit.toAlignedRect().adjusted(-2, 0, 2, 0), package))

    # ------------------------------------------------------ interaction

    def package_at(self, pos: QPoint) -> Optional[Package]:
        for rect, package in reversed(self._hits):
            if rect.contains(pos):
                return package
        return None

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and self.game is not None:
            package = self.package_at(event.pos())  # type: ignore[attr-defined]
            if package is not None:
                QToolTip.showText(event.globalPos(), ap.package_tooltip(self.game, package), self)  # type: ignore[attr-defined]
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        package = self.package_at(event.position().toPoint())
        if package is not None:
            self.selected = package
            self.update()
            self.package_clicked.emit(package)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        over = self.package_at(event.position().toPoint()) is not None
        self.setCursor(Qt.CursorShape.PointingHandCursor if over else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        package = self.package_at(event.position().toPoint())
        if package is not None:
            self.package_double_clicked.emit(package)
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self.set_zoom(self.px_per_min * factor)
            event.accept()
            return
        super().wheelEvent(event)


class AtoTimelineDialog(QDialog):
    """Non-modal window around a TimelineWidget."""

    package_selected = Signal(object)

    def __init__(self, game_model: GameModel, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.game_model = game_model
        self.setWindowTitle("ATO timeline")
        self.setModal(False)
        self.resize(1250, 720)

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        layout.addLayout(toolbar)

        self.opfor = QCheckBox("Show OPFOR's ATO")
        self.opfor.toggled.connect(self._on_opfor_toggled)
        toolbar.addWidget(self.opfor)
        toolbar.addStretch()
        legend = QLabel(
            "<span style='color:#9aa7b2'>— startup &nbsp; ▬ airborne &nbsp; ◆ TOT &nbsp;"
            " ▒ on station &nbsp; <span style='color:#82e05a'>▢</span> player flight"
            " &nbsp; <span style='color:#3592c4'>▒</span> DCS window"
            " &nbsp; · Ctrl+wheel to zoom, double-click to edit</span>"
        )
        toolbar.addWidget(legend)
        for text, factor in (("−", 1 / 1.4), ("+", 1.4)):
            button = QPushButton(text)
            button.setFixedWidth(28)
            button.clicked.connect(
                lambda _=False, f=factor: self.timeline.set_zoom(self.timeline.px_per_min * f)
            )
            toolbar.addWidget(button)
        fit = QPushButton("Fit")
        fit.clicked.connect(self.fit)
        toolbar.addWidget(fit)

        self.timeline = TimelineWidget(game_model)
        self.timeline.package_clicked.connect(self.package_selected)
        self.timeline.package_double_clicked.connect(self.edit_package)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.timeline)
        self.scroll_area.setWidgetResizable(True)
        layout.addWidget(self.scroll_area)

        for model in (game_model.ato_model, game_model.red_ato_model):
            for signal in (
                model.rowsInserted,
                model.rowsRemoved,
                model.modelReset,
                model.layoutChanged,
                model.dataChanged,
            ):
                signal.connect(self.timeline.refresh)
            # Package edits (TOT, start types, delays) redraw it at once.
            model.package_timing_changed.connect(self.timeline.refresh)
        game_model.sim_controller.sim_update.connect(self.timeline.update)

    def set_opfor(self, opfor: bool) -> None:
        self.opfor.setChecked(opfor)

    def _on_opfor_toggled(self, red: bool) -> None:
        from game.server.fogofwar import OPFOR_PLAN_HIDDEN, opfor_plan_visible

        if red and not opfor_plan_visible(self.game_model.game):
            # Fog of war: the enemy's ATO stays hidden.
            self.opfor.setToolTip(OPFOR_PLAN_HIDDEN)
            self.opfor.setChecked(False)
            return
        self.timeline.set_blue(not red)

    def fit(self) -> None:
        start, end = self.timeline.bounds()
        minutes = max((end - start) / timedelta(minutes=1), 60)
        width = self.scroll_area.viewport().width() - self.timeline.label_width - 24
        self.timeline.set_zoom(width / minutes)

    def edit_package(self, package: Package) -> None:
        from qt_ui.dialogs import Dialog

        model = (
            self.game_model.red_ato_model if self.opfor.isChecked() else self.game_model.ato_model
        ).find_matching_package_model(package)
        if model is not None:
            Dialog.open_edit_package_dialog(model)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self.timeline.refresh()
