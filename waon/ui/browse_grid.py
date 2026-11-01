
from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import QAbstractItemView, QListView, QStyledItemDelegate

from waon.library import locations
from waon.ui import theme
from waon.ui.browse_models import EntryModel
from waon.ui.browse_panes import _CHECKBOX_SIZE, _HoverScrollView, playable_key
from waon.ui.cover_art import placeholder, rounded
from waon.ui.icons import render_icon, screen_dpr

TILE_ART = 140
TILE_PAD = 12
LABEL_LINE_H = 20
LABEL_H = 6 + LABEL_LINE_H + 2 + LABEL_LINE_H + TILE_PAD
TILE_W = TILE_ART + TILE_PAD * 2
TILE_H = TILE_ART + TILE_PAD + LABEL_H
GRID_SPACING = 12

_LOCK_NAME_GLYPH_SIZE = 14
_LOCK_NAME_GAP = 4
_STATUS_GLYPH_SIZE = 18
PLAY_BUTTON_SIZE = 32
PLAY_BUTTON_INSET = 8
_PLAY_GLYPH_SIZE = 16
_PLAY_BUTTON_GROW = 2
_ART_HOVER_DIM = QColor(0, 0, 0, 77)
_PLAY_BUTTON_FILL = QColor(0, 0, 0, 153)
_PLAY_BUTTON_FILL_HOVER = QColor(0, 0, 0, 230)


def play_button_rect(tile_rect):
    art_right = tile_rect.left() + TILE_PAD + TILE_ART
    art_bottom = tile_rect.top() + TILE_PAD + TILE_ART
    return QRect(art_right - PLAY_BUTTON_INSET - PLAY_BUTTON_SIZE,
                 art_bottom - PLAY_BUTTON_INSET - PLAY_BUTTON_SIZE,
                 PLAY_BUTTON_SIZE, PLAY_BUTTON_SIZE)


class _ThumbnailDelegate(QStyledItemDelegate):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pixmap_cache = {}
        self._collage_cache = {}
        self._round = False
        self._placeholder = placeholder(TILE_ART)
        self._lock_glyph = render_icon("lock-simple", theme.TEXT_MUTED,
                                       _LOCK_NAME_GLYPH_SIZE)
        self._active_glyph = render_icon("waveform", theme.BRAND,
                                         _STATUS_GLYPH_SIZE)
        self._play_glyph = render_icon("play", "#FFFFFF", _PLAY_GLYPH_SIZE)
        self._hover_pos = None

    def set_round_thumbs(self, round_thumbs):
        if round_thumbs == self._round:
            return
        self._round = round_thumbs
        self._pixmap_cache.clear()
        self._collage_cache.clear()
        radius = TILE_ART / 2 if round_thumbs else 0
        self._placeholder = placeholder(TILE_ART, radius=radius)

    def set_hover_pos(self, pos):
        self._hover_pos = pos

    def sizeHint(self, option, index):
        return QSize(TILE_W, TILE_H)

    def paint(self, painter, option, index):
        painter.save()
        art_rect = QRect(option.rect.left() + TILE_PAD, option.rect.top() + TILE_PAD,
                         TILE_ART, TILE_ART)
        highlight = None
        selected = (not index.model().is_selection_mode()
                   and bool(option.state & option.state.__class__.State_Selected))
        if selected:
            highlight = QColor(theme.BRAND_SOFT)
        elif option.state & option.state.__class__.State_MouseOver:
            highlight = QColor(theme.SURFACE_ALT)
        if highlight is not None:
            painter.fillRect(option.rect, highlight)

        art_ids = index.data(EntryModel.ArtIdsRole) or ()
        key = index.data(EntryModel.KeyRole)
        painter.drawPixmap(art_rect, self.art_pixmap(key, art_ids))
        if (option.state & option.state.__class__.State_MouseOver
                and index.data(EntryModel.PlayableRole)
                and not index.model().is_selection_mode()):
            painter.fillRect(art_rect, _ART_HOVER_DIM)
            self._paint_play_button(painter, play_button_rect(option.rect))

        if index.model().is_selection_mode():
            checked = bool(index.data(EntryModel.CheckedRole))
            backing = QRect(art_rect.left() + 2, art_rect.top() + 2,
                           _CHECKBOX_SIZE + 4, _CHECKBOX_SIZE + 4)
            painter.fillRect(backing, QColor(theme.SURFACE))
            box = QRect(backing.left() + 2, backing.top() + 2,
                       _CHECKBOX_SIZE, _CHECKBOX_SIZE)
            painter.drawPixmap(box.topLeft(), render_icon(
                "check-square" if checked else "square", theme.ICON, _CHECKBOX_SIZE))

        label_x = option.rect.left() + TILE_PAD
        title_rect = QRect(label_x, art_rect.bottom() + 6, TILE_ART, LABEL_LINE_H)
        subtitle_rect = QRect(label_x, title_rect.bottom() + 2, TILE_ART, LABEL_LINE_H)
        label_align = Qt.AlignHCenter if self._round else Qt.AlignLeft

        locked = bool(index.data(EntryModel.LockedRole))
        active = bool(index.data(EntryModel.ActiveRole))
        status_glyph = self._lock_glyph if locked else (
            self._active_glyph if active else None)
        status_size = _LOCK_NAME_GLYPH_SIZE if locked else _STATUS_GLYPH_SIZE
        status_reserve = status_size + _LOCK_NAME_GAP if status_glyph else 0

        font = QFont(option.font)
        font.setWeight(QFont.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT))
        title = painter.fontMetrics().elidedText(
            index.data(Qt.DisplayRole) or "", Qt.ElideRight, TILE_ART - status_reserve)
        painter.drawText(title_rect, label_align | Qt.AlignVCenter, title)
        if status_glyph is not None:
            glyph_rect = self._status_glyph_rect(title_rect, status_size)
            painter.drawPixmap(glyph_rect.topLeft(), status_glyph)

        font.setWeight(QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(theme.TEXT_MUTED))
        subtitle = painter.fontMetrics().elidedText(
            index.data(EntryModel.SublabelRole) or "", Qt.ElideRight, TILE_ART)
        painter.drawText(subtitle_rect, label_align | Qt.AlignVCenter, subtitle)
        painter.restore()

    def _paint_play_button(self, painter, rect):
        on_button = self._hover_pos is not None and rect.contains(self._hover_pos)
        circle = (rect.adjusted(-_PLAY_BUTTON_GROW, -_PLAY_BUTTON_GROW,
                                _PLAY_BUTTON_GROW, _PLAY_BUTTON_GROW)
                  if on_button else rect)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_PLAY_BUTTON_FILL_HOVER if on_button else _PLAY_BUTTON_FILL)
        painter.drawEllipse(circle)
        painter.restore()
        offset = (PLAY_BUTTON_SIZE - _PLAY_GLYPH_SIZE) // 2
        painter.drawPixmap(rect.left() + offset, rect.top() + offset, self._play_glyph)

    def _status_glyph_rect(self, title_rect, size=_LOCK_NAME_GLYPH_SIZE):
        x = title_rect.left() + title_rect.width() - size
        y = title_rect.top() + (title_rect.height() - size) // 2
        return QRect(x, y, size, size)


    def art_pixmap(self, key, art_ids):
        if not art_ids:
            return self._placeholder
        if len(art_ids) == 1:
            return self._single_pixmap(art_ids[0])
        return self._collage_pixmap(key, art_ids)

    def _single_pixmap(self, album_id):
        cached = self._pixmap_cache.get(album_id)
        if cached is not None:
            return cached
        pixmap = QPixmap(locations.art_path(album_id))
        if pixmap.isNull():
            return self._placeholder
        radius = TILE_ART / 2 if self._round else 0
        result = rounded(pixmap, TILE_ART, radius=radius)
        self._pixmap_cache[album_id] = result
        return result

    def _collage_pixmap(self, key, art_ids):
        cache_key = (key, tuple(art_ids))
        cached = self._collage_cache.get(cache_key)
        if cached is not None:
            return cached
        cells = [art_ids[i % len(art_ids)] for i in range(4)]
        dpr = screen_dpr()
        half = TILE_ART // 2
        out = QPixmap(round(TILE_ART * dpr), round(TILE_ART * dpr))
        out.setDevicePixelRatio(dpr)
        out.fill(Qt.transparent)
        painter = QPainter(out)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        positions = [(0, 0), (half, 0), (0, half), (half, half)]
        any_missing = False
        for (x, y), album_id in zip(positions, cells):
            quadrant = self._single_pixmap(album_id)
            if quadrant is self._placeholder:
                any_missing = True
            painter.drawPixmap(QRect(x, y, half, half), quadrant)
        painter.end()
        if not any_missing:
            self._collage_cache[cache_key] = out
        return out


class _TileView(_HoverScrollView):

    playRequested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pressed_play = False

    def play_key_at(self, pos):
        index = self.indexAt(pos)
        key = playable_key(self, index)
        if key is None or not play_button_rect(self.visualRect(index)).contains(pos):
            return None
        return key

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            key = self.play_key_at(event.position().toPoint())
            if key is not None:
                self._pressed_play = True
                event.accept()
                self.playRequested.emit(key)
                return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._pressed_play:
            self._pressed_play = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.play_key_at(event.position().toPoint()) is not None:
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint()
        self.itemDelegate().set_hover_pos(pos)
        index = self.indexAt(pos)
        if index.isValid():
            self.viewport().update(self.visualRect(index))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.itemDelegate().set_hover_pos(None)
        super().leaveEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            key = playable_key(self, self.currentIndex())
            if key is not None:
                self.playRequested.emit(key)
            event.accept()
            return
        super().keyPressEvent(event)


class ThumbnailGridView(_TileView):

    WHEEL_STEP = 40

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setGridSize(QSize(TILE_W + GRID_SPACING, TILE_H + GRID_SPACING))
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setMouseTracking(True)
        self.setItemDelegate(_ThumbnailDelegate(self))

    def mousePressEvent(self, event):
        pos = event.position().toPoint()
        index = self.indexAt(pos)
        if (event.button() == Qt.LeftButton and index.isValid()
                and self.model().is_selection_mode()):
            self.model().toggle_checked(index.data(EntryModel.KeyRole))
            return
        super().mousePressEvent(event)

    def updateGeometries(self):
        self._fit_grid_to_viewport()
        super().updateGeometries()
        self.verticalScrollBar().setSingleStep(self.WHEEL_STEP)

    def _fit_grid_to_viewport(self):
        pitch = TILE_W + GRID_SPACING
        bar = self.verticalScrollBar()
        viewport_w = self.viewport().width()
        stable_w = viewport_w if bar.isVisible() else viewport_w - bar.sizeHint().width()
        if stable_w < pitch:
            return
        columns = stable_w // pitch
        new_pitch = (stable_w - 1) // columns
        if new_pitch != self.gridSize().width():
            self.setGridSize(QSize(new_pitch, TILE_H + GRID_SPACING))

    def set_round_thumbs(self, round_thumbs):
        self.itemDelegate().set_round_thumbs(round_thumbs)
