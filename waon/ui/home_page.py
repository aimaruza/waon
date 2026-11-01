
import time
from datetime import datetime, timedelta

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QHBoxLayout, QLabel, QListView,
    QPushButton, QScrollArea, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from waon.library import locations
from waon.library.entities import METRIC_PLAYS, METRIC_TIME, RECAP_METRICS
from waon.ui import theme
from waon.ui.browse_grid import (GRID_SPACING, TILE_H, TILE_W, _ThumbnailDelegate,
                                  _TileView)
from waon.ui.browse_models import EntryModel
from waon.ui.cover_art import placeholder, rounded
from waon.ui.icons import IconButton, render_icon
from waon.util import format_listened

PERIOD_WEEK = "week"
PERIOD_MONTH = "month"
PERIOD_YEAR = "year"
PERIOD_ALL = "all"
PERIODS = (PERIOD_WEEK, PERIOD_MONTH, PERIOD_YEAR, PERIOD_ALL)
_PERIOD_LABELS = {PERIOD_WEEK: "This Week", PERIOD_MONTH: "Month",
                  PERIOD_YEAR: "Year", PERIOD_ALL: "All time"}
_NAVIGABLE_PERIODS = (PERIOD_MONTH, PERIOD_YEAR)


def bounds_for(mode, year=None, month=None, now=None):
    if mode == PERIOD_ALL:
        return None, None
    moment = datetime.fromtimestamp(time.time() if now is None else now)
    if mode == PERIOD_WEEK:
        start_of_day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start_of_day - timedelta(days=start_of_day.weekday())
        return int(start.timestamp()), None
    if mode == PERIOD_MONTH:
        y = moment.year if year is None else year
        m = moment.month if month is None else month
        start = datetime(y, m, 1)
        end = datetime(y + 1, 1, 1) if m == 12 else datetime(y, m + 1, 1)
        return int(start.timestamp()), int(end.timestamp())
    if mode == PERIOD_YEAR:
        y = moment.year if year is None else year
        start = datetime(y, 1, 1)
        end = datetime(y + 1, 1, 1)
        return int(start.timestamp()), int(end.timestamp())
    raise ValueError("unknown period {!r}".format(mode))


class _PeriodTabs(QWidget):

    periodChanged = Signal()

    _MONTH_FORMAT = "%b %Y"

    def __init__(self, parent=None, now=None):
        super().__init__(parent)
        self.setObjectName("HomePeriodTabs")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons_by_period = {}
        self._prev_buttons = {}
        self._next_buttons = {}
        self._now = datetime.fromtimestamp(time.time() if now is None else now)
        self._position = {PERIOD_MONTH: (self._now.year, self._now.month),
                          PERIOD_YEAR: (self._now.year, None)}
        self._earliest_known = False
        self._earliest = None
        for period in PERIODS:
            if period in _NAVIGABLE_PERIODS:
                prev_btn = QPushButton("‹")
                prev_btn.setObjectName("HomePeriodNavArrow")
                prev_btn.setCursor(Qt.PointingHandCursor)
                prev_btn.clicked.connect(lambda _c, p=period: self._step(p, -1))
                layout.addWidget(prev_btn)
                self._prev_buttons[period] = prev_btn
            button = QPushButton(_PERIOD_LABELS[period])
            button.setObjectName("HomePeriodTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self._group.addButton(button)
            self.buttons_by_period[period] = button
            layout.addWidget(button)
            if period in _NAVIGABLE_PERIODS:
                next_btn = QPushButton("›")
                next_btn.setObjectName("HomePeriodNavArrow")
                next_btn.setCursor(Qt.PointingHandCursor)
                next_btn.clicked.connect(lambda _c, p=period: self._step(p, 1))
                layout.addWidget(next_btn)
                self._next_buttons[period] = next_btn
        layout.addStretch(1)
        self.buttons_by_period[PERIOD_WEEK].setChecked(True)
        self._group.buttonClicked.connect(self._on_mode_clicked)
        self._refresh_labels()

    def _on_mode_clicked(self, _button):
        self._refresh_labels()
        self.periodChanged.emit()

    def _step(self, period, delta):
        year, month = self._position[period]
        new_year, new_month = self._stepped(period, year, month, delta)
        if not self._in_bounds(period, new_year, new_month):
            return
        self._position[period] = (new_year, new_month)
        self._refresh_labels()
        self.periodChanged.emit()

    def _stepped(self, period, year, month, delta):
        if period == PERIOD_MONTH:
            month += delta
            if month < 1:
                return year - 1, 12
            if month > 12:
                return year + 1, 1
            return year, month
        return year + delta, None

    def _in_bounds(self, period, year, month):
        if period == PERIOD_MONTH:
            if (year, month) > (self._now.year, self._now.month):
                return False
        elif year > self._now.year:
            return False
        if not self._earliest_known:
            return True
        if self._earliest is None:
            return False
        if period == PERIOD_MONTH:
            return (year, month) >= (self._earliest.year, self._earliest.month)
        return year >= self._earliest.year

    def _refresh_labels(self):
        for period in _NAVIGABLE_PERIODS:
            selected = self.buttons_by_period[period].isChecked()
            year, month = self._position[period]
            if selected:
                label = (datetime(year, month, 1).strftime(self._MONTH_FORMAT)
                         if period == PERIOD_MONTH else str(year))
            else:
                label = _PERIOD_LABELS[period]
            self.buttons_by_period[period].setText(label)
            self._prev_buttons[period].setVisible(selected)
            self._next_buttons[period].setVisible(selected)
            if selected:
                prev_pos = self._stepped(period, year, month, -1)
                next_pos = self._stepped(period, year, month, 1)
                self._prev_buttons[period].setEnabled(self._in_bounds(period, *prev_pos))
                self._next_buttons[period].setEnabled(self._in_bounds(period, *next_pos))

    def set_earliest_play_at(self, epoch_seconds):
        self._earliest_known = True
        self._earliest = (None if epoch_seconds is None
                          else datetime.fromtimestamp(epoch_seconds))
        self._refresh_labels()

    def current(self):
        for period, button in self.buttons_by_period.items():
            if button.isChecked():
                return period
        return PERIOD_WEEK

    def current_position(self):
        mode = self.current()
        if mode in self._position:
            year, month = self._position[mode]
            return mode, year, month
        return mode, None, None


_METRIC_LABELS = {METRIC_PLAYS: "Plays", METRIC_TIME: "Time"}


class _MetricToggle(QWidget):

    metricChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons_by_metric = {}
        for metric in RECAP_METRICS:
            button = QPushButton(_METRIC_LABELS[metric])
            button.setObjectName("HomePeriodTab")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self._group.addButton(button)
            self.buttons_by_metric[metric] = button
            layout.addWidget(button)
        self.buttons_by_metric[METRIC_PLAYS].setChecked(True)
        self._group.buttonClicked.connect(lambda _b: self.metricChanged.emit())

    def current(self):
        for metric, button in self.buttons_by_metric.items():
            if button.isChecked():
                return metric
        return METRIC_PLAYS

    def set_current(self, metric):
        if metric not in self.buttons_by_metric:
            metric = METRIC_PLAYS
        self.buttons_by_metric[metric].setChecked(True)


_EMPTY_TEXT = "Nothing played yet"


class _RankedRowDelegate(QStyledItemDelegate):

    ROW_H = 56
    THUMB = 40
    RANK_W = 22
    _SUBTITLE_PT_DELTA = -1.5
    _SUBTITLE_PX_DELTA = -2
    _NOW_PLAYING_GLYPH_SIZE = 18
    _NOW_PLAYING_GAP = 10

    def __init__(self, round_thumb=False, is_tracks=False, parent=None):
        super().__init__(parent)
        self._round_thumb = round_thumb
        self._is_tracks = is_tracks
        self._now_playing_track_id = None
        self._now_playing_glyph = render_icon(
            "waveform", theme.BRAND, self._NOW_PLAYING_GLYPH_SIZE)
        self._thumb_cache = {}

    def set_now_playing(self, track_id):
        if track_id == self._now_playing_track_id:
            return
        self._now_playing_track_id = track_id

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.ROW_H)
        return size

    def paint(self, painter, option, index):
        painter.save()
        if option.state & option.state.__class__.State_MouseOver:
            painter.fillRect(option.rect, QColor(theme.SURFACE_ALT))

        rank_rect = QRectF(option.rect.left() + 12, option.rect.top(),
                           self.RANK_W, option.rect.height())
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(rank_rect, Qt.AlignVCenter | Qt.AlignRight,
                         str(index.row() + 1))

        thumb_x = rank_rect.right() + 10
        thumb_y = option.rect.top() + (option.rect.height() - self.THUMB) / 2
        painter.drawPixmap(int(thumb_x), int(thumb_y),
                           self._thumbnail(index.data(EntryModel.ArtIdsRole) or ()))
        now_playing = (self._is_tracks and self._now_playing_track_id is not None
                      and index.data(EntryModel.KeyRole) == self._now_playing_track_id)

        base_font = painter.font()
        painter.setFont(base_font)

        count = index.data(EntryModel.CountRole) or ""
        count_w = painter.fontMetrics().horizontalAdvance(count) + 12
        count_left = option.rect.right() - count_w
        glyph_reserve = (self._NOW_PLAYING_GLYPH_SIZE + self._NOW_PLAYING_GAP
                         if now_playing else 0)
        text_left = thumb_x + self.THUMB + 10
        text_right = count_left - glyph_reserve
        text_w = max(0.0, text_right - text_left)

        title = index.data(EntryModel.LabelRole) or ""
        subtitle = index.data(EntryModel.SublabelRole) or ""
        if subtitle:
            half = option.rect.height() / 2
            title_rect = QRectF(text_left, option.rect.top(), text_w, half)
            sub_rect = QRectF(text_left, option.rect.top() + half, text_w, half)
        else:
            title_rect = QRectF(text_left, option.rect.top(), text_w, option.rect.height())
            sub_rect = None

        painter.setFont(base_font)
        painter.setPen(QColor(theme.TEXT))
        elided_title = painter.fontMetrics().elidedText(title, Qt.ElideRight, int(text_w))
        painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, elided_title)

        if sub_rect is not None:
            sub_font = QFont(base_font)
            self._shrink(sub_font)
            painter.setFont(sub_font)
            painter.setPen(QColor(theme.TEXT_MUTED))
            elided_sub = painter.fontMetrics().elidedText(subtitle, Qt.ElideRight, int(text_w))
            painter.drawText(sub_rect, Qt.AlignVCenter | Qt.AlignLeft, elided_sub)
            painter.setFont(base_font)

        if now_playing:
            glyph_x = count_left - self._NOW_PLAYING_GAP - self._NOW_PLAYING_GLYPH_SIZE
            glyph_y = (option.rect.top()
                      + (option.rect.height() - self._NOW_PLAYING_GLYPH_SIZE) / 2)
            painter.drawPixmap(int(glyph_x), int(glyph_y), self._now_playing_glyph)

        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(QRectF(count_left, option.rect.top(), count_w - 12, option.rect.height()),
                         Qt.AlignVCenter | Qt.AlignRight, count)
        painter.restore()

    def _thumbnail(self, art_ids):
        radius = self.THUMB / 2 if self._round_thumb else 0
        if art_ids:
            cached = self._thumb_cache.get(art_ids[0])
            if cached is not None:
                return cached
            pixmap = QPixmap(locations.art_path(art_ids[0]))
            if not pixmap.isNull():
                thumb = rounded(pixmap, self.THUMB, radius=radius)
                self._thumb_cache[art_ids[0]] = thumb
                return thumb
        return placeholder(self.THUMB, radius=radius, glyph=16)

    def _shrink(self, font):
        if font.pixelSize() > 0:
            font.setPixelSize(max(1, font.pixelSize() + self._SUBTITLE_PX_DELTA))
        else:
            font.setPointSizeF(max(1.0, font.pointSizeF() + self._SUBTITLE_PT_DELTA))


class _NoScrollListView(QListView):

    def wheelEvent(self, event):
        event.ignore()


class _Section(QWidget):

    activated = Signal(object)
    contextMenuRequested = Signal(object, QPoint)

    def __init__(self, title, round_thumb=False, is_tracks=False, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 16)
        layout.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("HomeSectionTitle")
        layout.addWidget(heading)

        self.model = EntryModel(self)
        self.view = _NoScrollListView()
        self.view.setObjectName("HomeSectionList")
        self.view.setModel(self.model)
        self._delegate = _RankedRowDelegate(round_thumb=round_thumb,
                                            is_tracks=is_tracks, parent=self)
        self.view.setItemDelegate(self._delegate)
        self.view.setSelectionMode(QListView.NoSelection)
        self.view.setFocusPolicy(Qt.NoFocus)
        self.view.setMouseTracking(True)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.clicked.connect(self._on_clicked)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.view)

        self.empty_label = QLabel(_EMPTY_TEXT)
        self.empty_label.setObjectName("HomeSectionEmpty")
        layout.addWidget(self.empty_label)
        self.set_entries([])

    def set_entries(self, entries):
        self.model.set_entries(entries)
        empty = not entries
        self.view.setVisible(not empty)
        self.empty_label.setVisible(empty)
        self.view.setFixedHeight(self.model.rowCount() * _RankedRowDelegate.ROW_H)

    def set_now_playing(self, track_id):
        self._delegate.set_now_playing(track_id)
        self.view.viewport().update()

    def _on_clicked(self, index):
        key = index.data(EntryModel.KeyRole)
        if key is not None:
            self.activated.emit(key)

    def _on_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        key = index.data(EntryModel.KeyRole)
        if key is not None:
            self.contextMenuRequested.emit(
                key, self.view.viewport().mapToGlobal(pos))


class _ShelfView(_TileView):

    def wheelEvent(self, event):
        event.ignore()


class _ShelfSection(QWidget):

    activated = Signal(object)
    playRequested = Signal(object)
    contextMenuRequested = Signal(object, QPoint)

    def __init__(self, title, empty_text, list_name, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 24)
        layout.setSpacing(6)
        self.heading_row = QHBoxLayout()
        self.heading_row.setContentsMargins(0, 0, 0, 0)
        self.heading_row.setSpacing(6)
        heading = QLabel(title)
        heading.setObjectName("HomeSectionTitle")
        self.heading_row.addWidget(heading)
        self.heading_row.addStretch(1)
        layout.addLayout(self.heading_row)

        self.model = EntryModel(self)
        self.view = _ShelfView()
        self.view.setObjectName(list_name)
        self.view.setModel(self.model)
        self.view.setViewMode(QListView.IconMode)
        self.view.setFlow(QListView.LeftToRight)
        self.view.setWrapping(False)
        self.view.setResizeMode(QListView.Fixed)
        self.view.setMovement(QListView.Static)
        self.view.setUniformItemSizes(True)
        self.view.setGridSize(QSize(TILE_W + GRID_SPACING, TILE_H + GRID_SPACING))
        self.view.setSelectionMode(QAbstractItemView.NoSelection)
        self.view.setFocusPolicy(Qt.NoFocus)
        self.view.setMouseTracking(True)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFixedHeight(TILE_H + GRID_SPACING)
        self._delegate = _ThumbnailDelegate(self)
        self.view.setItemDelegate(self._delegate)
        self.view.clicked.connect(self._on_clicked)
        self.view.playRequested.connect(self.playRequested)
        self.view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.view)

        self.empty_label = QLabel(empty_text)
        self.empty_label.setObjectName("HomeSectionEmpty")
        layout.addWidget(self.empty_label)
        self.set_entries([])

    def set_entries(self, entries):
        self.model.set_entries(entries)
        empty = not entries
        self.view.setVisible(not empty)
        self.empty_label.setVisible(empty)

    def _on_clicked(self, index):
        key = index.data(EntryModel.KeyRole)
        if key is not None:
            self.activated.emit(key)

    def _on_context_menu(self, pos):
        index = self.view.indexAt(pos)
        if not index.isValid():
            return
        key = index.data(EntryModel.KeyRole)
        if key is not None:
            self.contextMenuRequested.emit(
                key, self.view.viewport().mapToGlobal(pos))


class _LastAddedSection(_ShelfSection):

    def __init__(self, parent=None):
        super().__init__("LAST ADDED", "Nothing added yet", "HomeLastAddedList",
                         parent)


class _FavoritesSection(_ShelfSection):

    shuffleRequested = Signal()

    def __init__(self, parent=None):
        super().__init__("FAVORITES", "No favorites yet", "HomeFavoritesList",
                         parent)
        self.shuffle_button = IconButton("shuffle", "Shuffle favorites",
                                         icon_size=16, diameter=24,
                                         pill_hover=False)
        self.shuffle_button.clicked.connect(self.shuffleRequested)
        self.heading_row.insertWidget(1, self.shuffle_button)
        self.shuffle_button.setVisible(False)

    def set_entries(self, entries):
        super().set_entries(entries)
        button = getattr(self, "shuffle_button", None)
        if button is not None:
            button.setVisible(bool(entries))


class HomePage(QWidget):

    periodChanged = Signal()
    metricChanged = Signal()
    trackActivated = Signal(object)
    albumActivated = Signal(object)
    artistActivated = Signal(object)
    lastAddedActivated = Signal(object)
    lastAddedContextMenuRequested = Signal(object, QPoint)
    trackContextMenuRequested = Signal(object, QPoint)
    albumContextMenuRequested = Signal(object, QPoint)
    artistContextMenuRequested = Signal(object, QPoint)
    favoriteActivated = Signal(object)
    favoritePlayRequested = Signal(object)
    lastAddedPlayRequested = Signal(object)
    favoritesShuffleRequested = Signal()
    favoriteContextMenuRequested = Signal(object, QPoint)

    def __init__(self, parent=None, now=None):
        super().__init__(parent)
        self.setObjectName("HomePage")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(4)

        self.last_added_section = _LastAddedSection(content)
        self.last_added_section.activated.connect(self.lastAddedActivated)
        self.last_added_section.playRequested.connect(self.lastAddedPlayRequested)
        self.last_added_section.contextMenuRequested.connect(
            self.lastAddedContextMenuRequested)
        layout.addWidget(self.last_added_section)

        self.favorites_section = _FavoritesSection(content)
        self.favorites_section.activated.connect(self.favoriteActivated)
        self.favorites_section.playRequested.connect(self.favoritePlayRequested)
        self.favorites_section.shuffleRequested.connect(self.favoritesShuffleRequested)
        self.favorites_section.contextMenuRequested.connect(
            self.favoriteContextMenuRequested)
        layout.addWidget(self.favorites_section)

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(0, 0, 0, 0)
        self.tabs = _PeriodTabs(content, now=now)
        self.tabs.periodChanged.connect(self.periodChanged)
        tabs_row.addWidget(self.tabs, 1)
        self.metric_toggle = _MetricToggle(content)
        self.metric_toggle.metricChanged.connect(self.metricChanged)
        tabs_row.addWidget(self.metric_toggle)
        layout.addLayout(tabs_row)

        self.stat_label = QLabel("")
        self.stat_label.setObjectName("HomeStatTile")
        layout.addWidget(self.stat_label)

        self.tracks_section = _Section("TOP TRACKS", round_thumb=False, is_tracks=True)
        self.albums_section = _Section("TOP ALBUMS", round_thumb=False)
        self.artists_section = _Section("TOP ARTISTS", round_thumb=True)
        self.tracks_section.activated.connect(self.trackActivated)
        self.albums_section.activated.connect(self.albumActivated)
        self.artists_section.activated.connect(self.artistActivated)
        self.tracks_section.contextMenuRequested.connect(self.trackContextMenuRequested)
        self.albums_section.contextMenuRequested.connect(self.albumContextMenuRequested)
        self.artists_section.contextMenuRequested.connect(self.artistContextMenuRequested)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(24)
        columns.addWidget(self.tracks_section, 1, Qt.AlignTop)
        columns.addWidget(self.albums_section, 1, Qt.AlignTop)
        columns.addWidget(self.artists_section, 1, Qt.AlignTop)
        layout.addLayout(columns)
        layout.addStretch(1)

        self.scroll_area = QScrollArea()
        self.scroll_area.setObjectName("HomeScrollArea")
        self.scroll_area.setFrameShape(QScrollArea.NoFrame)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll_area.setWidget(content)
        outer.addWidget(self.scroll_area)

    def current_period(self):
        return self.tabs.current()

    def current_bounds(self):
        mode, year, month = self.tabs.current_position()
        return bounds_for(mode, year=year, month=month)

    def current_metric(self):
        return self.metric_toggle.current()

    def set_metric(self, metric):
        self.metric_toggle.set_current(metric)

    def set_earliest_play_at(self, epoch_seconds):
        self.tabs.set_earliest_play_at(epoch_seconds)

    def set_last_added(self, entries):
        self.last_added_section.set_entries(entries)

    def set_favorites(self, entries):
        self.favorites_section.set_entries(entries)

    def set_data(self, total_seconds, top_tracks, top_albums, top_artists):
        self.stat_label.setText(format_listened(total_seconds) + " listened")
        self.tracks_section.set_entries(top_tracks)
        self.albums_section.set_entries(top_albums)
        self.artists_section.set_entries(top_artists)

    def set_now_playing(self, track_id):
        self.tracks_section.set_now_playing(track_id)
