
import logging
from dataclasses import dataclass
from typing import Optional, Tuple

from PySide6.QtCore import QObject, Signal

log = logging.getLogger(__name__)

TOGGLE = "toggle"
CHOICE = "choice"

_PREFIX = "setting."


@dataclass(frozen=True)
class Setting:
    key: str
    label: str
    category: str
    kind: str
    default: object
    group: Optional[str] = None
    hint: str = ""
    choices: Tuple = ()
    enabled_by: Optional[str] = None

    def value_label(self, value):
        if self.kind == TOGGLE:
            return "On" if value else "Off"
        for choice_value, label in self.choices:
            if choice_value == value:
                return label
        raise ValueError("{!r} is not a choice of {}".format(value, self.key))

    def accepts(self, value):
        if self.kind == TOGGLE:
            return isinstance(value, bool)
        return any(type(v) is type(value) and v == value for v, _ in self.choices)


_NOTIFICATIONS_ON = "notifications.enabled"

RELEASE_ON_BATTERY = "power.release_on_battery_s"
RELEASE_PLUGGED_IN = "power.release_plugged_in_s"
NEVER = -1
_RELEASE_AFTER = ((60, "1 minute"), (300, "5 minutes"), (900, "15 minutes"),
                  (1800, "30 minutes"), (NEVER, "Never"))

REGISTRY = (
    Setting("window.remember_geometry", "Remember window size and position",
            "General", TOGGLE, True, group="Window"),
    Setting("appearance.animations", "Animations", "General", TOGGLE, True,
            group="Appearance", hint="Fades and slides around the app"),
    Setting(RELEASE_ON_BATTERY, "Release audio after pausing, on battery",
            "Playback", CHOICE, 60, group="Power saving",
            hint="Stops waon using CPU while nothing plays. "
                 "Resuming then takes a moment longer.",
            choices=((0, "Immediately"),) + _RELEASE_AFTER),
    Setting(RELEASE_PLUGGED_IN, "Release audio after pausing, plugged in",
            "Playback", CHOICE, NEVER, group="Power saving",
            choices=_RELEASE_AFTER),
    Setting(_NOTIFICATIONS_ON, "Show track notifications",
            "Notifications", TOGGLE, True,
            hint="A popup when the track changes"),
    Setting("notifications.corner", "Corner", "Notifications", CHOICE,
            "bottom_right", group="Appearance",
            choices=(("top_left", "Top left"), ("top_right", "Top right"),
                     ("bottom_left", "Bottom left"),
                     ("bottom_right", "Bottom right")),
            enabled_by=_NOTIFICATIONS_ON),
    Setting("notifications.duration_ms", "Stay on screen for", "Notifications",
            CHOICE, 5000, group="Appearance",
            choices=((3000, "3 seconds"), (5000, "5 seconds"),
                     (8000, "8 seconds"), (12000, "12 seconds")),
            enabled_by=_NOTIFICATIONS_ON),
    Setting("notifications.trigger", "Show when", "Notifications", CHOICE,
            "unfocused", group="When to show",
            choices=(("unfocused", "waon isn't focused"), ("always", "Always")),
            enabled_by=_NOTIFICATIONS_ON),
)


def declared(key, registry=REGISTRY):
    for setting in registry:
        if setting.key == key:
            return setting
    raise KeyError(key)


def default(key, registry=REGISTRY):
    return declared(key, registry).default


def categories(registry=REGISTRY):
    seen = []
    for setting in registry:
        if setting.category not in seen:
            seen.append(setting.category)
    return seen


def groups(category, registry=REGISTRY):
    order = []
    members = {}
    for setting in registry:
        if setting.category != category:
            continue
        if setting.group not in members:
            order.append(setting.group)
            members[setting.group] = []
        members[setting.group].append(setting)
    if None in order:
        order.remove(None)
        order.insert(0, None)
    return [(group, members[group]) for group in order]


def _serialize(setting, value):
    if setting.kind == TOGGLE:
        return "1" if value else "0"
    return str(value)


def _parse(setting, raw):
    if setting.kind == TOGGLE:
        if raw == "1":
            return True
        if raw == "0":
            return False
        raise ValueError(raw)
    value = type(setting.default)(raw)
    if not setting.accepts(value):
        raise ValueError(raw)
    return value


class Settings(QObject):

    changed = Signal(str, object)
    writeFailed = Signal(str, str)

    def __init__(self, store, registry=REGISTRY, parent=None):
        super().__init__(parent)
        self._store = store
        self.registry = tuple(registry)
        self._by_key = {s.key: s for s in self.registry}

    def setting(self, key):
        return self._by_key[key]

    def get(self, key):
        setting = self.setting(key)
        raw = self._store.get_state(_PREFIX + key)
        if raw is None:
            return setting.default
        try:
            return _parse(setting, raw)
        except (TypeError, ValueError):
            log.warning("setting %s: ignoring unreadable stored value %r; "
                        "using the default", key, raw)
            return setting.default

    def set(self, key, value):
        setting = self.setting(key)
        if not setting.accepts(value):
            raise ValueError("{!r} is not a legal value for {}".format(value, key))
        if self.get(key) == value and type(self.get(key)) is type(value):
            return True
        try:
            self._store.set_state(_PREFIX + key, _serialize(setting, value))
        except Exception as exc:
            log.exception("could not save setting %s", key)
            self.writeFailed.emit(key, str(exc))
            return False
        self.changed.emit(key, value)
        return True

    def default(self, key):
        return self.setting(key).default

    def is_default(self, key):
        return self.get(key) == self.default(key)

    def reset(self, key):
        return self.set(key, self.default(key))

    def reset_all(self):
        for setting in self.registry:
            self.reset(setting.key)
