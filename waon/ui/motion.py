
import logging

import shiboken6
from PySide6.QtCore import (
    QEasingCurve, QParallelAnimationGroup, QPoint,
    QPropertyAnimation, Qt,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel

log = logging.getLogger(__name__)

SETTING_KEY = "appearance.animations"

TRACK_MS = 200
VIEW_MS = 150
ENTRANCE_MS = 150
ENTRANCE_RISE = 6
HOVER_MS = 120

enabled = True
SUPPRESSED = False
OVERLAY_NAME = "MotionSnapshot"


def duration(ms):
    return 0 if SUPPRESSED or not enabled else ms


def bind(settings):
    global enabled
    enabled = bool(settings.get(SETTING_KEY))
    settings.changed.connect(_on_setting_changed)


def _on_setting_changed(key, value):
    global enabled
    if key == SETTING_KEY:
        enabled = bool(value)


def run_tween(animation, start, end, ms, apply):
    animation.stop()
    ms = duration(ms)
    if ms <= 0 or start == end:
        apply(end)
        return
    animation.setStartValue(start)
    animation.setEndValue(end)
    animation.setDuration(ms)
    animation.start()


def snapshot_fade(widget, ms):
    ms = duration(ms)
    if (ms <= 0 or not widget.isVisible() or widget.width() <= 0
            or widget.height() <= 0 or _ancestor_fading(widget)):
        _retire(_overlay_of(widget))
        return None
    pixmap = widget.grab()
    if pixmap.isNull():
        log.warning("snapshot_fade: could not grab %s; changing without a fade",
                    widget.objectName() or type(widget).__name__)
        return None
    _retire(_overlay_of(widget))
    overlay = QLabel(widget)
    overlay.setObjectName(OVERLAY_NAME)
    overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
    overlay.setPixmap(pixmap)
    overlay.setGeometry(widget.rect())
    effect = QGraphicsOpacityEffect(overlay)
    overlay.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", overlay)
    fade.setDuration(ms)
    fade.setStartValue(1.0)
    fade.setEndValue(0.0)
    fade.finished.connect(lambda: _retire(overlay))
    overlay.show()
    overlay.raise_()
    fade.start()
    return overlay


def _overlay_of(widget):
    return widget.findChild(QLabel, OVERLAY_NAME, Qt.FindDirectChildrenOnly)


def _retire(overlay):
    if overlay is None or not shiboken6.isValid(overlay):
        return
    overlay.hide()
    overlay.setObjectName("")
    overlay.deleteLater()


def _ancestor_fading(widget):
    parent = widget.parentWidget()
    while parent is not None:
        if _overlay_of(parent) is not None:
            return True
        parent = parent.parentWidget()
    return False


def fade_in(widget, ms, rise=0, rise_widget=None):
    _stop_entrance(widget)
    ms = duration(ms)
    if ms <= 0:
        return
    mover = (rise_widget if rise_widget is not None else widget) if rise else None
    end = mover.pos() if mover is not None else None
    group = QParallelAnimationGroup(widget)
    if widget.isWindow():
        widget.setWindowOpacity(0.0)
        fade = QPropertyAnimation(widget, b"windowOpacity")
    else:
        effect = QGraphicsOpacityEffect(widget)
        effect.setOpacity(0.0)
        widget.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity")
    fade.setDuration(ms)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    group.addAnimation(fade)
    if mover is not None:
        start = end + QPoint(0, rise)
        mover.move(start)
        move = QPropertyAnimation(mover, b"pos")
        move.setDuration(ms)
        move.setStartValue(start)
        move.setEndValue(end)
        move.setEasingCurve(QEasingCurve.OutCubic)
        group.addAnimation(move)
    widget._motion_entrance = (group, mover, end)
    group.finished.connect(lambda: _finish_entrance(group.parent(), group))
    group.start()


def _stop_entrance(widget):
    entrance = getattr(widget, "_motion_entrance", None)
    if entrance is None:
        return
    group = entrance[0]
    if shiboken6.isValid(group):
        group.stop()
    _finish_entrance(widget, group)


def _finish_entrance(widget, group):
    if shiboken6.isValid(group):
        group.deleteLater()
    if widget is None or not shiboken6.isValid(widget):
        return
    entrance = getattr(widget, "_motion_entrance", None)
    widget._motion_entrance = None
    if entrance is None:
        return
    _group, mover, end = entrance
    if mover is not None and shiboken6.isValid(mover):
        mover.move(end)
    if widget.isWindow():
        widget.setWindowOpacity(1.0)
    else:
        widget.setGraphicsEffect(None)
