
from PySide6.QtCore import QModelIndex, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QListView, QPushButton,
    QSplitter, QStackedWidget, QStyledItemDelegate,
    QVBoxLayout, QWidget,
)

from waon.library import locations
from waon.ui import motion
from waon.ui import theme
from waon.ui.browse_models import EntryModel, TrackListModel
from waon.ui.cover_art import placeholder, rounded
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import IconButton, render_icon
from waon.ui.popup_menu import PopupMenu

_LIST_MIN_W = 200
_DETAIL_MIN_W = 260
_SORT_FIELD_LABELS = {
    "name": "Name", "songs": "Number of Songs", "albums": "Number of Albums",
    "duration": "Duration", "year": "Year", "artist": "Artist",
    "title": "Title", "album": "Album", "track_no": "Track Number",
    "position": "Playlist Order",
    "added": "Date Added", "last_played": "Last Played", "plays": "Plays",
    "favorited": "Date Favorited",
}


def _detail_title(name, count):
    suffix = "1 track" if count == 1 else "{} tracks".format(count)
    return "{} • {}".format(name, suffix)


_TREE_BASE_INSET = 16
_INDENT_STEP = 20
_CHEVRON_SIZE = 14
_CHEVRON_GAP = 6


def _folder_chevron_rect(row_rect, depth):
    left = row_rect.left() + _TREE_BASE_INSET + depth * _INDENT_STEP
    y = row_rect.top() + (row_rect.height() - _CHEVRON_SIZE) // 2
    return QRect(left, y, _CHEVRON_SIZE, _CHEVRON_SIZE)


_CHECKBOX_SIZE = 18
_CHECKBOX_GAP = 10


def _checkbox_rect(row_rect):
    y = row_rect.top() + (row_rect.height() - _CHECKBOX_SIZE) // 2
    return QRect(row_rect.left() + 16, y, _CHECKBOX_SIZE, _CHECKBOX_SIZE)


def _checkbox_reserve(index):
    return (_CHECKBOX_SIZE + _CHECKBOX_GAP) if index.model().is_selection_mode() else 0


class _TwoColumnDelegate(QStyledItemDelegate):

    ROW_H = 40

    def __init__(self, secondary_role, parent=None):
        super().__init__(parent)
        self._secondary_role = secondary_role

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(self.ROW_H)
        size.setWidth(0)
        return size

    def paint(self, painter, option, index):
        painter.save()
        selected = (not index.model().is_selection_mode()
                   and bool(option.state & option.state.__class__.State_Selected))
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.BRAND_SOFT))
            painter.drawRect(option.rect.adjusted(6, 2, -6, -2))
        elif option.state & option.state.__class__.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.SURFACE_ALT))
            painter.drawRect(option.rect.adjusted(6, 2, -6, -2))

        self._paint_checkbox_if_needed(painter, option, index)

        rect = self._text_rect(painter, option, index)
        secondary = index.data(self._secondary_role) or ""
        font = QFont(option.font)
        painter.setFont(font)
        secondary_w = painter.fontMetrics().horizontalAdvance(secondary) + 12

        painter.setPen(QColor(theme.TEXT))
        primary_rect = rect.adjusted(0, 0, -secondary_w, 0)
        primary = painter.fontMetrics().elidedText(
            index.data(Qt.DisplayRole) or "", Qt.ElideRight, primary_rect.width())
        painter.drawText(primary_rect, Qt.AlignLeft | Qt.AlignVCenter, primary)

        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, secondary)
        painter.restore()

    def _paint_checkbox_if_needed(self, painter, option, index):
        if not index.model().is_selection_mode():
            return
        checked = bool(index.data(index.model().CheckedRole))
        box = _checkbox_rect(option.rect)
        painter.drawPixmap(box.topLeft(), render_icon(
            "check-square" if checked else "square", theme.ICON, _CHECKBOX_SIZE))

    def _text_rect(self, painter, option, index):
        model = index.model()
        content_rect = option.rect.adjusted(_checkbox_reserve(index), 0, 0, 0)
        if not (isinstance(model, EntryModel) and model.has_tree_rows()):
            return content_rect.adjusted(16, 0, -16, 0)
        depth = index.data(EntryModel.DepthRole) or 0
        chevron_rect = _folder_chevron_rect(content_rect, depth)
        if index.data(EntryModel.HasChildrenRole):
            icon_name = ("chevron-down" if index.data(EntryModel.IsExpandedRole)
                        else "chevron-right")
            painter.drawPixmap(chevron_rect.topLeft(),
                               render_icon(icon_name, theme.ICON, _CHEVRON_SIZE))
        left = chevron_rect.left() + _CHEVRON_SIZE + _CHEVRON_GAP
        return QRect(left, option.rect.top(),
                    option.rect.right() - 16 - left, option.rect.height())


_THUMB = 36
_THUMB_GAP = 8
_NOW_PLAYING_GLYPH_SIZE = 18
_NOW_PLAYING_GAP = 6

_HEADER_ICON_SIZE = 18
_HEADER_ICON_GAP = 6


def _header_icon_rects(row_rect):
    inset_right = row_rect.adjusted(16, 0, -16, 0).right()
    y = row_rect.top() + (row_rect.height() - _HEADER_ICON_SIZE) // 2
    collapse_left = inset_right - _HEADER_ICON_SIZE
    play_left = collapse_left - _HEADER_ICON_GAP - _HEADER_ICON_SIZE
    play_rect = QRect(play_left, y, _HEADER_ICON_SIZE, _HEADER_ICON_SIZE)
    collapse_rect = QRect(collapse_left, y, _HEADER_ICON_SIZE, _HEADER_ICON_SIZE)
    return play_rect, collapse_rect


class _TrackDelegate(_TwoColumnDelegate):

    TRACK_ROW_H = 52
    _LINE_GAP = 1

    def __init__(self, secondary_role, parent=None):
        super().__init__(secondary_role, parent)
        self._art_cache = {}
        self._placeholder = placeholder(_THUMB, radius=0)
        self._now_playing_glyph = render_icon(
            "waveform", theme.BRAND, _NOW_PLAYING_GLYPH_SIZE)

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        if not index.data(TrackListModel.IsHeaderRole):
            size.setHeight(self.TRACK_ROW_H)
        return size

    def paint(self, painter, option, index):
        if index.data(TrackListModel.IsHeaderRole):
            self._paint_header(painter, option, index)
            return
        painter.save()
        selected = (not index.model().is_selection_mode()
                   and bool(option.state & option.state.__class__.State_Selected))
        if selected:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.BRAND_SOFT))
            painter.drawRect(option.rect.adjusted(6, 2, -6, -2))
        elif option.state & option.state.__class__.State_MouseOver:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(theme.SURFACE_ALT))
            painter.drawRect(option.rect.adjusted(6, 2, -6, -2))

        self._paint_checkbox_if_needed(painter, option, index)

        rect = self._text_rect(painter, option, index)
        secondary = index.data(self._secondary_role) or ""
        font = QFont(option.font)
        painter.setFont(font)
        secondary_w = painter.fontMetrics().horizontalAdvance(secondary) + 12

        now_playing = bool(index.data(TrackListModel.NowPlayingRole))
        glyph_reserve = (_NOW_PLAYING_GLYPH_SIZE + _NOW_PLAYING_GAP
                         if now_playing else 0)

        primary_rect = rect.adjusted(0, 0, -secondary_w - glyph_reserve, 0)
        self._paint_title_and_artist(painter, primary_rect, font, index)
        painter.setFont(font)

        if now_playing:
            glyph_x = rect.right() - secondary_w - _NOW_PLAYING_GLYPH_SIZE
            glyph_y = (option.rect.top()
                      + (option.rect.height() - _NOW_PLAYING_GLYPH_SIZE) // 2)
            painter.drawPixmap(glyph_x, glyph_y, self._now_playing_glyph)

        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(rect, Qt.AlignRight | Qt.AlignVCenter, secondary)
        painter.restore()

    def _paint_title_and_artist(self, painter, rect, font, index):
        title = index.data(Qt.DisplayRole) or ""
        artist = index.data(TrackListModel.SubtitleRole) or ""
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        if not artist:
            painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter,
                             painter.fontMetrics().elidedText(
                                 title, Qt.ElideRight, rect.width()))
            return
        artist_font = QFont(font)
        if artist_font.pixelSize() > 0:
            artist_font.setPixelSize(max(1, artist_font.pixelSize() - 2))
        else:
            artist_font.setPointSizeF(max(1.0, artist_font.pointSizeF() - 1.5))
        title_h = painter.fontMetrics().height()
        painter.setFont(artist_font)
        artist_h = painter.fontMetrics().height()
        top = rect.top() + (rect.height() - title_h - self._LINE_GAP - artist_h) // 2
        title_rect = QRect(rect.left(), top, rect.width(), title_h)
        artist_rect = QRect(rect.left(), top + title_h + self._LINE_GAP,
                            rect.width(), artist_h)
        painter.setPen(QColor(theme.TEXT_MUTED))
        painter.drawText(artist_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(
                             artist, Qt.ElideRight, rect.width()))
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter,
                         painter.fontMetrics().elidedText(
                             title, Qt.ElideRight, rect.width()))

    def _paint_header(self, painter, option, index):
        painter.save()
        rect = option.rect.adjusted(_checkbox_reserve(index) + 16, 0, -16, 0)
        font = QFont(option.font)
        if index.data(TrackListModel.IsSectionRole):
            if index.row() > 0:
                rule_y = option.rect.top() + 14
                painter.setPen(QPen(QColor(theme.BRAND), 2))
                painter.drawLine(rect.left(), rule_y, rect.right(), rule_y)
                rect = QRect(rect.left(), rule_y + 7, rect.width(),
                            option.rect.bottom() - (rule_y + 7) + 1)
            if font.pointSize() > 0:
                font.setPointSize(font.pointSize() - 1)
            else:
                font.setPixelSize(max(1, font.pixelSize() - 1))
            font.setWeight(QFont.DemiBold)
            painter.setPen(QColor(theme.TEXT_MUTED))
        else:
            font.setWeight(QFont.DemiBold)
            painter.setPen(QColor(theme.BRAND))
            collapse_icon_name = ("caret-circle-double-down"
                                 if index.data(TrackListModel.IsCollapsedRole)
                                 else "caret-circle-double-up")
            play_rect, collapse_rect = _header_icon_rects(option.rect)
            painter.drawPixmap(collapse_rect.topLeft(),
                               render_icon(collapse_icon_name, theme.BRAND,
                                          _HEADER_ICON_SIZE))
            painter.drawPixmap(play_rect.topLeft(),
                               render_icon("play-circle", theme.BRAND,
                                          _HEADER_ICON_SIZE))
            rect.setRight(play_rect.left() - _HEADER_ICON_GAP)
        painter.setFont(font)
        text = painter.fontMetrics().elidedText(
            index.data(Qt.DisplayRole) or "", Qt.ElideRight, rect.width())
        painter.drawText(rect, Qt.AlignLeft | Qt.AlignVCenter, text)
        painter.restore()

    def _text_rect(self, painter, option, index):
        content_rect = option.rect.adjusted(_checkbox_reserve(index), 0, 0, 0)
        art_rect = QRect(
            content_rect.left() + 16,
            option.rect.top() + (option.rect.height() - _THUMB) // 2,
            _THUMB, _THUMB)
        painter.drawPixmap(art_rect, self._art_pixmap(index))
        left = art_rect.right() + _THUMB_GAP
        return QRect(left, option.rect.top(),
                    option.rect.right() - 16 - left, option.rect.height())

    def _art_pixmap(self, index):
        track = index.data(TrackListModel.TrackRole)
        album_id = track.album_id if track else None
        if not album_id:
            return self._placeholder
        cached = self._art_cache.get(album_id)
        if cached is not None:
            return cached
        pixmap = QPixmap(locations.art_path(album_id))
        if pixmap.isNull():
            return self._placeholder
        result = rounded(pixmap, _THUMB, radius=0)
        self._art_cache[album_id] = result
        return result


class _HoverScrollView(QListView):

    def enterEvent(self, event):
        self._set_hovering(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._set_hovering(False)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        had_current = self.currentIndex().isValid()
        selection = self.selectionModel()
        if had_current or selection is None:
            super().focusInEvent(event)
            return
        blocked = selection.blockSignals(True)
        try:
            super().focusInEvent(event)
            if self.currentIndex().isValid():
                selection.clear()
        finally:
            selection.blockSignals(blocked)

    def mousePressEvent(self, event):
        if (event.button() == Qt.LeftButton
                and not self.indexAt(event.position().toPoint()).isValid()):
            self.selectionModel().clear()
        super().mousePressEvent(event)

    def _set_hovering(self, value):
        for bar in (self.verticalScrollBar(), self.horizontalScrollBar()):
            bar.setProperty("hovering", value)
            bar.style().unpolish(bar)
            bar.style().polish(bar)


class _DetailTrackView(_HoverScrollView):

    albumPlayIconClicked = Signal(QModelIndex)
    albumCollapseIconClicked = Signal(QModelIndex)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if (event.button() == Qt.LeftButton and index.isValid()
                and self.model().is_selection_mode()
                and not index.data(TrackListModel.IsHeaderRole)):
            self.model().toggle_checked(index.row())
            return
        if (event.button() == Qt.LeftButton and index.isValid()
                and index.data(TrackListModel.IsHeaderRole)
                and not index.data(TrackListModel.IsSectionRole)):
            play_rect, collapse_rect = _header_icon_rects(self.visualRect(index))
            if play_rect.contains(pos):
                self.albumPlayIconClicked.emit(index)
                return
            if collapse_rect.contains(pos):
                self.albumCollapseIconClicked.emit(index)
                return
        super().mousePressEvent(event)

    def dropEvent(self, event):
        source_row = self.currentIndex().row()
        if source_row < 0:
            event.ignore()
            return
        target_index = self.indexAt(event.position().toPoint())
        target_row = (target_index.row() if target_index.isValid()
                     else self.model().rowCount() - 1)
        if target_row == source_row:
            event.ignore()
            return
        resolved = self.model().move_row(source_row, target_row)
        self.setCurrentIndex(self.model().index(resolved, 0))
        event.acceptProposedAction()


class _ListPaneView(_HoverScrollView):

    folderChevronClicked = Signal(QModelIndex)
    playRequested = Signal(object)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            key = playable_key(self, self.currentIndex())
            if key is not None:
                self.playRequested.emit(key)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if (event.button() == Qt.LeftButton and index.isValid()
                and self.model().is_selection_mode()):
            self.model().toggle_checked(index.data(EntryModel.KeyRole))
            return
        if (event.button() == Qt.LeftButton and index.isValid()
                and index.data(EntryModel.HasChildrenRole)):
            chevron_rect = _folder_chevron_rect(
                self.visualRect(index), index.data(EntryModel.DepthRole) or 0)
            if chevron_rect.contains(pos):
                self.folderChevronClicked.emit(index)
                return
        super().mousePressEvent(event)


def playable_key(view, index):
    if not index.isValid() or not index.data(EntryModel.PlayableRole):
        return None
    if view.model().is_selection_mode():
        return None
    return index.data(EntryModel.KeyRole)


def _pane_view(object_name, secondary_role, delegate_cls=_TwoColumnDelegate,
               view_cls=_HoverScrollView):
    view = view_cls()
    view.setObjectName(object_name)
    view.setUniformItemSizes(True)
    view.setSelectionMode(QAbstractItemView.SingleSelection)
    view.setEditTriggers(QAbstractItemView.NoEditTriggers)
    view.setMouseTracking(True)
    view.setItemDelegate(delegate_cls(secondary_role, view))
    return view


def make_track_list_view(object_name):
    view = _pane_view(object_name, TrackListModel.DurationRole,
                      delegate_cls=_TrackDelegate, view_cls=_DetailTrackView)
    view.setUniformItemSizes(False)
    view.setDragEnabled(True)
    view.setAcceptDrops(True)
    view.setDropIndicatorShown(True)
    view.setDragDropMode(QAbstractItemView.InternalMove)
    view.setDefaultDropAction(Qt.MoveAction)
    view.setContextMenuPolicy(Qt.CustomContextMenu)
    return view


class BrowsePanes(QWidget):

    entrySelected = Signal(object)
    entryActivated = Signal(object)
    trackActivated = Signal(int)
    albumActivated = Signal(object)
    showFeaturedArtistsToggled = Signal(bool)
    sortChanged = Signal(str, str)
    detailSortChanged = Signal(str, str)
    detailGroupToggled = Signal(bool)
    showFeaturedTracksToggled = Signal(bool)
    entryContextMenuRequested = Signal(object, QPoint)
    trackContextMenuRequested = Signal(int, QPoint)
    albumContextMenuRequested = Signal(object, QPoint)
    importPlaylistsRequested = Signal()
    trackReordered = Signal()
    resumeQueueRequested = Signal()
    playAllRequested = Signal()
    shuffleAllRequested = Signal()
    periodChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._muted = False
        self._detail_key = None
        self.entry_model = EntryModel(self)
        self.track_model = TrackListModel(self)
        self._build()

    def _build(self):
        from waon.ui.browse_grid import ThumbnailGridView

        self.list_header = QLabel("")
        self.list_header.setObjectName("ListPaneHeader")
        self._sort_fields = ()
        self._sort_state = ("name", "asc")
        self._show_featured = False
        self.sort_button = IconButton("arrows-down-up", "Sort", icon_size=20,
                                      diameter=34, pill_hover=False)
        self.sort_button.setVisible(False)
        self.sort_button.clicked.connect(self._on_sort_clicked)
        self.filter_button = IconButton("eye-slash", "Show featured artists",
                                        icon_size=20, diameter=34, pill_hover=False)
        self.filter_button.setVisible(False)
        self.filter_button.clicked.connect(self._on_filter_clicked)
        self.import_button = IconButton("file-arrow-down", "Import playlists",
                                        icon_size=20, diameter=34,
                                        pill_hover=False)
        self.import_button.setVisible(False)
        self.import_button.clicked.connect(self.importPlaylistsRequested)
        self.select_button = IconButton("list-checks", "Select", icon_size=20,
                                        diameter=34, pill_hover=False)
        self.select_button.clicked.connect(self._on_list_select_clicked)
        self.list_header_row = QWidget()
        list_header_layout = QHBoxLayout(self.list_header_row)
        list_header_layout.setContentsMargins(0, 0, 0, 0)
        list_header_layout.setSpacing(0)
        list_header_layout.addWidget(self.list_header, 1)
        list_header_layout.addWidget(self.filter_button)
        list_header_layout.addWidget(self.import_button)
        list_header_layout.addWidget(self.sort_button)
        list_header_layout.addWidget(self.select_button)

        self.list_selection_label = QLabel("")
        self.list_selection_label.setObjectName("ListPaneHeader")
        self.list_select_all_button = IconButton(
            "selection-all", "Select all", icon_size=18, diameter=34,
            pill_hover=False)
        self.list_select_all_button.clicked.connect(
            lambda: self.entry_model.select_all())
        self.list_clear_selection_button = IconButton(
            "selection-slash", "Clear selection", icon_size=18, diameter=34,
            pill_hover=False)
        self.list_clear_selection_button.clicked.connect(
            lambda: self.entry_model.clear_checked())
        self.list_cancel_selection_button = IconButton(
            "close", "Cancel", icon_size=18, diameter=34, pill_hover=False)
        self.list_cancel_selection_button.clicked.connect(
            lambda: self.entry_model.set_selection_mode(False))
        self.list_selection_header_row = QWidget()
        self.list_selection_header_row.setVisible(False)
        selection_header_layout = QHBoxLayout(self.list_selection_header_row)
        selection_header_layout.setContentsMargins(0, 0, 0, 0)
        selection_header_layout.setSpacing(8)
        selection_header_layout.addWidget(self.list_selection_label, 1)
        selection_header_layout.addWidget(self.list_select_all_button)
        selection_header_layout.addWidget(self.list_clear_selection_button)
        selection_header_layout.addWidget(self.list_cancel_selection_button)

        self.entry_model.selectionChanged.connect(self._on_list_selection_changed)
        self.list_header_divider = QWidget()
        self.list_header_divider.setObjectName("ListHeaderDivider")
        self.list_header_divider.setFixedHeight(1)
        self.list_header_divider.setAttribute(Qt.WA_StyledBackground, True)
        self.list_view = _pane_view("ListPane", EntryModel.SublabelRole,
                                    view_cls=_ListPaneView)
        self.list_view.setModel(self.entry_model)

        self.grid_view = ThumbnailGridView()
        self.grid_view.setObjectName("GridPane")
        self.grid_view.setModel(self.entry_model)
        self.grid_view.setSelectionModel(self.list_view.selectionModel())

        self.list_view.selectionModel().currentChanged.connect(
            self._on_entry_changed)
        self.list_view.playRequested.connect(self.entryActivated)
        self.list_view.folderChevronClicked.connect(self._on_folder_chevron_clicked)
        self.grid_view.playRequested.connect(self.entryActivated)
        self.list_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(
            lambda pos: self._on_entry_context_menu(self.list_view, pos))
        self.grid_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.grid_view.customContextMenuRequested.connect(
            lambda pos: self._on_entry_context_menu(self.grid_view, pos))

        self.left_stack = QStackedWidget()
        self.left_stack.addWidget(self.list_view)
        self.left_stack.addWidget(self.grid_view)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self.list_header_row)
        left_layout.addWidget(self.list_selection_header_row)
        left_layout.addWidget(self.list_header_divider)
        left_layout.addWidget(self.left_stack, 1)

        self.detail_header = ElidedLabel("")
        self.detail_header.setObjectName("DetailPaneHeader")
        self._detail_tracks_key = object()
        self._detail_grouped = False
        self._detail_sort_fields = ()
        self._detail_sort_state = ("title", "asc")
        self._detail_show_featured = True
        self.detail_resume_button = IconButton(
            "play-circle", "Switch to this queue", icon_size=20,
            diameter=34, pill_hover=False)
        self.detail_resume_button.setVisible(False)
        self.detail_resume_button.clicked.connect(self.resumeQueueRequested)
        self._detail_period_options = ()
        self._detail_period_state = None
        self.detail_play_all_button = IconButton(
            "play-circle", "Play all", icon_size=20, diameter=34, pill_hover=False)
        self.detail_play_all_button.setVisible(False)
        self.detail_play_all_button.clicked.connect(self.playAllRequested)
        self.detail_shuffle_button = IconButton(
            "shuffle", "Shuffle", icon_size=20, diameter=34, pill_hover=False)
        self.detail_shuffle_button.setVisible(False)
        self.detail_shuffle_button.clicked.connect(self.shuffleAllRequested)
        self.detail_period_button = IconButton(
            "calendar", "Period", icon_size=20, diameter=34, pill_hover=False)
        self.detail_period_button.setVisible(False)
        self.detail_period_button.clicked.connect(self._on_detail_period_clicked)
        self.detail_group_button = IconButton("stack", "Group by Album", icon_size=20,
                                              diameter=34, pill_hover=False)
        self.detail_group_button.setVisible(False)
        self.detail_group_button.clicked.connect(self._on_detail_group_clicked)
        self.detail_sort_button = IconButton("arrows-down-up", "Sort", icon_size=20,
                                             diameter=34, pill_hover=False)
        self.detail_sort_button.setVisible(False)
        self.detail_sort_button.clicked.connect(self._on_detail_sort_clicked)
        self.detail_filter_button = IconButton("eye-slash", "Show featured on",
                                               icon_size=20, diameter=34,
                                               pill_hover=False)
        self.detail_filter_button.setVisible(False)
        self.detail_filter_button.clicked.connect(self._on_detail_filter_clicked)
        self.detail_select_button = IconButton("list-checks", "Select", icon_size=20,
                                               diameter=34, pill_hover=False)
        self.detail_select_button.clicked.connect(self._on_detail_select_clicked)
        self.detail_header_row = QWidget()
        detail_header_layout = QHBoxLayout(self.detail_header_row)
        detail_header_layout.setContentsMargins(0, 0, 0, 0)
        detail_header_layout.setSpacing(0)
        detail_header_layout.addWidget(self.detail_header, 1)
        detail_header_layout.addWidget(self.detail_resume_button)
        detail_header_layout.addWidget(self.detail_play_all_button)
        detail_header_layout.addWidget(self.detail_shuffle_button)
        detail_header_layout.addWidget(self.detail_group_button)
        detail_header_layout.addWidget(self.detail_filter_button)
        detail_header_layout.addWidget(self.detail_period_button)
        detail_header_layout.addWidget(self.detail_sort_button)
        detail_header_layout.addWidget(self.detail_select_button)

        self.detail_selection_label = QLabel("")
        self.detail_selection_label.setObjectName("DetailPaneHeader")
        self.detail_select_all_button = IconButton(
            "selection-all", "Select all", icon_size=18, diameter=34,
            pill_hover=False)
        self.detail_select_all_button.clicked.connect(
            lambda: self.track_model.select_all())
        self.detail_clear_selection_button = IconButton(
            "selection-slash", "Clear selection", icon_size=18, diameter=34,
            pill_hover=False)
        self.detail_clear_selection_button.clicked.connect(
            lambda: self.track_model.clear_checked())
        self.detail_cancel_selection_button = IconButton(
            "close", "Cancel", icon_size=18, diameter=34, pill_hover=False)
        self.detail_cancel_selection_button.clicked.connect(
            lambda: self.track_model.set_selection_mode(False))
        self.detail_selection_header_row = QWidget()
        self.detail_selection_header_row.setVisible(False)
        detail_selection_layout = QHBoxLayout(self.detail_selection_header_row)
        detail_selection_layout.setContentsMargins(0, 0, 0, 0)
        detail_selection_layout.setSpacing(8)
        detail_selection_layout.addWidget(self.detail_selection_label, 1)
        detail_selection_layout.addWidget(self.detail_select_all_button)
        detail_selection_layout.addWidget(self.detail_clear_selection_button)
        detail_selection_layout.addWidget(self.detail_cancel_selection_button)

        self.track_model.selectionChanged.connect(self._on_detail_selection_changed)
        self.detail_header_divider = QWidget()
        self.detail_header_divider.setObjectName("DetailHeaderDivider")
        self.detail_header_divider.setFixedHeight(1)
        self.detail_header_divider.setAttribute(Qt.WA_StyledBackground, True)
        self.detail_view = make_track_list_view("DetailPane")
        self.detail_view.setModel(self.track_model)
        self.track_model.orderChanged.connect(self.trackReordered)
        self.detail_view.activated.connect(self._on_detail_activated)
        self.detail_view.albumPlayIconClicked.connect(self._on_detail_play_icon_clicked)
        self.detail_view.albumCollapseIconClicked.connect(
            self._on_detail_collapse_icon_clicked)
        self.detail_view.customContextMenuRequested.connect(
            self._on_detail_context_menu)
        self.detail_empty = QLabel("Nothing here")
        self.detail_empty.setObjectName("PaneEmpty")
        self.detail_empty.setAlignment(Qt.AlignCenter)

        self.detail_pane_divider = QWidget()
        self.detail_pane_divider.setObjectName("DetailPaneDivider")
        self.detail_pane_divider.setFixedWidth(1)
        self.detail_pane_divider.setAttribute(Qt.WA_StyledBackground, True)

        detail_content = QWidget()
        detail_content_layout = QVBoxLayout(detail_content)
        detail_content_layout.setContentsMargins(0, 0, 0, 0)
        detail_content_layout.setSpacing(0)
        detail_content_layout.addWidget(self.detail_header_row)
        detail_content_layout.addWidget(self.detail_selection_header_row)
        detail_content_layout.addWidget(self.detail_header_divider)
        detail_content_layout.addWidget(self.detail_view, 1)
        detail_content_layout.addWidget(self.detail_empty, 1)

        right = QWidget()
        self.detail_panel = right
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self.detail_pane_divider)
        right_layout.addWidget(detail_content, 1)

        self.splitter = QSplitter(Qt.Horizontal)
        left.setMinimumWidth(_LIST_MIN_W)
        right.setMinimumWidth(_DETAIL_MIN_W)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(left)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([520, 380])

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self.set_tracks([], "")

    def _on_list_select_clicked(self):
        self.entry_model.set_selection_mode(True)

    def _on_list_selection_changed(self):
        on = self.entry_model.is_selection_mode()
        self.list_header_row.setVisible(not on)
        self.list_selection_header_row.setVisible(on)
        count = len(self.entry_model.checked_keys())
        self.list_selection_label.setText(
            "1 selected" if count == 1 else "{} selected".format(count))

    def _on_sort_clicked(self):
        menu = self._build_sort_menu()
        pos = self.sort_button.mapToGlobal(
            self.sort_button.rect().bottomLeft())
        menu.popup_at(pos)

    def _build_sort_menu(self):
        return self._build_field_sort_menu(
            self._sort_fields, self._sort_state, self.sortChanged)

    def _on_detail_sort_clicked(self):
        menu = self._build_detail_sort_menu()
        pos = self.detail_sort_button.mapToGlobal(
            self.detail_sort_button.rect().bottomLeft())
        menu.popup_at(pos)

    def _build_detail_sort_menu(self):
        return self._build_field_sort_menu(
            self._detail_sort_fields, self._detail_sort_state,
            self.detailSortChanged)

    def _on_detail_period_clicked(self):
        menu = self._build_period_menu()
        pos = self.detail_period_button.mapToGlobal(
            self.detail_period_button.rect().bottomLeft())
        menu.popup_at(pos)

    def _build_period_menu(self):
        menu = PopupMenu(parent=self)
        for period_id, label in self._detail_period_options:
            menu.add_action(None, label,
                            lambda p=period_id: self.periodChanged.emit(p),
                            checked=period_id == self._detail_period_state)
        return menu

    def _build_field_sort_menu(self, fields, state, changed_signal):
        active_field, active_direction = state
        menu = PopupMenu(parent=self)
        for field in fields:
            is_active = field == active_field
            if is_active:
                icon = ("sort-descending" if active_direction == "desc"
                       else "sort-ascending")
                next_direction = "asc" if active_direction == "desc" else "desc"
            else:
                icon = None
                next_direction = "asc"
            menu.add_action(
                icon, _SORT_FIELD_LABELS[field],
                lambda f=field, d=next_direction, sig=changed_signal:
                    sig.emit(f, d))
        return menu

    def _on_detail_select_clicked(self):
        self.track_model.set_selection_mode(True)

    def _on_detail_selection_changed(self):
        on = self.track_model.is_selection_mode()
        self.detail_header_row.setVisible(not on)
        self.detail_selection_header_row.setVisible(on)
        count = len(self.track_model.checked_tracks())
        self.detail_selection_label.setText(
            "1 selected" if count == 1 else "{} selected".format(count))

    def _on_detail_group_clicked(self):
        menu = self._build_detail_group_menu()
        pos = self.detail_group_button.mapToGlobal(
            self.detail_group_button.rect().bottomLeft())
        menu.popup_at(pos)

    def _build_detail_group_menu(self):
        menu = PopupMenu(parent=self)
        menu.add_action(
            None, "Group by Album",
            lambda: self._on_detail_group_toggled(not self._detail_grouped),
            checked=self._detail_grouped)
        menu.add_separator()
        menu.add_action(None, "Collapse all albums", self._on_collapse_all_clicked,
                        enabled=self._detail_grouped)
        menu.add_action(None, "Expand all albums", self._on_expand_all_clicked,
                        enabled=self._detail_grouped)
        return menu

    def _on_detail_group_toggled(self, checked):
        self._detail_grouped = checked
        self.detail_group_button.set_active(checked)
        self.detailGroupToggled.emit(checked)

    def _on_collapse_all_clicked(self):
        self.track_model.collapse_all()
        self._apply_collapse_view()

    def _on_expand_all_clicked(self):
        self.track_model.expand_all()
        self._apply_collapse_view()

    def _on_detail_collapse_icon_clicked(self, index):
        album_id = self.track_model.data(index, TrackListModel.AlbumIdRole)
        self.track_model.set_collapsed(
            album_id, not self.track_model.is_collapsed(album_id))
        self._apply_collapse_view()

    def _on_detail_play_icon_clicked(self, index):
        self.albumActivated.emit(self.track_model.tracks_for_header(index.row()))

    def _apply_collapse_view(self):
        for row in range(self.track_model.rowCount()):
            if self.track_model.is_header(row) and not self.track_model.is_section(row):
                index = self.track_model.index(row, 0)
                album_id = self.track_model.data(index, TrackListModel.AlbumIdRole)
                hidden = self.track_model.is_collapsed(album_id)
                for track_row in self.track_model.track_rows_for_header(row):
                    self.detail_view.setRowHidden(track_row, hidden)

    def _on_folder_chevron_clicked(self, index):
        entry = self.entry_model.entry_at(index.row())
        if entry is None:
            return
        self.entry_model.set_expanded(
            entry.key, not self.entry_model.is_expanded(entry.key))
        self._apply_folder_collapse_view()

    def _apply_folder_collapse_view(self):
        hidden_from_depth = None
        for row in range(self.entry_model.rowCount()):
            entry = self.entry_model.entry_at(row)
            if hidden_from_depth is not None and entry.depth > hidden_from_depth:
                self.list_view.setRowHidden(row, True)
                continue
            hidden_from_depth = None
            self.list_view.setRowHidden(row, False)
            if entry.has_children and not self.entry_model.is_expanded(entry.key):
                hidden_from_depth = entry.depth

    def _on_filter_clicked(self):
        self._on_filter_toggled(not self._show_featured)

    def _on_filter_toggled(self, checked):
        self._show_featured = checked
        self.filter_button.set_active(checked)
        self.filter_button.set_name("eye" if checked else "eye-slash")
        self.showFeaturedArtistsToggled.emit(checked)

    def _on_detail_filter_clicked(self):
        self._on_detail_filter_toggled(not self._detail_show_featured)

    def _on_detail_filter_toggled(self, checked):
        self._detail_show_featured = checked
        self.detail_filter_button.set_name("eye" if checked else "eye-slash")
        self.showFeaturedTracksToggled.emit(checked)

    def set_entries(self, entries, header, use_grid=False, show_featured=None,
                    show_import=False, round_thumbs=False, sort_fields=(),
                    sort_state=("name", "asc"), show_select=True, playable=True):
        previous_key = self.selected_key()
        self.list_header.setText(header)
        self._muted = True
        try:
            self.entry_model.set_playable(playable)
            self.entry_model.set_entries(entries)
        finally:
            self._muted = False
        self._apply_folder_collapse_view()
        self.left_stack.setCurrentWidget(self.grid_view if use_grid else self.list_view)
        self.grid_view.set_round_thumbs(round_thumbs)
        self._sort_fields = sort_fields
        self._sort_state = sort_state
        self.sort_button.setVisible(bool(sort_fields))
        self.filter_button.setVisible(show_featured is not None)
        if show_featured is not None:
            self._show_featured = show_featured
            self.filter_button.set_active(show_featured)
            self.filter_button.set_name("eye" if show_featured else "eye-slash")
        self.import_button.setVisible(show_import)
        self.select_button.setVisible(show_select)
        row = self.entry_model.row_of(previous_key) if previous_key is not None else -1
        if row >= 0:
            self.list_view.setCurrentIndex(self.entry_model.index(row, 0))
        else:
            self.set_tracks([], "")

    def set_tracks(self, tracks, header, grouped=False, featured_tracks=(),
                   featured_checked=True, sort_fields=(), sort_state=("title", "asc"),
                   show_group=False, show_filter=False, show_count=False,
                   album_years=None, reorderable=False, show_resume=False,
                   show_play_all=False, period_options=(), period_state=None,
                   empty_text="Nothing here"):
        if show_count:
            count = len(tracks) + len(featured_tracks)
            self.detail_header.setText(_detail_title(header, count))
        else:
            self.detail_header.setText(header)
        self.track_model.set_tracks(tracks, grouped=grouped,
                                    featured_tracks=featured_tracks,
                                    album_years=album_years)
        self.track_model.set_reorderable(reorderable)
        empty = self.track_model.rowCount() == 0
        self.detail_view.setVisible(not empty)
        self.detail_empty.setVisible(empty)
        self.detail_empty.setText(empty_text)
        self.detail_play_all_button.setVisible(show_play_all)
        self.detail_shuffle_button.setVisible(show_play_all)
        self.detail_play_all_button.setEnabled(not empty)
        self.detail_shuffle_button.setEnabled(not empty)
        self._detail_period_options = tuple(period_options)
        self._detail_period_state = period_state
        self.detail_period_button.setVisible(bool(period_options))
        current_key = self.selected_key()
        if current_key != self._detail_tracks_key:
            self._detail_tracks_key = current_key
            self.detail_view.scrollToTop()
            self.track_model.set_selection_mode(False)
        self._detail_grouped = grouped
        self._detail_sort_fields = sort_fields
        self._detail_sort_state = sort_state
        self._detail_show_featured = featured_checked
        self.detail_resume_button.setVisible(show_resume)
        self.detail_group_button.setVisible(show_group)
        self.detail_group_button.set_active(grouped)
        self.detail_sort_button.setVisible(bool(sort_fields))
        self.detail_filter_button.setVisible(show_filter)
        self.detail_filter_button.set_name(
            "eye" if featured_checked else "eye-slash")
        self._apply_collapse_view()

    def tracks(self):
        return self.track_model.tracks()

    def selected_entry(self):
        return self.entry_model.entry_at(self.list_view.currentIndex().row())

    def selected_key(self):
        entry = self.selected_entry()
        return None if entry is None else entry.key

    def select_entry(self, key):
        row = self.entry_model.row_of(key)
        if row >= 0:
            self.list_view.setCurrentIndex(self.entry_model.index(row, 0))

    def highlight_detail_row(self, row):
        if 0 <= row < self.track_model.rowCount():
            index = self.track_model.index(row, 0)
            self.detail_view.setCurrentIndex(index)
            self.detail_view.scrollTo(index)

    def select_track(self, track_id):
        for row in range(self.track_model.rowCount()):
            if self.track_model.is_header(row):
                continue
            track = self.track_model.index(row, 0).data(TrackListModel.TrackRole)
            if getattr(track, "id", None) == track_id:
                self.highlight_detail_row(row)
                return

    def clear(self):
        self._muted = True
        try:
            self.entry_model.set_entries([])
        finally:
            self._muted = False
        self.list_header.setText("")
        self.sort_button.setVisible(False)
        self.filter_button.setVisible(False)
        self.import_button.setVisible(False)
        self.set_tracks([], "")

    def align_split(self, divider_x):
        total = sum(self.splitter.sizes())
        list_w = max(_LIST_MIN_W, divider_x)
        detail_w = max(_DETAIL_MIN_W, total - list_w)
        self.splitter.setSizes([list_w, detail_w])

    def _on_entry_changed(self, current, _previous=QModelIndex()):
        if self._muted:
            return
        if not current.isValid():
            self._detail_key = None
            self.set_tracks([], "")
            return
        entry = self.entry_model.entry_at(current.row())
        if entry is not None:
            if entry.key != self._detail_key:
                motion.snapshot_fade(self.detail_panel, motion.VIEW_MS)
            self._detail_key = entry.key
            self.entrySelected.emit(entry.key)

    def _on_detail_activated(self, index):
        row = index.row()
        if self.track_model.is_header(row):
            return
        track_index = self.track_model.track_index(row)
        if track_index is not None:
            self.trackActivated.emit(track_index)

    def _on_entry_context_menu(self, view, pos):
        index = view.indexAt(pos)
        if not index.isValid():
            return
        entry = self.entry_model.entry_at(index.row())
        if entry is not None:
            self.entryContextMenuRequested.emit(
                entry.key, view.viewport().mapToGlobal(pos))

    def _on_detail_context_menu(self, pos):
        index = self.detail_view.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        global_pos = self.detail_view.viewport().mapToGlobal(pos)
        if self.track_model.is_header(row):
            if self.track_model.is_section(row):
                return
            self.albumContextMenuRequested.emit(
                self.track_model.tracks_for_header(row), global_pos)
            return
        track_index = self.track_model.track_index(row)
        if track_index is not None:
            self.trackContextMenuRequested.emit(track_index, global_pos)
