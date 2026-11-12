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
FIRE = QColor("#ff6b3d")

#: The timeline's fire mission section (game.warfare.firemissions).
FIRE_GROUP = ap.Group("fire", "Fire missions", "#b5452c", "Fire")


class FireLane:
    """One launcher's fire missions this turn."""

    def __init__(self, label: str, missions: list) -> None:
        self.label = label
        self.missions = missions
        #: The missions stacked in tracks so that none overlap: each track
        #: is a row of the lane.
        self.tracks: list[list] = [missions] if missions else [[]]


def stack_tracks(spans: list[tuple[object, float, float]]) -> list[list]:
    """Greedy packing of (item, start, end) spans, sorted by start, into the
    fewest tracks where no two spans in a track overlap."""
    tracks: list[list] = []
    ends: list[float] = []
    for item, start, end in sorted(spans, key=lambda s: (s[1], s[2])):
        for i, last in enumerate(ends):
            if start > last:
                tracks[i].append(item)
                ends[i] = end
                break
        else:
            tracks.append([item])
            ends.append(end)
    return tracks or [[]]


class TimelineWidget(QWidget):
    package_clicked = Signal(object)
    package_double_clicked = Signal(object)
    #: The player dragged the DCS window; minutes after the period start.
    window_moved = Signal(int)
    #: The player dragged a package to a new TOT (on release).
    package_moved = Signal(object)
    #: The player dragged a fire mission to a new time (on release).
    fire_mission_moved = Signal(object)
    fire_mission_double_clicked = Signal()

    #: The dragged window snaps to this many minutes (the picker's step).
    WINDOW_STEP_MIN = 15
    #: A dragged package's TOT snaps to this many minutes.
    PACKAGE_STEP_MIN = 1
    #: Pixels the mouse must move before a press on a package becomes a drag.
    DRAG_THRESHOLD_PX = 4

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
        #: (press x, window offset then) while the DCS window is dragged.
        self._window_drag: Optional[tuple[float, int]] = None
        #: (package, press x, its TOT then, dragging yet) while a package is
        #: pressed; it becomes a drag once the mouse moves a few pixels.
        self._package_drag: Optional[tuple[Package, float, datetime, bool]] = None
        self._fire_hits: list[tuple[QRect, object]] = []
        #: (mission, press x, its time then, dragging yet) for a fire mission.
        self._fire_drag: Optional[tuple[object, float, datetime, bool]] = None
        self._drag_y = 0.0
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
        fire = self.fire_lanes()
        if fire:
            if not self.compact:
                rows.append(("header", FIRE_GROUP))
            rows.extend(("fire", lane) for lane in fire)
        return rows

    def fire_missions(self) -> list:
        from game.warfare.firemissions import FireStatus, missions_this_turn

        game = self.game
        if game is None:
            return []
        try:
            coalition = game.blue if self.blue else game.red
            return [
                m
                for m in missions_this_turn(game, coalition.player)
                if m.status is not FireStatus.CANCELLED
            ]
        except Exception:
            return []

    def fire_lanes(self) -> list[FireLane]:
        by_launcher: dict[str, FireLane] = {}
        for mission in sorted(self.fire_missions(), key=lambda m: m.time):
            lane = by_launcher.get(mission.launcher_key)
            if lane is None:
                lane = FireLane(f"{mission.launcher_name} ({mission.weapon})", [])
                by_launcher[mission.launcher_key] = lane
            lane.missions.append(mission)
        game = self.game
        # A marker's width in minutes at this zoom, so markers don't touch.
        pad = (2 * self._fire_marker_radius() + 6) / self.px_per_min
        for lane in by_launcher.values():
            spans = []
            for mission in lane.missions:
                flight = (
                    self._flight_time(game, mission) / timedelta(minutes=1)
                    if game is not None
                    else 0.0
                )
                start = (mission.time - datetime.min) / timedelta(minutes=1)
                spans.append((mission, start - pad / 2, start + flight + pad / 2))
            lane.tracks = stack_tracks(spans)
        return list(by_launcher.values())

    def _fire_marker_radius(self) -> float:
        return max(3.0, (self.lane_height - 6) / 2)

    def refresh(self, *_args: object) -> None:
        start, end = self.bounds()
        minutes = max((end - start) / timedelta(minutes=1), 60)
        height = self.axis_height + 6
        for kind, item in self.rows():
            height += (
                self.header_height
                if kind == "header"
                else (
                    self.lane_height * len(item.tracks)  # type: ignore[union-attr]
                    if kind == "fire"
                    else self.lane_px(item)  # type: ignore[arg-type]
                )
            )
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
        return (
            self.label_width + (when - start) / timedelta(minutes=1) * self.px_per_min
        )

    # ------------------------------------------------------------ paint

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), BACKGROUND)
        game = self.game
        self._hits = []
        if game is None:
            painter.setPen(QPen(DIM))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter, "No game loaded"
            )
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
        fire_rows: list[tuple[int, FireLane]] = []
        self._fire_hits = []
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
            if kind == "fire":
                fire_height = self.lane_height * len(item.tracks)  # type: ignore[union-attr]
                if stripe:
                    painter.fillRect(
                        QRect(0, y, self.width(), fire_height), LANE_ALT
                    )
                stripe = not stripe
                fire_rows.append((y, item))  # type: ignore[arg-type]
                y += fire_height
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
        bars_clip = QRect(
            self.label_width, top, self.width() - self.label_width, bottom - top
        )
        for y, lane in lane_rows:
            height = self.lane_px(lane)
            painter.setPen(QPen(DIM if not self.compact else TEXT))
            painter.drawText(
                QRect(
                    6 + (6 if not self.compact else 0), y, self.label_width - 16, height
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(
                    lane.label, Qt.TextElideMode.ElideRight, self.label_width - 16
                ),
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

        for y, fire_lane in fire_rows:
            painter.setPen(QPen(DIM if not self.compact else TEXT))
            painter.drawText(
                QRect(
                    6 + (6 if not self.compact else 0),
                    y,
                    self.label_width - 16,
                    self.lane_height,
                ),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                metrics.elidedText(
                    fire_lane.label, Qt.TextElideMode.ElideRight, self.label_width - 16
                ),
            )
            painter.save()
            painter.setClipRect(bars_clip)
            for track, missions in enumerate(fire_lane.tracks):
                for mission in missions:
                    self._paint_fire_mission(
                        painter,
                        game,
                        mission,
                        y + track * self.lane_height,
                        self.lane_height,
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
            self.x_for(takeoff),
            y + pad,
            max(self.x_for(last) - self.x_for(takeoff), 2),
            height - 2 * pad,
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
            band = QRectF(
                self.x_for(patrol[0]),
                bar.top() + 2,
                self.x_for(patrol[1]) - self.x_for(patrol[0]),
                bar.height() - 4,
            )
            painter.setBrush(QBrush(QColor(255, 255, 255, 70 if not dimmed else 35)))
            painter.drawRect(band)
        # TOT diamond.
        x = self.x_for(package.time_over_target)
        r = (height - 2 * pad) / 2 + 1
        diamond = QPolygonF(
            [
                QPointF(x, mid - r),
                QPointF(x + r, mid),
                QPointF(x, mid + r),
                QPointF(x - r, mid),
            ]
        )
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

    def _flight_time(self, game: Game, mission: object) -> timedelta:
        """Launch to impact: Tomahawks at about 880 km/h, Scuds in minutes,
        artillery at once."""
        from game.warfare.firemissions import LauncherKind, launcher_by_key, target_of

        kind = getattr(mission, "kind", None)
        if kind is LauncherKind.ARTILLERY:
            return timedelta(0)
        try:
            coalition = game.blue if self.blue else game.red
            launcher = launcher_by_key(game, coalition.player, mission.launcher_key)  # type: ignore[attr-defined]
            target = target_of(game, mission)  # type: ignore[arg-type]
            if launcher is None or target is None:
                return timedelta(0)
            meters = launcher.position.distance_to_point(target.position)
        except Exception:
            return timedelta(0)
        speed = 245.0 if kind is LauncherKind.SHIP else 1500.0
        return timedelta(seconds=meters / speed)

    def _paint_fire_mission(
        self, painter: QPainter, game: Game, mission: object, y: int, height: int
    ) -> None:
        from game.warfare.firemissions import FireStatus

        status = getattr(mission, "status", None)
        launch = mission.time  # type: ignore[attr-defined]
        impact = launch + self._flight_time(game, mission)
        x0, x1 = self.x_for(launch), self.x_for(impact)
        mid = y + height / 2
        color = QColor(FIRE)
        if status is FireStatus.FIRED:
            color.setAlpha(120)
        # Flight: a line from launch to impact.
        if x1 - x0 >= 1:
            painter.setPen(QPen(color, 2, Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(x0, mid), QPointF(x1, mid))
        # Launch: a small triangle; impact: a burst.
        r = self._fire_marker_radius()
        painter.setPen(QPen(QColor("#1e262c"), 1))
        painter.setBrush(QBrush(color))
        painter.drawPolygon(
            QPolygonF(
                [
                    QPointF(x0 - r, mid - r),
                    QPointF(x0 + r * 0.6, mid),
                    QPointF(x0 - r, mid + r),
                ]
            )
        )
        burst = QPolygonF()
        import math

        for i in range(16):
            radius = r + 1 if i % 2 == 0 else r * 0.45
            angle = math.pi * i / 8
            burst.append(
                QPointF(x1 + radius * math.cos(angle), mid + radius * math.sin(angle))
            )
        painter.setBrush(
            QBrush(QColor("#ffd166") if status is not FireStatus.FIRED else DIM)
        )
        painter.drawPolygon(burst)
        if mission is getattr(self, "_selected_fire", None):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor("#ffffff"), 2, Qt.PenStyle.DashLine))
            painter.drawRoundedRect(
                QRectF(x0 - r - 2, y + 1, x1 - x0 + 2 * r + 4, height - 2), 3, 3
            )
        hit = QRectF(x0 - r - 2, y, x1 - x0 + 2 * r + 4, height)
        self._fire_hits.append((hit.toAlignedRect(), mission))

    def fire_mission_at(self, pos: QPoint) -> Optional[object]:
        for rect, mission in reversed(self._fire_hits):
            if rect.contains(pos):
                return mission
        return None

    def fire_mission_draggable(self, mission: object) -> bool:
        """Your own planned missions can be moved until they are fired (or
        given to the DCS mission)."""
        from game.warfare.firemissions import FireStatus

        if self.game_model is None or self.compact or not self.blue:
            return False
        if getattr(mission, "status", None) is not FireStatus.PLANNED:
            return False
        now = self.sim_now()
        return now is None or mission.time >= now  # type: ignore[attr-defined]

    def _drag_fire_mission_to(self, x: float) -> None:
        assert self._fire_drag is not None
        mission, press_x, when, _ = self._fire_drag
        minutes = round((x - press_x) / self.px_per_min)
        new_time = when + timedelta(minutes=minutes)
        start, end = self.bounds()
        now = self.sim_now()
        earliest = max(start, now) if now is not None else start
        new_time = max(earliest, min(new_time, end))
        new_time = new_time.replace(second=0, microsecond=0)
        if new_time != mission.time:  # type: ignore[attr-defined]
            mission.time = new_time  # type: ignore[attr-defined]
            self.update()
        game = self.game
        offset = self._mission_clock(new_time)
        QToolTip.showText(
            self.mapToGlobal(QPoint(int(x), int(self._drag_y))),
            f"Launch {offset} ({new_time:%H:%M})",
            self,
        )

    def _mission_clock(self, when: datetime) -> str:
        """The fire mission dialog's clock: hh:mm:ss from the DCS mission start."""
        from qt_ui.windows.QFireMissionsDialog import mission_zero

        game = self.game
        if game is None:
            return ""
        minutes = int((when - mission_zero(game)) / timedelta(minutes=1))
        sign = "-" if minutes < 0 else ""
        minutes = abs(minutes)
        return f"{sign}{minutes // 60:02d}:{minutes % 60:02d}:00"

    def fire_tooltip(self, mission: object) -> str:
        game = self.game
        m = mission
        offset = self._mission_clock(m.time)  # type: ignore[attr-defined]
        impact = m.time + self._flight_time(game, m) if game is not None else m.time  # type: ignore[attr-defined]
        lines = [
            f"<b>{m.launcher_name}</b>: {m.rounds} {m.weapon} at <b>{m.target_name}</b>",  # type: ignore[attr-defined]
            f"Launch {offset} ({m.time:%H:%M}), impact about {impact:%H:%M}",  # type: ignore[attr-defined]
            f"Status: {m.result or m.status.value}",  # type: ignore[attr-defined]
        ]
        if self.fire_mission_draggable(m):
            lines.append("<i>Drag to change the launch time</i>")
        return "<br>".join(lines)

    # ------------------------------------------------------ interaction

    def window_draggable(self) -> bool:
        """The DCS window can be moved: a full turn with room to move it,
        and none of the turn fought yet."""
        from game.sim import atoperiod

        game = self.game
        if game is None or not self.blue:
            return False
        if atoperiod.is_focused(game) or atoperiod.max_window_offset_min(game) <= 0:
            return False
        bounds = atoperiod.period(game)
        if bounds is None:
            return False
        controller = getattr(self.game_model, "sim_controller", None)
        now = getattr(controller, "current_time_in_sim_if_game_loaded", None)
        return now is None or now <= bounds[0]

    def in_window_band(self, pos: QPoint) -> bool:
        game = self.game
        window = ap.dcs_window(game) if game is not None else None
        if window is None:
            return False
        x0, x1 = self.x_for(window[0]), self.x_for(window[1])
        return x0 <= pos.x() <= x1 and pos.x() >= self.label_width

    def _drag_window_to(self, x: float) -> None:
        from game.sim import atoperiod

        game = self.game
        assert game is not None and self._window_drag is not None
        press_x, offset = self._window_drag
        minutes = offset + (x - press_x) / self.px_per_min
        step = self.WINDOW_STEP_MIN
        snapped = int(round(minutes / step) * step)
        snapped = max(0, min(snapped, atoperiod.max_window_offset_min(game)))
        if snapped != game.air_campaign.window_offset_min:
            atoperiod.pin_window(game, snapped)
            self.update()
            self.window_moved.emit(game.air_campaign.window_offset_min)

    def sim_now(self) -> Optional[datetime]:
        controller = getattr(self.game_model, "sim_controller", None)
        return getattr(controller, "current_time_in_sim_if_game_loaded", None)

    def package_draggable(self, package: Package) -> bool:
        """Your own packages can be moved in time until any of their flights
        has started up."""
        if self.game_model is None or self.compact:
            # The compact view (DCS window dialog) only shows the plan.
            return False
        if not self.blue or self.game is None or not package.flights:
            return False
        if not all(f.state.is_waiting_for_start for f in package.flights):
            return False
        if self._is_king(package):
            # A Rescue King is already on its orbit when the mission starts:
            # its orbit can be moved until it takes up its station.
            return True
        first, _ = ap.package_span(package)
        now = self.sim_now()
        return first is not None and (now is None or first >= now)

    @staticmethod
    def _is_king(package: Package) -> bool:
        from game.ato.flighttype import FlightType

        return any(f.flight_type is FlightType.RESCUE_KING for f in package.flights)

    def _drag_package_to(self, x: float) -> None:
        assert self._package_drag is not None
        package, press_x, tot, _ = self._package_drag
        minutes = (x - press_x) / self.px_per_min
        step = self.PACKAGE_STEP_MIN
        new_tot = tot + timedelta(minutes=round(minutes / step) * step)
        now = self.sim_now()
        if self._is_king(package):
            # The King's TOT no earlier than now (or than it was).
            if now is not None:
                new_tot = max(new_tot, min(tot, now))
        else:
            # Keep the first startup at or after the current time.
            first, _ = ap.package_span(package)
            if now is not None and first is not None:
                earliest = now + (package.time_over_target - first)
                if new_tot < earliest:
                    late = (earliest - tot).total_seconds()
                    new_tot = tot + timedelta(minutes=-(-late // 60))
        _, end = self.bounds()
        new_tot = min(new_tot, end)
        if new_tot != package.time_over_target:
            package.auto_asap = False
            package.time_over_target = new_tot
        # Helicopters flying from a Rescue King stay inside its time on station.
        note = ""
        farps = self.game.blue.farps if self.game is not None else None
        if farps is not None and not self._is_king(package):
            fitted = farps.fit_to_king(package)
            if fitted is not None:
                package.time_over_target = fitted
                new_tot = fitted
                note = "\nkept inside the Rescue King's time on station"
        self.update()
        shift = (new_tot - tot) // timedelta(minutes=1)
        sign = "+" if shift >= 0 else "\u2212"
        QToolTip.showText(
            self.mapToGlobal(QPoint(int(x), int(self._drag_y))),
            f"TOT {new_tot:%H:%M} ({sign}{abs(shift)} min){note}",
            self,
        )

    def package_at(self, pos: QPoint) -> Optional[Package]:
        for rect, package in reversed(self._hits):
            if rect.contains(pos):
                return package
        return None

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.ToolTip and (
            self._package_drag is not None or self._fire_drag is not None
        ):
            return True
        if event.type() == QEvent.Type.ToolTip and self.game is not None:
            mission = self.fire_mission_at(event.pos())  # type: ignore[attr-defined]
            if mission is not None:
                QToolTip.showText(event.globalPos(), self.fire_tooltip(mission), self)  # type: ignore[attr-defined]
                return True
        if event.type() == QEvent.Type.ToolTip and self.game is not None:
            package = self.package_at(event.pos())  # type: ignore[attr-defined]
            if (
                package is None
                and self.window_draggable()
                and self.in_window_band(event.pos())  # type: ignore[attr-defined]
            ):
                QToolTip.showText(
                    event.globalPos(),  # type: ignore[attr-defined]
                    "Drag to move the DCS mission window",
                    self,
                )
                return True
            if package is not None:
                QToolTip.showText(event.globalPos(), ap.package_tooltip(self.game, package), self)  # type: ignore[attr-defined]
            else:
                QToolTip.hideText()
                event.ignore()
            return True
        return super().event(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position().toPoint()
        mission = self.fire_mission_at(pos)
        if mission is not None:
            self._selected_fire = mission
            self.update()
            if (
                event.button() == Qt.MouseButton.LeftButton
                and self.fire_mission_draggable(mission)
            ):
                self._fire_drag = (mission, event.position().x(), mission.time, False)  # type: ignore[attr-defined]
                self._drag_y = event.position().y()
            event.accept()
            return
        package = self.package_at(pos)
        if package is not None:
            self.selected = package
            self.update()
            self.package_clicked.emit(package)
            if event.button() == Qt.MouseButton.LeftButton and self.package_draggable(
                package
            ):
                self._package_drag = (
                    package,
                    event.position().x(),
                    package.time_over_target,
                    False,
                )
                self._drag_y = event.position().y()
                event.accept()
                return
        elif (
            event.button() == Qt.MouseButton.LeftButton
            and self.window_draggable()
            and self.in_window_band(pos)
            and self.game is not None
        ):
            # Grab the DCS window anywhere off the packages.
            self._window_drag = (
                event.position().x(),
                self.game.air_campaign.window_offset_min,
            )
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._fire_drag is not None:
            mission, press_x, when, dragging = self._fire_drag
            x = event.position().x()
            if not dragging and abs(x - press_x) >= self.DRAG_THRESHOLD_PX:
                self._fire_drag = (mission, press_x, when, True)
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                dragging = True
            if dragging:
                self._drag_fire_mission_to(x)
            event.accept()
            return
        if self._package_drag is not None:
            package, press_x, tot, dragging = self._package_drag
            x = event.position().x()
            if not dragging and abs(x - press_x) >= self.DRAG_THRESHOLD_PX:
                self._package_drag = (package, press_x, tot, True)
                self.setCursor(Qt.CursorShape.SizeHorCursor)
                dragging = True
            if dragging:
                self._drag_package_to(x)
            event.accept()
            return
        if self._window_drag is not None:
            self._drag_window_to(event.position().x())
            event.accept()
            return
        pos = event.position().toPoint()
        hovered_fire = self.fire_mission_at(pos)
        hovered = self.package_at(pos)
        if hovered_fire is not None:
            cursor = (
                Qt.CursorShape.SizeHorCursor
                if self.fire_mission_draggable(hovered_fire)
                else Qt.CursorShape.PointingHandCursor
            )
        elif hovered is not None:
            cursor = (
                Qt.CursorShape.SizeHorCursor
                if self.package_draggable(hovered)
                else Qt.CursorShape.PointingHandCursor
            )
        elif self.window_draggable() and self.in_window_band(pos):
            cursor = Qt.CursorShape.OpenHandCursor
        else:
            cursor = Qt.CursorShape.ArrowCursor
        self.setCursor(cursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._fire_drag is not None:
            mission, _, when, dragging = self._fire_drag
            if dragging:
                self._drag_fire_mission_to(event.position().x())
            self._fire_drag = None
            QToolTip.hideText()
            if dragging and mission.time != when:  # type: ignore[attr-defined]
                self.fire_mission_moved.emit(mission)
            event.accept()
            return
        if self._package_drag is not None:
            package, _, tot, dragging = self._package_drag
            if dragging:
                self._drag_package_to(event.position().x())
            self._package_drag = None
            QToolTip.hideText()
            if dragging and package.time_over_target != tot:
                self.package_moved.emit(package)
            event.accept()
            return
        if self._window_drag is not None:
            self._drag_window_to(event.position().x())
            self._window_drag = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self.fire_mission_at(event.position().toPoint()) is not None:
            self.fire_mission_double_clicked.emit()
            return
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
            " (drag to move it) &nbsp; <span style='color:#ff6b3d'>▶ - - ✸</span>"
            " fire mission launch to impact &nbsp; · drag a package or fire mission"
            " to move it,"
            " Ctrl+wheel to zoom, double-click to edit</span>"
        )
        toolbar.addWidget(legend)
        for text, factor in (("−", 1 / 1.4), ("+", 1.4)):
            button = QPushButton(text)
            button.setFixedWidth(28)
            button.clicked.connect(
                lambda _=False, f=factor: self.timeline.set_zoom(
                    self.timeline.px_per_min * f
                )
            )
            toolbar.addWidget(button)
        fit = QPushButton("Fit")
        fit.clicked.connect(self.fit)
        toolbar.addWidget(fit)

        self.timeline = TimelineWidget(game_model)
        self.timeline.package_clicked.connect(self.package_selected)
        self.timeline.package_double_clicked.connect(self.edit_package)
        self.timeline.package_moved.connect(self.package_moved)
        self.timeline.fire_mission_moved.connect(self.fire_mission_moved)
        self.timeline.fire_mission_double_clicked.connect(self.open_fire_missions)
        from qt_ui.windows.QFireMissionsDialog import fire_mission_signals

        fire_mission_signals().changed.connect(self.timeline.refresh)
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

    def package_moved(self, package: Package) -> None:
        """A package dragged to a new TOT: apply it as the package dialog does,
        so open dialogs, the ATO list and the map follow."""
        from game.server import EventStream
        from game.sim import GameUpdateEvents

        model = self.game_model.ato_model.find_matching_package_model(package)
        if model is not None:
            model.set_tot(package.time_over_target)
        EventStream.put_nowait(GameUpdateEvents().update_flights_in_package(package))
        from qt_ui.windows.basemenu.farp.kingguard import warn_king_conflicts

        warn_king_conflicts(self, self.game_model, package)

    def fire_mission_moved(self, mission: object) -> None:
        from qt_ui.windows.QFireMissionsDialog import notify_map

        notify_map(self.game_model.game, [mission])  # type: ignore[list-item]
        self.timeline.refresh()

    def open_fire_missions(self) -> None:
        from qt_ui.windows.QFireMissionsDialog import QFireMissionsDialog

        QFireMissionsDialog(self.game_model.game, self).exec()
        self.timeline.refresh()

    def edit_package(self, package: Package) -> None:
        from qt_ui.dialogs import Dialog

        model = (
            self.game_model.red_ato_model
            if self.opfor.isChecked()
            else self.game_model.ato_model
        ).find_matching_package_model(package)
        if model is not None:
            Dialog.open_edit_package_dialog(model)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self.timeline.refresh()
