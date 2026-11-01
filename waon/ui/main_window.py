
import logging
import os
import random
import sqlite3
import time
from dataclasses import replace

import shiboken6
from PySide6.QtCore import QByteArray, QEvent, QProcess, Qt, QTimer
from PySide6.QtGui import QCursor, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QDialog, QFileDialog, QHBoxLayout, QMainWindow,
    QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from waon import playlist_file
from waon.library import locations, paths, porting
from waon.library import service as svc
from waon.library.db import LibraryCorruptError, SchemaTooNewError
from waon.library.entities import METRIC_PLAYS, BrowseEntry
from waon.library.scan_worker import ScanWorker
from waon.library.service import LibraryService
from waon.models import Track
from waon.player.artwork import extract_cover
from waon.player.controller import PlaybackController
from waon.player.engine import PlayerEngine
from waon.player.idle_release import IdleRelease
from waon.player.play_tracker import PlayTracker
from waon.player.queue import QueueModel
from waon.power import PowerWatcher
from waon.settings import Settings
from waon.track_info import build_track_info, listening_rows, read_file_details
from waon.ui import dnd
from waon.ui import frameless
from waon.ui import motion
from waon.ui import settings_pages
from waon.ui.browse_models import track_identity
from waon.ui.browse_panes import BrowsePanes
from waon.ui.home_page import HomePage
from waon.ui.icons import app_icon
from waon.ui.library_dialog import LibrarySettingsDialog
from waon.ui.library_import_dialog import LibraryImportResultsDialog, import_summary
from waon.ui.media_keys import MediaKeys
from waon.ui.nav_rail import NavRail
from waon.ui.notification_controller import NotificationController
from waon.ui.now_playing_page import NowPlayingPage
from waon.ui.playlist_dialog import AddToPlaylistDialog
from waon.ui.playlist_import_dialog import PlaylistImportResultsDialog
from waon.ui.popup_menu import PopupMenu
from waon.ui.queue_dialog import AddToQueueDialog
from waon.ui.rename_playlist_dialog import RenamePlaylistDialog
from waon.ui.rename_queue_dialog import RenameQueueDialog
from waon.ui.scan_overlay import ScanOverlay
from waon.ui.settings_overlay import SettingsOverlay
from waon.ui.title_bar import TitleBar
from waon.ui.track_info_dialog import TrackInfoDialog
from waon.ui.toast import Toast
from waon.ui.transport_bar import TransportBar
from waon.ui.setup_wizard import SetupWizard
from waon.util import AUDIO_EXTENSIONS, display_artist, format_duration

log = logging.getLogger(__name__)

_UNSET = object()


def _plural(n, noun):
    return "1 {}".format(noun) if n == 1 else "{} {}s".format(n, noun)


def _count_caption(n, singular, plural):
    return "{} {}".format(n, singular if n == 1 else plural)


def _queue_detail_title(label, tracks):
    total = format_duration(sum(t.duration for t in tracks))
    return "{} • {} • {}".format(label, _plural(len(tracks), "track"), total)


def _playlist_add_message(n, playlist_name):
    return "Added {} to {}.".format(_plural(n, "track"), playlist_name)


def _playlist_remove_message(n, playlist_name):
    return "Removed {} from {}.".format(_plural(n, "track"), playlist_name)


def _playlist_changes_message(added_to, removed_from):
    parts = []
    if added_to:
        parts.append("added to {}".format(_plural(added_to, "playlist")))
    if removed_from:
        parts.append("removed from {}".format(_plural(removed_from, "playlist")))
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _count(n, noun):
    return "{:,} {}{}".format(n, noun, "" if n == 1 else "s")


def _queue_add_message(n):
    return "Added {} to the queue.".format(_plural(n, "track"))


def _owner_of(tracks):
    ids = {t.library_id for t in tracks}
    if len(ids) == 1 and None not in ids:
        return next(iter(ids))
    return None


def _queue_remove_message(n):
    return "Removed {} from the queue.".format(_plural(n, "track"))


def _queue_changes_message(added_to, removed_from):
    parts = []
    if added_to:
        parts.append("added to {}".format(_plural(added_to, "queue")))
    if removed_from:
        parts.append("removed from {}".format(_plural(removed_from, "queue")))
    text = ", ".join(parts)
    return text[:1].upper() + text[1:] + "."


def _play_next_message(n):
    return "{} will play next.".format(_plural(n, "track"))


def _explorer_target(paths):
    if not paths:
        return None
    if len(paths) == 1:
        return ("select", paths[0]) if os.path.exists(paths[0]) else None
    folders = {os.path.normcase(os.path.dirname(p)) for p in paths}
    if len(folders) != 1:
        return None
    folder = os.path.dirname(paths[0])
    return ("folder", folder) if os.path.isdir(folder) else None


class MainWindow(QMainWindow):
    def __init__(self, service=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("waon")
        self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint)
        self.setWindowIcon(app_icon())
        self.setMinimumSize(860, 480)
        self.resize(1100, 700)
        self._frameless_installed = False
        self._split_aligned = False
        self._force_show_featured = False

        self.service = service if service is not None else LibraryService()
        self.settings = Settings(self.service, parent=self)
        motion.bind(self.settings)
        self.queue = QueueModel(self)
        self.engine = PlayerEngine(self)
        self.controller = PlaybackController(self.queue, self.engine, self)
        self.play_tracker = PlayTracker(self.queue, self.engine, self.service, self)
        self.idle_release = IdleRelease(self.engine, self.settings, parent=self)
        self.power_watcher = PowerWatcher(self)
        self.power_watcher.changed.connect(self.idle_release.power_changed)

        self.worker_factory = ScanWorker
        self.library_settings_dialog_factory = LibrarySettingsDialog
        self.add_to_playlist_dialog_factory = AddToPlaylistDialog
        self.rename_playlist_dialog_factory = RenamePlaylistDialog
        self.import_results_dialog_factory = PlaylistImportResultsDialog
        self.add_to_queue_dialog_factory = AddToQueueDialog
        self.rename_queue_dialog_factory = RenameQueueDialog
        self.library_import_dialog_factory = LibraryImportResultsDialog
        self.track_info_dialog_factory = TrackInfoDialog
        self.shuffle_tracks = random.shuffle
        self._scan_worker = None
        self._scan_library_id = None
        self._pending_library_id = None
        self._scan_sink = None
        self._wizard_library_id = None
        self._wizard_return_id = None
        self._settings_dialog = None

        self.queue_source_kind = None
        self.queue_source_label = ""
        self.queue_owner_library_id = None
        self.active_queue_id = None

        self._restoring = False
        self._position = 0.0
        self._closed = False
        self._pending_resume_row = None
        self._pending_resume_seconds = 0.0

        self._build_ui()
        self.notifications = NotificationController(self, parent=self,
                                                    settings=self.settings)
        settings_pages.install(self.settings_overlay, self.settings,
                               lambda title, text: self.confirm(title, text))
        self.settings.writeFailed.connect(
            lambda key, message: self.report_error("Could not save setting", message))
        self._wire()
        self._install_shortcuts()
        self._restore_state()
        self._start_hover_correction_timer()

    def _build_ui(self):
        self.title_bar = TitleBar()
        self.library_bar = self.title_bar.library_bar
        self.rail = NavRail()
        self.panes = BrowsePanes()
        self.home_page = HomePage()

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.panes)
        self.content_stack.addWidget(self.home_page)

        self.browse_page = QWidget()
        browse_layout = QHBoxLayout(self.browse_page)
        browse_layout.setContentsMargins(0, 0, 0, 0)
        browse_layout.setSpacing(0)
        browse_layout.addWidget(self.rail)
        browse_layout.addWidget(self.content_stack, 1)

        self.setup_wizard = SetupWizard()

        self.root_stack = QStackedWidget()
        self.root_stack.addWidget(self.browse_page)
        self.root_stack.addWidget(self.setup_wizard)

        self.transport = TransportBar()

        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self.title_bar)
        root.addWidget(self.root_stack, 1)
        root.addWidget(self.transport)
        self.setCentralWidget(central)

        self.overlay = ScanOverlay(self, cover=self.browse_page)

        self.now_playing_page = NowPlayingPage(self.root_stack)
        self.now_playing_page.hide()
        self.root_stack.installEventFilter(self)

        self.settings_overlay = SettingsOverlay(central)
        self.toast = Toast(self.browse_page)
        self.setAcceptDrops(True)

    def _wire(self):
        self.rail.itemSelected.connect(self._on_rail_item)
        self.panes.entrySelected.connect(self._on_entry_selected)
        self.panes.trackActivated.connect(self._on_track_activated)
        self.panes.albumActivated.connect(self._on_album_activated)
        self.panes.entryActivated.connect(self._on_entry_activated)
        self.panes.entryContextMenuRequested.connect(self._on_entry_context_menu)
        self.panes.trackContextMenuRequested.connect(self._on_track_context_menu)
        self.panes.albumContextMenuRequested.connect(self._on_album_context_menu)
        self.panes.trackReordered.connect(self._on_track_reordered)
        self.panes.resumeQueueRequested.connect(self._on_resume_queue_clicked)
        self.panes.playAllRequested.connect(self._on_play_all)
        self.panes.shuffleAllRequested.connect(self._on_shuffle_all)
        self.panes.periodChanged.connect(self._on_songs_period_changed)
        self.panes.importPlaylistsRequested.connect(self.on_import_playlists)
        self.panes.showFeaturedArtistsToggled.connect(self._on_show_featured_artists_toggled)
        self.panes.showFeaturedTracksToggled.connect(self._on_show_featured_tracks_toggled)
        self.panes.sortChanged.connect(self._on_sort_changed)
        self.panes.detailGroupToggled.connect(self._on_detail_group_toggled)
        self.panes.detailSortChanged.connect(self._on_detail_sort_changed)
        self.queue.currentChanged.connect(self._on_queue_current_changed)
        self.library_bar.librarySelected.connect(self.select_library)
        self.setup_wizard.createRequested.connect(self._on_setup_create)
        self.setup_wizard.cancelRequested.connect(self._on_setup_cancel)
        self.setup_wizard.scanCancelRequested.connect(self._on_scan_cancel)
        self.setup_wizard.scanEnded.connect(self._on_setup_scan_ended)
        self.setup_wizard.scanFailed.connect(self._on_setup_scan_failed)
        self.setup_wizard.importRequested.connect(self._on_setup_import)
        self.setup_wizard.finishRequested.connect(self._on_setup_finished)
        self.library_bar.addLibraryRequested.connect(self.on_add_library)
        self.library_bar.librarySettingsRequested.connect(self.on_open_library_settings)
        self.title_bar.minimizeRequested.connect(self.showMinimized)
        self.title_bar.maximizeRequested.connect(self._toggle_maximize)
        self.title_bar.closeRequested.connect(self.close)
        self.title_bar.settingsRequested.connect(self.on_open_settings)
        self.overlay.cancelRequested.connect(self._on_scan_cancel)
        self.overlay.dismissed.connect(self._on_scan_dismissed)
        self.home_page.periodChanged.connect(self._on_home_period_changed)
        self.home_page.trackActivated.connect(self._on_home_track_activated)
        self.home_page.albumActivated.connect(self._on_home_album_activated)
        self.home_page.artistActivated.connect(self._on_home_artist_activated)
        self.home_page.lastAddedActivated.connect(self._on_home_last_added_activated)
        self.home_page.lastAddedContextMenuRequested.connect(
            self._on_home_last_added_context_menu)
        self.home_page.trackContextMenuRequested.connect(self._on_home_track_context_menu)
        self.home_page.albumContextMenuRequested.connect(self._on_home_album_context_menu)
        self.home_page.artistContextMenuRequested.connect(self._on_home_artist_context_menu)
        self.home_page.metricChanged.connect(self._on_home_metric_changed)
        self.home_page.favoriteActivated.connect(self._open_track_in_album)
        self.home_page.favoritePlayRequested.connect(self._on_home_favorite_play)
        self.home_page.lastAddedPlayRequested.connect(self._on_home_last_added_play)
        self.home_page.favoritesShuffleRequested.connect(self._on_home_favorites_shuffle)
        self.home_page.favoriteContextMenuRequested.connect(
            self._on_home_track_context_menu)
        self.play_tracker.playCredited.connect(self._on_play_credited)

        self.transport.playPauseClicked.connect(self.controller.toggle_play)
        self.transport.stopClicked.connect(self._stop)
        self.transport.nextClicked.connect(self.controller.play_next)
        self.transport.prevClicked.connect(self.controller.play_prev)
        self.transport.repeatClicked.connect(self.controller.cycle_repeat)
        self.transport.shuffleClicked.connect(self.controller.toggle_shuffle)
        self.transport.seekRequested.connect(self.engine.seek)
        self.transport.volumeChanged.connect(self.engine.set_volume)
        self.transport.filesDropped.connect(self._on_transport_files_dropped)
        self.transport.moreClicked.connect(self._show_now_playing_menu)
        self.transport.favoriteClicked.connect(self._toggle_favorite)
        self.transport.artClicked.connect(self._toggle_now_playing_page)
        page = self.now_playing_page
        page.closeRequested.connect(page.close_down)
        page.trackActivated.connect(self._on_now_playing_row_activated)
        page.orderChanged.connect(self._on_now_playing_reordered)
        page.trackContextMenuRequested.connect(self._on_now_playing_row_menu)
        self.queue.currentChanged.connect(self._sync_now_playing_page)
        self.queue.rowsInserted.connect(self._sync_now_playing_page)
        self.queue.rowsRemoved.connect(self._sync_now_playing_page)
        self.queue.modelReset.connect(self._sync_now_playing_page)

        self.media_keys = MediaKeys(self)
        self.media_keys.playPause.connect(self.controller.toggle_play)
        self.media_keys.next.connect(self.controller.play_next)
        self.media_keys.previous.connect(self.controller.play_prev)
        self.media_keys.stop.connect(self._stop)

        self.controller.repeatChanged.connect(self.transport.set_repeat_mode)
        self.controller.shuffleChanged.connect(self.transport.set_shuffle)
        self.controller.falseStart.connect(self.notifications.cancel)

        self.engine.positionChanged.connect(self.transport.set_position)
        self.engine.positionChanged.connect(self._on_position_changed)
        self.engine.durationChanged.connect(self.transport.set_duration)
        self.engine.stateChanged.connect(self._on_state_changed)
        self.engine.errorOccurred.connect(self._on_error)

        self.queue.currentChanged.connect(self._on_current_changed)
        self.queue.rowsInserted.connect(self._refresh_transport_enabled)
        self.queue.modelReset.connect(self._refresh_transport_enabled)

    def _install_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self,
                  activated=self.controller.toggle_play)
        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._stop)
        QShortcut(QKeySequence("Ctrl+O"), self, activated=self.open_file_dialog)

    def _restore_state(self):
        self.home_page.set_metric(
            self.service.get_state("home_recap_metric", METRIC_PLAYS))
        if self.service.recovered_app_db:
            QMessageBox.warning(
                self, "Settings file replaced",
                "waon could not read its settings file and started fresh. "
                "The old one was kept alongside it at:\n{}".format(
                    self.service.recovered_app_db))
        libraries = self.service.libraries()
        remembered = self.service.get_state("current_library_id")
        if remembered == svc.ALL_LIBRARIES_ID and len(libraries) >= 2:
            self._enter_all_libraries()
            self._refresh_transport_enabled()
            self._restore_playback()
            return

        target = None
        for library in libraries:
            if remembered is not None and str(library.id) == remembered:
                target = library
                break

        if target is None and libraries:
            target = libraries[0]
        if target is None:
            self._enter_no_library_ui()
        else:
            self.select_library(target.id)
        self._refresh_transport_enabled()
        self._restore_playback()

    def _restore_playback(self):
        volume = float(self.service.get_state("volume", "0.8"))
        self.engine.set_volume(volume)
        self.transport.set_volume(volume)
        self.controller.set_repeat(self.service.get_state("repeat", "off"))
        self.controller.set_shuffle(self.service.get_state("shuffle", "0") == "1")
        geometry = self.service.get_state("window_geometry")
        if geometry and self.settings.get("window.remember_geometry"):
            self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))

        loaded = None
        active_id = self.service.get_state("active_queue_id")
        if active_id:
            loaded = self.service.load_queue(active_id)
        if loaded is None:
            return
        queue_ref, tracks = loaded
        self.active_queue_id = queue_ref.id
        self.queue_source_kind = queue_ref.source_kind
        self.queue_source_label = queue_ref.source_label
        self.queue_owner_library_id = queue_ref.owner_library_id
        self._restoring = True
        try:
            self.queue.set_tracks(tracks, queue_ref.current_pos)
        finally:
            self._restoring = False
        saved_track_id = self.service.get_state("now_playing_track_id", "")
        if saved_track_id:
            self.play_tracker.restore_progress(
                saved_track_id,
                self.service.get_state("now_playing_library_id", "") or None,
                float(self.service.get_state("now_playing_accumulated", "0")),
                self.service.get_state("now_playing_credited", "0") == "1")
        self._refresh_queue_pane_if_active()
        if 0 <= queue_ref.current_pos < len(tracks):
            track = tracks[queue_ref.current_pos]
            position = float(self.service.get_state("position_seconds", "0"))
            self.engine.defer_load(track.path, position, track.duration)

    def select_library(self, library_id):
        if self._scan_worker is not None:
            return
        if library_id == svc.ALL_LIBRARIES_ID:
            self._enter_all_libraries()
            return
        try:
            self.service.open_library(library_id)
        except (LibraryCorruptError, SchemaTooNewError):
            log.exception("could not open library %s", library_id)
            self.panes.clear()
            self.rail.set_library_available(False)
            self._refresh_library_bar()
            return
        self.service.set_state("current_library_id", str(library_id))
        self.panes.track_model.set_open_library(library_id)
        if self.service.setup_pending():
            self._sync_favorite_button()
            self._resume_setup()
            return
        self._show_browse_page()
        self.rail.set_library_available(True)
        self.rail.set_all_mode(False)
        self.rail.set_current(svc.RAIL_HOME)
        self._refresh_library_bar()
        self._refresh_panes()
        self._sync_favorite_button()

    def _enter_all_libraries(self):
        if len(self.service.libraries()) < 2:
            log.warning("All libraries needs two libraries; staying put")
            return
        self.service.open_all()
        self.service.set_state("current_library_id", svc.ALL_LIBRARIES_ID)
        self.panes.track_model.set_open_library(None)
        self._show_browse_page()
        self.rail.set_library_available(True)
        self.rail.set_all_mode(True)
        self.rail.set_current(svc.RAIL_HOME)
        self._refresh_library_bar()
        self._refresh_panes()
        self._sync_favorite_button()

    def _enter_no_library_ui(self):
        if self.service.current is not None or self.service.all_mode:
            self.service.close_library()
        self.panes.track_model.set_open_library(None)
        self.rail.set_library_available(False)
        self.rail.set_all_mode(False)
        if self.rail.current() in svc.LIBRARY_RAIL_ITEMS:
            self.rail.set_current(svc.RAIL_QUEUES)
        self._refresh_library_bar()
        self._refresh_panes()
        self._begin_setup()

    def _show_browse_page(self):
        self.root_stack.setCurrentWidget(self.browse_page)
        self.library_bar.setVisible(True)
        self.transport.setVisible(True)
        self._maybe_align_initial_split()

    def _show_setup_page(self, can_cancel):
        self.root_stack.setCurrentWidget(self.setup_wizard)
        self.library_bar.setVisible(False)
        self.transport.setVisible(can_cancel)

    def _refresh_library_bar(self):
        libraries = self.service.libraries()
        current = self.service.current
        current_id = (svc.ALL_LIBRARIES_ID if self.service.all_mode
                      else None if current is None else current.id)
        self.library_bar.set_libraries(libraries, current_id, self.service.broken_ids,
                                       show_all=len(libraries) >= 2)

    def _on_rail_item(self, item):
        motion.snapshot_fade(self.content_stack, motion.VIEW_MS)
        self.panes.entry_model.set_selection_mode(False)
        self.rail.set_current(item)
        self._refresh_panes(item)

    def _refresh_panes(self, item=None):
        if item is None:
            item = self.rail.current()
        if item == svc.RAIL_HOME:
            self.content_stack.setCurrentWidget(self.home_page)
            self._refresh_home()
            return
        self.content_stack.setCurrentWidget(self.panes)
        caption = self.rail.button(item).caption
        if item == svc.RAIL_QUEUES:
            self._refresh_queue_pane(caption)
            return
        use_grid = item in svc.GRID_RAIL_ITEMS
        show_featured = ((self._force_show_featured or self.service.filter_featured_artists())
                         if item == svc.RAIL_ARTISTS else None)
        show_import = item == svc.RAIL_PLAYLISTS
        round_thumbs = item == svc.RAIL_ARTISTS
        sort_fields = svc.SORT_FIELDS.get(item, ())
        sort_state = self.service.sort_state(item)
        entries = self.service.entries(item, include_featured=bool(show_featured),
                                       sort=sort_state)
        if item == svc.RAIL_ARTISTS:
            caption = _count_caption(len(entries), "artist", "artists")
        elif item == svc.RAIL_ALBUMS:
            caption = _count_caption(len(entries), "album", "albums")
        elif item == svc.RAIL_PLAYLISTS:
            caption = _count_caption(len(entries), "playlist", "playlists")
        show_select = item not in (svc.RAIL_FOLDERS, svc.RAIL_SONGS)
        self.panes.set_entries(entries, caption, use_grid=use_grid,
                               show_featured=show_featured, show_import=show_import,
                               round_thumbs=round_thumbs, sort_fields=sort_fields,
                               sort_state=sort_state, show_select=show_select,
                               playable=item != svc.RAIL_ARTISTS)

    def _refresh_queue_pane(self, caption):
        listed = self.service.list_queues(self._browse_owner())
        if not listed:
            self.panes.set_entries([], caption)
            return
        entries = [
            BrowseEntry(key=ref.id, label=ref.source_label or "Queue",
                       sublabel=_plural(count, "track"),
                       art_ids=tuple(self.service.queue_art_ids(ref.id)),
                       active=(ref.id == self.active_queue_id))
            for ref, count in listed]
        caption = _count_caption(len(entries), "queue", "queues")
        self.panes.set_entries(entries, caption, use_grid=True)
        if self.active_queue_id is not None:
            self.panes.select_entry(self.active_queue_id)

    def _on_entry_selected(self, key):
        item = self.rail.current()
        entry = self.panes.selected_entry()
        label = "" if entry is None else entry.label
        if item == svc.RAIL_QUEUES:
            if key == self.active_queue_id:
                tracks = self.queue.tracks()
                self.panes.set_tracks(tracks, _queue_detail_title(label, tracks),
                                      reorderable=True)
                self.panes.highlight_detail_row(self.queue.playing_row())
            else:
                loaded = self.service.load_queue(key)
                tracks = loaded[1] if loaded is not None else []
                self.panes.set_tracks(tracks, _queue_detail_title(label, tracks),
                                      reorderable=True, show_resume=True)
            return
        if item == svc.RAIL_FOLDERS:
            self.panes.set_tracks(self.service.tracks(item, key), label)
            return
        if item == svc.RAIL_SONGS:
            self._show_song_list(key, label)
            return
        group_state = self.service.detail_group_state(item)
        sort_state = self.service.detail_sort_state(item, group_state)
        sort_fields = svc.DETAIL_SORT_FIELDS[(item, group_state)]
        if item == svc.RAIL_PLAYLISTS and entry is not None and entry.locked:
            sort_fields = ()
        filter_state = self.service.detail_filter_featured_tracks()
        show_filter = item == svc.RAIL_ARTISTS
        featured = (self.service.featured_tracks(key)
                    if show_filter and filter_state else [])
        tracks = self.service.tracks(item, key, sort=sort_state, group=group_state)
        album_years = (self._album_years(list(tracks) + list(featured))
                      if item == svc.RAIL_ARTISTS and (group_state or featured)
                      else None)
        reorderable = (item == svc.RAIL_PLAYLISTS and not group_state
                      and sort_state == ("position", "asc")
                      and entry is not None and not entry.locked)
        self.panes.set_tracks(
            tracks, label, grouped=group_state, featured_tracks=featured,
            featured_checked=filter_state, sort_fields=sort_fields,
            sort_state=sort_state, show_group=item in svc.DETAIL_GROUP_RAIL_ITEMS,
            show_filter=show_filter, show_count=item != svc.RAIL_ALBUMS,
            album_years=album_years, reorderable=reorderable)

    def _album_years(self, tracks):
        years = {}
        for t in tracks:
            if t.album_id not in years:
                years[t.album_id] = self.service.album_year(t.album_id)
        return years

    def _show_song_list(self, key, label):
        period = self.service.songs_period(key)
        options = tuple((p, svc.SONGS_PERIOD_LABELS[p])
                        for p in svc.SONGS_PERIODS.get(key, ()))
        self.panes.set_tracks(
            self.service.tracks(svc.RAIL_SONGS, key), label, show_count=True,
            sort_fields=svc.SONGS_SORT_FIELDS[key],
            sort_state=self.service.songs_sort_state(key),
            period_options=options, period_state=period, show_play_all=True,
            empty_text=self.service.songs_empty_text(key))

    def _on_entry_activated(self, key):
        item = self.rail.current()
        if item == svc.RAIL_QUEUES:
            self._switch_to_queue(key)
            return
        entry = self.panes.entry_model.entry_at(self.panes.entry_model.row_of(key))
        label = "" if entry is None else entry.label
        tracks, start = self._resolve_rows(self.service.tracks(item, key), 0)
        if not tracks:
            log.warning("nothing in this selection could be found on disk")
            return
        self._start_queue(tracks, start, label=label)

    def _on_entry_context_menu(self, key, global_pos):
        item = self.rail.current()
        checked = self.panes.entry_model.checked_keys()
        keys = checked if checked else {key}
        if item == svc.RAIL_PLAYLISTS:
            self._show_playlist_menu(keys, global_pos)
            return
        if item == svc.RAIL_QUEUES:
            self._show_queue_menu(keys, global_pos)
            return
        if item not in (svc.RAIL_ARTISTS, svc.RAIL_ALBUMS):
            return
        tracks = []
        for k in keys:
            tracks.extend(self.service.tracks(item, k))
        self._show_track_menu(tracks, global_pos)

    def _show_queue_menu(self, queue_ids, global_pos):
        self._build_queue_menu(queue_ids).popup_at(global_pos)

    def _build_queue_menu(self, queue_ids):
        menu = PopupMenu(parent=self)
        if len(queue_ids) == 1:
            (queue_id,) = queue_ids
            menu.add_action("pencil-square", "Rename queue",
                            lambda: self._rename_queue(queue_id))
            menu.add_action("trash", "Delete queue",
                            lambda: self._delete_queues(queue_ids), danger=True)
        else:
            menu.add_action(
                "trash", "Delete {} queues".format(len(queue_ids)),
                lambda: self._delete_queues(queue_ids), danger=True)
        return menu

    def _rename_queue(self, queue_id):
        loaded = self.service.load_queue(queue_id)
        if loaded is None:
            log.warning("rename requested for unknown queue id %s", queue_id)
            return
        ref, _tracks = loaded
        dialog = self.rename_queue_dialog_factory(ref.source_label or "Queue", self)
        if dialog.exec() == QDialog.Accepted and dialog.name():
            self.service.rename_queue(queue_id, dialog.name())
            if queue_id == self.active_queue_id:
                self.queue_source_label = dialog.name()
            self._refresh_queue_pane_if_active()

    def _delete_queues(self, queue_ids):
        was_active = self.active_queue_id in queue_ids
        for queue_id in queue_ids:
            self.service.delete_queue(queue_id)
        if was_active:
            self._switch_to_next_queue_or_stop()
        self._refresh_queue_pane_if_active()

    def _switch_to_next_queue_or_stop(self):
        self.engine.stop()
        listed = self.service.list_queues(self._browse_owner())
        if not listed:
            self.active_queue_id = None
            self.service.set_state("active_queue_id", "")
            self.queue.set_tracks([], -1)
            return
        ref, _count = listed[0]
        loaded = self.service.load_queue(ref.id)
        if loaded is None:
            return
        ref, tracks = loaded
        start = ref.current_pos if 0 <= ref.current_pos < len(tracks) else 0
        self._activate_queue(ref, tracks, start, play=False)
        if start == ref.current_pos and ref.position_seconds > 0:
            self._pending_resume_row = start
            self._pending_resume_seconds = ref.position_seconds

    def _on_track_context_menu(self, row, global_pos):
        rows = self.panes.tracks()
        if not (0 <= row < len(rows)):
            return
        checked = self.panes.track_model.checked_tracks()
        tracks = checked if checked else [rows[row]]
        playlist_id = None
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            playlist_id = self.panes.selected_entry().key
        self._show_track_menu(tracks, global_pos, playlist_id=playlist_id)

    def _on_album_context_menu(self, tracks, global_pos):
        playlist_id = None
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            playlist_id = self.panes.selected_entry().key
        self._show_track_menu(tracks, global_pos, playlist_id=playlist_id)

    def _show_track_menu(self, tracks, global_pos, playlist_id=None):
        self._build_track_menu(tracks, playlist_id=playlist_id).popup_at(global_pos)

    def _build_track_menu(self, tracks, playlist_id=None, queue_context=False):
        menu = PopupMenu(parent=self)
        menu.add_action("plus", "Play next", lambda: self._play_next(tracks))
        menu.add_action("rows-plus-bottom", "Add to currently playing queue",
                        lambda: self._add_to_current_queue(tracks))
        if not self.service.all_mode:
            menu.add_action("playlist", "Add to playlist…",
                            lambda: self._add_to_playlist(tracks))
            menu.add_action("queue", "Add to queue…",
                            lambda: self._add_to_queue_dialog(tracks))
        queue_entry = (self.panes.selected_entry()
                       if self.rail.current() == svc.RAIL_QUEUES
                       and not queue_context else None)
        if playlist_id is not None:
            menu.add_action(
                "trash", "Remove from playlist",
                lambda: self._remove_from_playlist(playlist_id, tracks),
                danger=True, enabled=not self._playlist_locked(playlist_id))
        if queue_entry:
            queue_id = queue_entry.key
            menu.add_action("trash", "Remove from queue",
                            lambda: self._remove_from_queue(queue_id, tracks),
                            danger=True)
        resolved = self._resolve_rows(tracks, 0)[0]
        paths = [t.path for t in resolved]
        menu.add_action("folder-open", "Open in file explorer",
                        lambda: self._reveal_in_explorer(paths),
                        enabled=_explorer_target(paths) is not None)
        if len(resolved) == 1:
            (single,) = resolved
            menu.add_action("info", "Track info",
                            lambda: self._show_track_info(single))
        return menu

    def _add_to_queue_dialog(self, tracks):
        owner = self._browse_owner()
        if owner is None:
            log.warning("Add to queue needs an open library")
            return
        resolved, _ = self._resolve_rows(tracks, 0)
        if not resolved:
            log.warning("nothing in this selection could be found on disk")
            return
        unique = list({track_identity(t): t for t in resolved}.values())
        listed = [ref for ref, _count in self.service.list_queues(owner)]
        membership = self.service.queue_membership([r.id for r in listed], unique)
        dialog = self.add_to_queue_dialog_factory(listed, membership, len(unique), self)
        if dialog.exec() != QDialog.Accepted:
            return
        adds, removes, new_name = dialog.changes()
        added = removed = 0
        for ref in adds:
            if self._add_missing_to_queue(ref.id, unique):
                added += 1
        for ref in removes:
            self._remove_from_queue(ref.id, unique)
            removed += 1
        if new_name:
            self.service.create_queue("manual", new_name, self.service.current.name,
                                      unique, 0, dirty=True, owner_library_id=owner)
            self.service.evict_excess_queues(
                keep=20, protect_id=self.active_queue_id or "", owner_library_id=owner)
            added += 1
        if not added and not removed:
            return
        if added == 1 and not removed:
            message = _queue_add_message(len(unique))
        elif removed == 1 and not added:
            message = _queue_remove_message(len(unique))
        else:
            message = _queue_changes_message(added, removed)
        self.toast.show_message(message)
        self._refresh_queue_pane_if_active()

    def _add_missing_to_queue(self, queue_id, tracks):
        if queue_id != self.active_queue_id:
            return self.service.add_missing_queue_tracks(queue_id, tracks)
        present = {track_identity(t) for t in self.queue.tracks()}
        missing = [t for t in tracks if track_identity(t) not in present]
        if missing:
            self.queue.add(missing)
            self.service.add_queue_items(queue_id, missing)
        return len(missing)

    def _remove_from_playlist(self, playlist_id, tracks):
        for track in tracks:
            self.service.repo.remove_from_playlist(playlist_id, track.id)
        self._refresh_panes()

    def _remove_from_queue(self, queue_id, tracks):
        removed = {track_identity(t) for t in tracks}
        if queue_id != self.active_queue_id:
            if self.service.remove_queue_tracks(queue_id, tracks):
                self._refresh_panes()
            return
        rows = [i for i, t in enumerate(self.queue.tracks())
                if track_identity(t) in removed]
        if not rows:
            return
        self.queue.remove_rows(rows)
        self.service.reorder_queue_items(queue_id, self.queue.tracks())
        self.service.set_queue_position(queue_id, self.queue.resume_index())
        log.info("removed %d item(s) from the playing queue%s", len(rows),
                 " (the playing track keeps playing)"
                 if self.queue.is_detached() else "")
        self._refresh_panes()

    def _on_track_reordered(self):
        entry = self.panes.selected_entry()
        if entry is None:
            return
        if self.rail.current() == svc.RAIL_QUEUES:
            new_order = self.panes.tracks()
            self.service.reorder_queue_items(entry.key, new_order)
            if entry.key == self.active_queue_id:
                self.queue.reorder(new_order)
            self._refresh_queue_pane_if_active()
            return
        track_ids = [t.id for t in self.panes.tracks()]
        self.service.repo.replace_playlist_tracks(entry.key, track_ids)

    def _on_resume_queue_clicked(self):
        entry = self.panes.selected_entry()
        if entry is not None:
            self._switch_to_queue(entry.key)

    def _switch_to_queue(self, queue_id):
        if queue_id == self.active_queue_id:
            if self.engine.state() != "playing":
                self.controller.toggle_play()
            return
        loaded = self.service.load_queue(queue_id)
        if loaded is None:
            log.warning("queue %s no longer exists", queue_id)
            return
        ref, tracks = loaded
        start = ref.current_pos if 0 <= ref.current_pos < len(tracks) else 0
        self._activate_queue(ref, tracks, start)
        if start == ref.current_pos and ref.position_seconds > 0:
            self.engine.seek(ref.position_seconds)

    def _find_playlist(self, playlist_id):
        return next((p for p in self.service.repo.playlists()
                    if p.id == playlist_id), None)

    def _playlist_locked(self, playlist_id):
        playlist = self._find_playlist(playlist_id)
        return playlist is not None and playlist.locked

    def _show_playlist_menu(self, playlist_ids, global_pos):
        self._build_playlist_menu(playlist_ids).popup_at(global_pos)

    def _build_playlist_menu(self, playlist_ids):
        menu = PopupMenu(parent=self)
        if len(playlist_ids) == 1:
            (playlist_id,) = playlist_ids
            locked = self._playlist_locked(playlist_id)
            menu.add_action("pencil-square", "Rename playlist",
                            lambda: self._rename_playlist(playlist_id),
                            enabled=not locked)
            lock_icon = "lock-simple-open" if locked else "lock-simple"
            lock_text = "Unlock playlist" if locked else "Lock playlist"
            menu.add_action(lock_icon, lock_text,
                            lambda: self._set_playlist_locked(playlist_id, not locked))
            menu.add_action("trash", "Delete playlist",
                            lambda: self._delete_playlists(playlist_ids), danger=True,
                            enabled=not locked)
        else:
            menu.add_action(
                "trash", "Delete {} playlists".format(len(playlist_ids)),
                lambda: self._delete_playlists(playlist_ids), danger=True)
        return menu

    def _rename_playlist(self, playlist_id):
        playlist = self._find_playlist(playlist_id)
        if playlist is None:
            log.warning("rename requested for unknown playlist id %s", playlist_id)
            return
        dialog = self.rename_playlist_dialog_factory(playlist.name, self)
        if dialog.exec() == QDialog.Accepted and dialog.name():
            self.service.repo.rename_playlist(playlist_id, dialog.name())
            if self.rail.current() == svc.RAIL_PLAYLISTS:
                self._refresh_panes()

    def _set_playlist_locked(self, playlist_id, locked):
        self.service.repo.set_playlist_locked(playlist_id, locked)
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            self._refresh_panes()

    def _delete_playlists(self, playlist_ids):
        playlists = [p for p in self.service.repo.playlists() if p.id in playlist_ids]
        locked = [p for p in playlists if p.locked]
        unlocked = [p for p in playlists if not p.locked]
        locked_toast = None
        if locked:
            locked_toast = (
                "{} wasn't deleted — it's locked".format(locked[0].name)
                if len(locked) == 1 else
                "{} locked playlists weren't deleted".format(len(locked)))
        if not unlocked:
            if locked_toast:
                self.toast.show_message(locked_toast)
            return
        track_count = sum(len(self.service.tracks(svc.RAIL_PLAYLISTS, p.id))
                          for p in unlocked)
        if len(unlocked) == 1:
            title = "Delete playlist"
            message = ("Delete the playlist “{}”? Its {} won't be "
                      "removed from your library — only the playlist will "
                      "be.".format(unlocked[0].name, _plural(track_count, "track")))
        else:
            title = "Delete playlists"
            message = ("Delete {} playlists? Their tracks won't be removed "
                      "from your library — only the playlists will be."
                      .format(len(unlocked)))
        if not self.confirm(title, message):
            return
        for p in unlocked:
            self.service.repo.delete_playlist(p.id)
        if locked_toast:
            self.toast.show_message(locked_toast)
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            self._refresh_panes()

    def _add_to_playlist(self, tracks):
        if not tracks:
            return
        repo = self.service.repo
        ids = list(dict.fromkeys(t.id for t in tracks))
        dialog = self.add_to_playlist_dialog_factory(
            repo.playlists_by_updated(), repo.playlist_membership(ids),
            len(ids), self)
        if dialog.exec() != QDialog.Accepted:
            return
        adds, removes, new_name = dialog.changes()
        if new_name:
            adds = adds + [repo.create_playlist(new_name)]
        added = []
        for playlist in adds:
            present = set(repo.playlist_track_ids(playlist.id))
            missing = [i for i in ids if i not in present]
            repo.add_to_playlist(playlist.id, missing)
            added.append((playlist, len(missing)))
        removed = []
        for playlist in removes:
            present = set(repo.playlist_track_ids(playlist.id))
            gone = [i for i in ids if i in present]
            repo.remove_tracks_from_playlist(playlist.id, gone)
            removed.append((playlist, len(gone)))
        if not added and not removed:
            return
        if len(added) == 1 and not removed:
            playlist, n = added[0]
            message = _playlist_add_message(n, playlist.name)
        elif len(removed) == 1 and not added:
            playlist, n = removed[0]
            message = _playlist_remove_message(n, playlist.name)
        else:
            message = _playlist_changes_message(len(added), len(removed))
        self.toast.show_message(message)
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            self._refresh_panes()

    def _add_to_current_queue(self, tracks):
        resolved, _ = self._resolve_rows(tracks, 0)
        if not resolved:
            log.warning("nothing in this selection could be found on disk")
            return
        if self.active_queue_id is None:
            self._create_and_activate_queue("manual", "", resolved, 0)
        else:
            unlink = self._would_unlink(resolved)
            resume = self.queue.resume_index()
            self.queue.add(resolved)
            if unlink:
                self._fork_mixed_queue(resume)
            else:
                self.service.add_queue_items(self.active_queue_id, resolved)
            self._refresh_queue_pane_if_active()
        self.toast.show_message(_queue_add_message(len(resolved)))

    def _play_next(self, tracks):
        resolved, _ = self._resolve_rows(tracks, 0)
        if not resolved:
            log.warning("nothing in this selection could be found on disk")
            return
        if self.active_queue_id is None:
            self._create_and_activate_queue("manual", "", resolved, 0)
        else:
            unlink = self._would_unlink(resolved)
            resume = self.queue.resume_index()
            self.queue.insert_after(self.queue.current_index(), resolved)
            if unlink:
                self._fork_mixed_queue(resume)
            else:
                self.service.reorder_queue_items(self.active_queue_id,
                                                 self.queue.tracks())
            self._refresh_queue_pane_if_active()
        self.toast.show_message(_play_next_message(len(resolved)))

    def _would_unlink(self, incoming):
        if self.active_queue_id is None or self.queue_owner_library_id is None:
            return False
        return _owner_of(self.queue.tracks() + list(incoming)) is None

    def _fork_mixed_queue(self, old_resume_row):
        old_id = self.active_queue_id
        seconds = 0.0 if self.queue.is_detached() else self._position
        self.service.set_queue_position(old_id, old_resume_row, seconds)
        ref = self.service.create_queue(
            self.queue_source_kind, self.queue_source_label, "",
            self.queue.tracks(), self.queue.resume_index(), dirty=True,
            owner_library_id=None)
        self.service.evict_excess_queues(keep=20, protect_id=ref.id,
                                         owner_library_id=None)
        log.info("queue %s spans libraries now; continuing as mixed queue %s",
                 old_id, ref.id)
        self._adopt_active_ref(ref)

    def _create_and_activate_queue(self, kind, label, tracks, start):
        owner = _owner_of(tracks)
        ref = self.service.create_queue(kind, label, "", tracks, start,
                                        owner_library_id=owner)
        self.service.evict_excess_queues(keep=20, protect_id=ref.id,
                                         owner_library_id=owner)
        self._activate_queue(ref, tracks, start, touch=False)

    def _on_show_featured_artists_toggled(self, checked):
        self._force_show_featured = False
        self.service.set_filter_featured_artists(checked)
        self._refresh_panes()

    def _on_sort_changed(self, field, direction):
        item = self.rail.current()
        self.service.set_sort_state(item, field, direction)
        self._refresh_panes(item)

    def _on_show_featured_tracks_toggled(self, checked):
        self.service.set_detail_filter_featured_tracks(checked)
        key = self.panes.selected_key()
        if key is not None:
            self._on_entry_selected(key)

    def _on_detail_group_toggled(self, checked):
        item = self.rail.current()
        self.service.set_detail_group_state(item, checked)
        key = self.panes.selected_key()
        if key is not None:
            self._on_entry_selected(key)

    def _on_detail_sort_changed(self, field, direction):
        item = self.rail.current()
        if item == svc.RAIL_SONGS:
            key = self.panes.selected_key()
            if key is not None:
                self.service.set_songs_sort_state(key, field, direction)
                self._on_entry_selected(key)
            return
        group_state = self.service.detail_group_state(item)
        self.service.set_detail_sort_state(item, group_state, field, direction)
        key = self.panes.selected_key()
        if key is not None:
            self._on_entry_selected(key)

    def _on_songs_period_changed(self, period):
        key = self.panes.selected_key()
        if key is None:
            return
        self.service.set_songs_period(key, period)
        self._refresh_panes(svc.RAIL_SONGS)

    def _on_play_all(self):
        tracks, start = self._resolve_rows(self.panes.tracks(), 0)
        if not tracks:
            log.warning("nothing in this list can be played")
            return
        self._start_queue(tracks, start)

    def _on_shuffle_all(self):
        tracks, _start = self._resolve_rows(self.panes.tracks(), 0)
        if not tracks:
            log.warning("nothing in this list can be played")
            return
        shuffled = list(tracks)
        self.shuffle_tracks(shuffled)
        entry = self.panes.selected_entry()
        label = "{} (shuffled)".format(entry.label if entry is not None else "")
        self._start_queue(shuffled, 0, label=label)

    def _refresh_home(self):
        since, until = self.home_page.current_bounds()
        total, tracks, albums, artists = self.service.home_summary(
            since, until, self.home_page.current_metric())
        self.home_page.set_data(total, tracks, albums, artists)
        self.home_page.set_last_added(self.service.recent_additions())
        self.home_page.set_favorites(self.service.favorite_entries())
        self.home_page.set_earliest_play_at(self.service.earliest_play_at())
        self._sync_home_now_playing()
        self._sync_favorite_button()

    def _sync_home_now_playing(self):
        track = self.queue.current_track()
        if self.service.all_mode:
            match_id = (None if track is None or track.track_id is None else
                        self.service.all_libraries.key_for(track.library_id,
                                                           track.track_id))
            self.home_page.set_now_playing(match_id)
            return
        library = self.service.current
        match_id = None
        if (track is not None and track.track_id is not None
                and library is not None and track.library_id == library.id):
            match_id = track.track_id
        self.home_page.set_now_playing(match_id)

    def _on_home_period_changed(self):
        if self.rail.current() == svc.RAIL_HOME:
            self._refresh_home()

    def _on_home_metric_changed(self):
        self.service.set_state("home_recap_metric", self.home_page.current_metric())
        if self.rail.current() == svc.RAIL_HOME:
            self._refresh_home()

    def _on_play_credited(self):
        if self.content_stack.currentWidget() is self.home_page:
            self._refresh_home()

    def _on_home_track_activated(self, track_id):
        if self.service.all_mode:
            track = self.service.all_libraries.best_track(track_id)
            if track is None:
                log.warning("the selected Home track can't be played from any library")
                return
            self._start_queue([track], 0, kind=None, label=track.title)
            return
        row = self.service.track_by_id(track_id)
        if row is None:
            log.warning("the selected Home track no longer exists")
            return
        tracks, start = self._resolve_rows([row], 0)
        if not tracks:
            log.warning("the selected Home track could not be found on disk")
            return
        self._start_queue(tracks, start, kind=None, label=row.title)

    def _on_home_favorite_play(self, track_id):
        if self.service.all_mode:
            pairs = self.service.all_favorite_tracks()
            keys = [key for key, _track in pairs]
            if track_id not in keys:
                log.warning("the selected favorite is no longer playable")
                return
            self._start_queue([t for _key, t in pairs], keys.index(track_id),
                              kind="favorites", label="Favorites")
            return
        rows = self.service.favorite_tracks()
        clicked = next((i for i, r in enumerate(rows) if r.id == track_id), None)
        if clicked is None:
            log.warning("the selected favorite is no longer a favorite")
            return
        tracks, start = self._resolve_rows(rows, clicked)
        if not tracks:
            log.warning("none of the favorites could be found on disk")
            return
        self._start_queue(tracks, start, kind="favorites", label="Favorites")

    def _on_home_favorites_shuffle(self):
        if self.service.all_mode:
            tracks = [t for _key, t in self.service.all_favorite_tracks()]
        else:
            tracks, _start = self._resolve_rows(self.service.favorite_tracks(), 0)
        if not tracks:
            log.warning("none of the favorites could be found on disk")
            return
        shuffled = list(tracks)
        self.shuffle_tracks(shuffled)
        self._start_queue(shuffled, 0, kind="favorites",
                          label="Favorites (shuffled)")

    def _on_home_album_activated(self, key):
        if self.service.all_mode:
            target = self.service.all_libraries.album_target(key)
            if target is None:
                log.warning("no library holds the selected album any more")
                return
            library_id, album_id = target
            self.select_library(library_id)
            self._go_to_album(album_id)
            return
        self._go_to_album(key)

    def _on_home_artist_activated(self, key):
        if self.service.all_mode:
            target = self.service.all_libraries.artist_target(key)
            if target is None:
                log.warning("no library holds the selected artist any more")
                return
            library_id, name = target
            self.select_library(library_id)
            self._go_to_artist(name)
            return
        self._go_to_artist(key)

    def _on_home_last_added_activated(self, key):
        kind, ident = key
        if kind == "album":
            self._on_home_album_activated(ident)
        else:
            self._open_track_in_album(ident)

    def _on_home_last_added_context_menu(self, key, global_pos):
        kind, ident = key
        if kind == "album":
            self._on_home_album_context_menu(ident, global_pos)
        else:
            self._on_home_track_context_menu(ident, global_pos)

    def _open_track_in_album(self, key):
        if self.service.all_mode:
            target = self.service.all_libraries.track_target(key)
            if target is None:
                log.warning("no library holds the selected song any more")
                return
            library_id, album_id, track_id = target
            self.select_library(library_id)
        else:
            row = self.service.track_by_id(key)
            if row is None or row.album_id is None:
                log.warning("the selected song no longer exists")
                return
            album_id, track_id = row.album_id, row.id
        self._go_to_album(album_id)
        self.panes.select_track(track_id)

    def _on_home_last_added_play(self, key):
        kind, ident = key
        if kind == "album":
            self._play_album(ident)
        else:
            self._play_album_from_track(ident)

    def _play_album(self, key):
        if self.service.all_mode:
            target = self.service.all_libraries.album_target(key)
            if target is None:
                log.warning("no library holds the selected album any more")
                return
            tracks, start = self.service.all_libraries.album_tracks(*target), 0
        else:
            tracks, start = self._resolve_rows(
                self.service.tracks(svc.RAIL_ALBUMS, key), 0)
        self._start_album_queue(tracks, start)

    def _play_album_from_track(self, key):
        if self.service.all_mode:
            target = self.service.all_libraries.track_target(key)
            if target is None:
                log.warning("no library holds the selected song any more")
                return
            library_id, album_id, track_id = target
            tracks = self.service.all_libraries.album_tracks(library_id, album_id)
            start = next((i for i, t in enumerate(tracks) if t.track_id == track_id),
                         None)
        else:
            row = self.service.track_by_id(key)
            if row is None or row.album_id is None:
                log.warning("the selected song no longer exists")
                return
            rows = self.service.tracks(svc.RAIL_ALBUMS, row.album_id)
            clicked = next((i for i, r in enumerate(rows) if r.id == row.id), None)
            tracks, start = (self._resolve_rows(rows, clicked)
                             if clicked is not None else ([], None))
        if start is None:
            log.warning("the selected song can't be played")
            return
        self._start_album_queue(tracks, start)

    def _start_album_queue(self, tracks, start):
        if not tracks:
            log.warning("nothing in this album can be played")
            return
        self._start_queue(tracks, start, kind=svc.RAIL_ALBUMS,
                          label=tracks[0].album or svc.UNKNOWN_ALBUM_LABEL)

    def _go_to_album(self, album_id):
        self.rail.set_current(svc.RAIL_ALBUMS)
        self._refresh_panes(svc.RAIL_ALBUMS)
        self.panes.select_entry(album_id)

    def _go_to_artist(self, name):
        self._force_show_featured = True
        self.rail.set_current(svc.RAIL_ARTISTS)
        self._refresh_panes(svc.RAIL_ARTISTS)
        self.panes.select_entry(name)

    def _on_home_track_context_menu(self, track_id, global_pos):
        row = self.service.track_by_id(track_id)
        if row is None:
            log.warning("the selected Home track no longer exists")
            return
        self._show_track_menu([row], global_pos)

    def _on_home_album_context_menu(self, key, global_pos):
        self._show_track_menu(self.service.tracks(svc.RAIL_ALBUMS, key), global_pos)

    def _on_home_artist_context_menu(self, key, global_pos):
        self._show_track_menu(self.service.tracks(svc.RAIL_ARTISTS, key), global_pos)

    def _show_now_playing_menu(self):
        if self.queue.current_track() is None:
            return
        self._build_now_playing_menu().popup_above(self.transport.more_button)

    def _library_row(self, track):
        library = self.service.current
        if (track is None or track.track_id is None or library is None
                or track.library_id != library.id):
            return None
        return self.service.track_by_id(track.track_id)

    def _build_now_playing_menu(self):
        track = self.queue.current_track()
        row = self._library_row(track)
        in_library = row is not None
        menu = PopupMenu(parent=self)
        menu.add_action("album", "Go to album", self._now_playing_go_to_album,
                        enabled=in_library and track.album_id is not None)
        menu.add_action("artist", "Go to artist", self._now_playing_go_to_artist,
                        enabled=in_library)
        menu.add_action("playlist", "Add to playlist…",
                        lambda: self._add_to_playlist([row]), enabled=in_library)
        menu.add_action("queue", "Add to queue…",
                        lambda: self._add_to_queue_dialog([row]), enabled=in_library)
        favorite = in_library and self.service.is_favorite(row.id)
        menu.add_action("fav-break" if favorite else "fav",
                        "Remove from favorites" if favorite else "Add to favorites",
                        self._toggle_favorite, enabled=in_library)
        menu.add_action("crosshair", "Locate in queue", self._locate_in_queue)
        menu.add_action("folder-open", "Open in file explorer",
                        lambda: self._reveal_in_explorer([track.path]),
                        enabled=os.path.exists(track.path))
        menu.add_action("info", "Track info",
                        lambda: self._show_track_info(track))
        return menu

    def _locate_in_queue(self):
        self.rail.set_current(svc.RAIL_QUEUES)
        self._refresh_panes(svc.RAIL_QUEUES)

    def eventFilter(self, obj, event):
        if obj is self.root_stack and event.type() == QEvent.Resize:
            self.now_playing_page.snap_to(self.root_stack.rect())
        return super().eventFilter(obj, event)

    def _toggle_now_playing_page(self):
        page = self.now_playing_page
        if page.is_open():
            page.close_down()
            return
        if self.queue.current_track() is None and self.queue.rowCount() == 0:
            return
        page.open_over(self.root_stack.rect())
        self._sync_now_playing_page()

    def _sync_now_playing_page(self, *_args):
        page = self.now_playing_page
        if not page.is_open():
            return
        track = self.queue.current_track()
        now_playing = (None if track is None
                       else (track.track_id, track.library_id, track.path))
        page.set_queue(self.queue.tracks(), self.queue.playing_row(), now_playing)
        page.set_header(self.queue_source_label or "Queue", self._owner_text())
        if track is None:
            page.set_art(None, None)
            return
        page.set_art(self._load_artwork(track),
                     (track.track_id, track.library_id, track.path))

    def _owner_text(self):
        if self.queue_owner_library_id is None:
            return "Mixed"
        library = self.service.app_repo.library(self.queue_owner_library_id)
        return library.name if library is not None else ""

    def _album_line(self, track):
        if not track.album:
            return ""
        library = self.service.current
        if (track.album_id is None or library is None or self.service.repo is None
                or track.library_id != library.id):
            return track.album
        year = (self.service.repo.album_release_date_for_id(track.album_id) or "")[:4]
        return "{} • {}".format(track.album, year) if year else track.album

    def _on_now_playing_row_activated(self, row):
        if 0 <= row < self.queue.rowCount():
            self.controller.play_index(row)

    def _on_now_playing_reordered(self, new_order):
        if self.active_queue_id is None:
            return
        self.queue.reorder(new_order)
        self.service.reorder_queue_items(self.active_queue_id, self.queue.tracks())
        self._refresh_queue_pane_if_active()

    def _on_now_playing_row_menu(self, row, global_pos):
        self._build_now_playing_queue_menu(row).popup_at(global_pos)

    def _build_now_playing_queue_menu(self, row):
        track = self.queue.track_at(row)
        menu = self._build_track_menu([track], queue_context=True)
        if self.active_queue_id is not None:
            queue_id = self.active_queue_id
            menu.add_action("trash", "Remove from queue",
                            lambda: self._remove_from_queue(queue_id, [track]),
                            danger=True)
        return menu

    def _now_playing_navigate(self, go):
        track = self.queue.current_track()
        self.now_playing_page.close_down()
        if track is None or track.library_id is None:
            log.warning("the playing track belongs to no library: nowhere to go")
            return
        current = self.service.current
        if current is None or current.id != track.library_id:
            self.select_library(track.library_id)
        go(track)

    def _now_playing_go_to_artist(self):
        self._now_playing_navigate(
            lambda t: self._go_to_artist(self._display_artist_for(t)))

    def _now_playing_go_to_album(self):
        def go(track):
            if track.album_id is not None:
                self._go_to_album(track.album_id)
        self._now_playing_navigate(go)

    def _favorite_target(self):
        track = self.queue.current_track()
        if self.service.all_mode:
            if track is None or track.track_id is None:
                return None
            return track.library_id, track.track_id
        row = self._library_row(track)
        return None if row is None else (self.service.current.id, row.id)

    def _toggle_favorite(self):
        target = self._favorite_target()
        if target is None:
            log.warning("the playing track isn't in an open library: "
                        "cannot change its favorite")
            return
        on = not self.service.is_favorite_for(*target)
        self.service.set_favorite_for(*target, on)
        self.toast.show_message(
            "Added to favorites" if on else "Removed from favorites")
        self._sync_favorite_button()
        if self.content_stack.currentWidget() is self.home_page:
            self._refresh_home()

    def _sync_favorite_button(self):
        target = self._favorite_target()
        self.transport.set_favorite_enabled(target is not None)
        self.transport.set_favorite(
            target is not None and self.service.is_favorite_for(*target))

    def _show_track_info(self, track):
        details = read_file_details(track.path)
        row = self._library_row(track)
        stats = self._play_stats_or_none(row)
        info = build_track_info(track, details, row, stats)
        dialog = self.track_info_dialog_factory(
            info, self._load_artwork(track), self)
        if info.listening is not None:
            dialog.resetRequested.connect(
                lambda: self._reset_track_plays(dialog, row, info.title))
        dialog.exec()

    def _play_stats_or_none(self, row):
        if row is None:
            return None
        try:
            return self.service.play_stats(row.id)
        except sqlite3.Error:
            log.exception("could not read play stats for track %s", row.id)
            return None

    def _reset_track_plays(self, dialog, row, title):
        stats = self._play_stats_or_none(row)
        if not stats or not stats[0]:
            return
        count = stats[0]
        plays = ("1 recorded play" if count == 1
                 else "{} recorded plays".format(count))
        if not self.confirm(
                "Reset play stats?",
                "This permanently deletes the {} of “{}”. It will also "
                "drop out of Home's top lists.".format(plays, title)):
            return
        try:
            self.service.reset_plays(row.id)
        except sqlite3.Error:
            log.exception("could not reset play stats for track %s", row.id)
            self.report_error("Couldn't reset play stats",
                              "The library could not be updated.")
            return
        fresh = self._play_stats_or_none(row) or (0, None, None)
        dialog.set_listening(listening_rows(row, fresh), fresh[0])
        self.toast.show_message("Play stats reset")
        if self.content_stack.currentWidget() is self.home_page:
            self._refresh_home()

    def _on_track_activated(self, row):
        if self.rail.current() == svc.RAIL_QUEUES:
            shown_id = self.panes.selected_entry().key
            if shown_id == self.active_queue_id:
                if 0 <= row < self.queue.rowCount():
                    self.controller.play_index(row)
                return
            loaded = self.service.load_queue(shown_id)
            if loaded is None:
                log.warning("activated a track in a queue that no longer exists")
                return
            ref, tracks = loaded
            if not (0 <= row < len(tracks)):
                return
            self._activate_queue(ref, tracks, row)
            return
        rows = self.panes.tracks()
        if not (0 <= row < len(rows)):
            return
        tracks, start = self._resolve_rows(rows, row)
        if not tracks:
            log.warning("nothing in this selection could be found on disk")
            return
        self._start_queue(tracks, start)

    def _on_album_activated(self, tracks):
        resolved, start = self._resolve_rows(tracks, 0)
        if not resolved:
            log.warning("nothing in this album could be found on disk")
            return
        self._start_queue(resolved, start)

    def _start_queue(self, tracks, start, kind=_UNSET, label=_UNSET):
        if kind is _UNSET:
            kind = self.rail.current()
        if label is _UNSET:
            entry = self.panes.selected_entry()
            label = "" if entry is None else entry.label
        owner = None if self.service.all_mode else _owner_of(tracks)
        if ((kind, label, owner) == (self.queue_source_kind,
                                     self.queue_source_label,
                                     self.queue_owner_library_id)
                and self.active_queue_id is not None
                and not self._active_queue_is_edited()):
            self.service.replace_queue_items(self.active_queue_id, tracks)
            self.queue.set_tracks(tracks, start)
            self.service.set_queue_position(self.active_queue_id, start)
            self.controller.play_index(start)
            return
        existing_id = self.service.find_pristine_queue(kind, label, owner)
        if existing_id is not None:
            ref, existing_tracks = self.service.load_queue(existing_id)
            if [track_identity(t) for t in existing_tracks] == \
                    [track_identity(t) for t in tracks]:
                self._activate_queue(ref, existing_tracks, start)
                return
            self.service.replace_queue_items(existing_id, tracks)
            self._activate_queue(ref, tracks, start)
            return
        library = self.service.current
        source_library = "" if library is None else library.name
        ref = self.service.create_queue(kind, label, source_library, tracks, start,
                                        owner_library_id=owner)
        self.service.evict_excess_queues(keep=20, protect_id=ref.id,
                                         owner_library_id=owner)
        self._activate_queue(ref, tracks, start, touch=False)

    def _browse_owner(self):
        library = self.service.current
        return None if library is None else library.id

    def _adopt_active_ref(self, queue_ref):
        self.active_queue_id = queue_ref.id
        self.service.set_state("active_queue_id", queue_ref.id)
        self.queue_source_kind = queue_ref.source_kind
        self.queue_source_label = queue_ref.source_label
        self.queue_owner_library_id = queue_ref.owner_library_id

    def _active_queue_is_edited(self):
        ref = (self.service.queue_ref(self.active_queue_id)
               if self.active_queue_id is not None else None)
        return ref is not None and ref.dirty

    def _activate_queue(self, queue_ref, tracks, start, touch=True, play=True):
        if self.active_queue_id is not None and self.active_queue_id != queue_ref.id:
            seconds = 0.0 if self.queue.is_detached() else self._position
            self.service.set_queue_position(
                self.active_queue_id, self.queue.resume_index(), seconds)
        self._pending_resume_row = None
        self._pending_resume_seconds = 0.0
        self._adopt_active_ref(queue_ref)
        self.queue.set_tracks(tracks, start)
        if touch:
            self.service.touch_queue(queue_ref.id)
        if play:
            self.controller.play_index(start)
        self._refresh_queue_pane_if_active()

    def _resolve_rows(self, rows, clicked):
        library = self.service.current
        library_id = None if library is None else library.id
        roots = {root.id: root.path for root in self.service.roots()}
        reachable = {}
        tracks = []
        start = None
        for position, row in enumerate(rows):
            track = self._playable_track(row, library_id, roots, reachable)
            if track is None:
                continue
            if start is None and position >= clicked:
                start = len(tracks)
            tracks.append(track)
        if start is None and tracks:
            log.warning("the clicked track and everything after it can't be "
                        "played; starting at the last playable track before it")
            start = len(tracks) - 1
        return tracks, (0 if start is None else start)

    def _playable_track(self, row, library_id, roots, reachable):
        if isinstance(row, Track):
            return row if row.available else None
        if not row.available:
            return None
        root_path = roots.get(row.root_hint_id)
        if root_path is None:
            resolver = self.service.resolver
            path = (resolver.resolve(row.rel_path, row.root_hint_id)[0]
                    if resolver is not None else None)
        else:
            if root_path not in reachable:
                reachable[root_path] = os.path.isdir(root_path)
            path = (paths.to_abs(root_path, row.rel_path)
                    if reachable[root_path] else None)
        if path is None:
            return None
        return Track(path=path, title=row.title, artist=row.artist,
                     album=row.album, duration=row.duration,
                     album_id=row.album_id, track_id=row.id,
                     library_id=library_id)

    def _on_queue_current_changed(self, row):
        if self.rail.current() == svc.RAIL_QUEUES:
            self.panes.highlight_detail_row(row)

    def confirm(self, title, text):
        answer = QMessageBox.question(self, title, text,
                                      QMessageBox.Yes | QMessageBox.No)
        return answer == QMessageBox.Yes

    def report_error(self, title, text):
        QMessageBox.critical(self, title, text)

    def report_info(self, title, text):
        QMessageBox.information(self, title, text)

    def launch_explorer(self, args):
        if not QProcess.startDetached("explorer", args):
            log.warning("could not start explorer with %r", args)

    def _reveal_in_explorer(self, paths):
        target = _explorer_target(paths)
        if target is None:
            log.warning("nothing to show in file explorer for %d path(s)",
                        len(paths))
            return
        kind, value = target
        value = os.path.normpath(value)
        self.launch_explorer(["/select,", value] if kind == "select" else [value])

    def pick_export_path(self, suggested):
        path, _ = QFileDialog.getSaveFileName(
            self, "Back up play history & playlists", suggested,
            porting.FILE_FILTER)
        if path and not path.lower().endswith(".zip"):
            path += ".zip"
        return path

    def on_add_library(self):
        if self._scan_worker is not None:
            return
        self._begin_setup()

    def _other_libraries(self, library_id=None):
        return [l for l in self.service.libraries() if l.id != library_id]

    def _begin_setup(self):
        current = self.service.current
        self._wizard_library_id = None
        self._wizard_return_id = current.id if current is not None else None
        can_cancel = bool(self._other_libraries())
        self.setup_wizard.begin(can_cancel)
        self._show_setup_page(can_cancel)

    def _resume_setup(self):
        library = self.service.current
        self._wizard_library_id = library.id
        others = self._other_libraries(library.id)
        self._wizard_return_id = others[0].id if others else None
        roots = {r.id: r.path for r in self.service.roots()}
        excludes = [paths.to_abs(roots[e.root_id], e.rel_path)
                    for e in self.service.exclusions() if e.root_id in roots]
        self.setup_wizard.resume(
            {"name": library.name, "color": library.color, "icon": library.icon},
            list(roots.values()), excludes, can_cancel=bool(others))
        self._show_setup_page(bool(others))
        if self.service.has_scanned():
            self.setup_wizard.show_import(self.service.track_count())
        else:
            self._start_scan(library, root_ids=None, sink=self.setup_wizard)

    def _on_setup_create(self, values):
        if self._scan_worker is not None:
            return
        try:
            library = self.service.create_library(
                values["name"], values["color"], values["roots"], values["icon"],
                exclusions=values["exclusions"], setup_pending=True)
        except Exception as exc:
            log.exception("could not create library %r", values["name"])
            self.setup_wizard.show_folders(
                "Could not create the library: {}".format(exc))
            return
        self._wizard_library_id = library.id
        try:
            self.service.open_library(library.id)
        except (LibraryCorruptError, SchemaTooNewError):
            log.exception("could not open the new library %s", library.id)
            self._abandon_setup_library()
            self.setup_wizard.show_folders("Could not open the new library.")
            return
        self.service.set_state("current_library_id", str(library.id))
        self._refresh_library_bar()
        self._start_scan(library, root_ids=None, sink=self.setup_wizard)

    def _on_setup_scan_ended(self, result):
        if result.cancelled:
            self._abandon_setup_library()
            self.setup_wizard.show_folders()
            return
        self.setup_wizard.show_import(self.service.track_count())

    def _on_setup_scan_failed(self, message):
        self.report_error("Scan failed", message)
        self._abandon_setup_library()
        self.setup_wizard.show_folders()

    def _abandon_setup_library(self):
        library_id = self._wizard_library_id
        self._wizard_library_id = None
        if library_id is None:
            return
        try:
            self.service.delete_library(library_id)
        except Exception:
            log.exception("could not delete abandoned library %s", library_id)
        self._refresh_library_bar()

    def _on_setup_import(self, path):
        try:
            result = self.service.import_library_data(path)
        except porting.LibraryDataError as exc:
            log.warning("refused library data %s: %s", path, exc)
            self.setup_wizard.show_import_error(str(exc))
            return
        except Exception as exc:
            log.exception("importing library data from %s failed", path)
            self.setup_wizard.show_import_error("Could not restore: {}".format(exc))
            return
        self.library_import_dialog_factory(result, self).exec()
        self.setup_wizard.mark_imported(import_summary(result))

    def _on_setup_finished(self):
        library_id = self._wizard_library_id
        self._wizard_library_id = None
        try:
            self.service.finish_setup()
        except sqlite3.Error:
            log.exception("could not mark library %s as set up", library_id)
        self.select_library(library_id)

    def _on_setup_cancel(self):
        ids = [l.id for l in self.service.libraries()]
        target = self._wizard_return_id if self._wizard_return_id in ids else None
        if target is None and ids:
            target = ids[0]
        if target is None:
            log.warning("setup cancel with no library to return to")
            return
        self.select_library(target)

    def on_open_settings(self):
        self.settings_overlay.open()

    def on_open_library_settings(self):
        if self.service.current is None or self._scan_worker is not None:
            return
        dialog = self.library_settings_dialog_factory(self.service, self)
        dialog.libraryChanged.connect(self._on_library_changed)
        dialog.scanRequested.connect(self._on_settings_scan_requested)
        dialog.exportRequested.connect(self.on_export_library_data)
        self._settings_dialog = dialog
        dialog.exec()
        self._settings_dialog = None
        self._on_library_changed()
        if dialog.delete_requested:
            self._delete_library(self.service.current)
        elif dialog.exclusions_changed:
            self._start_scan(self.service.current, root_ids=None)
        elif dialog.added_root_ids:
            self._start_scan(self.service.current, root_ids=dialog.added_root_ids)

    def on_export_library_data(self):
        library = self.service.current
        if library is None or not self.service.is_open():
            return
        start_dir = (self.service.get_state("last_export_dir")
                     or os.path.expanduser("~"))
        dest = self.pick_export_path(
            os.path.join(start_dir, porting.export_file_name(library.name)))
        if not dest:
            return
        self.service.set_state("last_export_dir", os.path.dirname(dest))
        try:
            counts = self.service.export_library_data(dest)
        except Exception as exc:
            log.exception("exporting library data to %s failed", dest)
            self.report_error("Could not save the backup", str(exc))
            return
        if counts is None:
            self.report_info("Nothing to back up yet",
                             "This library has no play history, playlists "
                             "or favorites yet.")
            return
        self.report_info("Backup saved", "Backed up {}, {} and {}.".format(
            _count(counts["plays"], "play"), _count(counts["playlists"], "playlist"),
            _count(counts["favorites"], "favorite")))

    def _on_settings_scan_requested(self):
        self._settings_dialog.set_scanning(True)
        self._start_scan(self.service.current, root_ids=None)

    def _delete_library(self, library):
        if (self.queue_owner_library_id == library.id
                and self.active_queue_id is not None):
            self.engine.stop()
            self.active_queue_id = None
            self.queue_owner_library_id = None
            self.service.set_state("active_queue_id", "")
            self.queue.set_tracks([], -1)
        self.service.delete_library(library.id)
        remaining = self.service.libraries()
        if remaining:
            self.select_library(remaining[0].id)
        else:
            self.service.set_state("current_library_id", "")
            self._enter_no_library_ui()

    def _on_library_changed(self):
        self._refresh_library_bar()
        self._refresh_panes()

    def _start_scan(self, library, root_ids, sink=None):
        if self._scan_worker is not None:
            return
        self.library_bar.setEnabled(False)
        path = self.service.library_path(library)
        self.service.close_all()
        self.service.close_current()
        self._scan_sink = sink if sink is not None else self.overlay
        self._scan_sink.start(library.name)
        worker = self.worker_factory(path, root_ids, self)
        worker.progress.connect(self._scan_sink.set_progress)
        worker.finished_ok.connect(self._on_scan_finished)
        worker.failed.connect(self._on_scan_failed)
        self._scan_worker = worker
        self._scan_library_id = library.id
        log.info("scanning %s (roots=%s)", library.name, root_ids or "all")
        worker.start()

    def _on_scan_finished(self, result):
        log.info("scan finished: %s", result)
        scanned_id = self._scan_library_id
        self._end_scan()
        if result.relinks:
            moves = self.service.apply_relinks(scanned_id, result.relinks)
            self.queue.relink(scanned_id, moves)
        self._scan_sink.show_result(result)

    def _on_scan_failed(self, message):
        log.error("scan failed: %s", message)
        self._end_scan()
        self._scan_sink.show_failure(message)

    def _end_scan(self):
        self._scan_worker = None
        self.library_bar.setEnabled(True)
        target = self._pending_library_id
        self._pending_library_id = None
        if target is not None:
            self.select_library(target)
        else:
            stale_id = self.service.current.id if self.service.current is not None else None
            try:
                self.service.reopen_current()
            except (LibraryCorruptError, SchemaTooNewError):
                log.exception("could not reopen library %s after a scan", stale_id)
                self.panes.clear()
                self.rail.set_library_available(False)
            self._refresh_library_bar()
            self._refresh_panes()
        if self._settings_dialog is not None:
            self._settings_dialog.set_scanning(False)
            self._settings_dialog.refresh_info()

    def _on_scan_cancel(self):
        if self._scan_worker is not None:
            self._scan_worker.cancel()

    def _on_scan_dismissed(self):
        self._refresh_library_bar()

    def open_file_dialog(self):
        pattern = " ".join("*{}".format(e) for e in AUDIO_EXTENSIONS)
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add audio files", "", "Audio ({})".format(pattern))
        if paths:
            self.add_paths(paths)

    def on_import_playlists(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import playlists", "", "Playlists (*.m3u *.m3u8)")
        if paths:
            self._finish_import(paths)

    def _finish_import(self, paths):
        results = self.service.import_playlists(paths)
        self.import_results_dialog_factory(results, self).exec()
        if self.rail.current() == svc.RAIL_PLAYLISTS:
            self._refresh_panes()

    def add_paths(self, paths):
        tracks = []
        for path in paths:
            if str(path).lower().endswith(AUDIO_EXTENSIONS):
                tracks.append(self._track_from_path(path))
        if not tracks:
            return
        if self.active_queue_id is None:
            owner = _owner_of(tracks)
            ref = self.service.create_queue(None, "", "", tracks, -1,
                                            owner_library_id=owner)
            self.service.evict_excess_queues(keep=20, protect_id=ref.id,
                                             owner_library_id=owner)
            self._adopt_active_ref(ref)
            self.queue.set_tracks(tracks, -1)
        else:
            unlink = self._would_unlink(tracks)
            resume = self.queue.resume_index()
            self.queue.add(tracks)
            if unlink:
                self._fork_mixed_queue(resume)
            else:
                self.service.add_queue_items(self.active_queue_id, tracks)
        self._refresh_queue_pane_if_active()

    def _track_from_path(self, path):
        track = Track.from_path(path)
        found = self.service.find_track_by_path(path)
        if found is None:
            return track
        library_id, track_id = found
        return replace(track, track_id=track_id, library_id=library_id)

    def _on_transport_files_dropped(self, paths):
        tracks = [self._track_from_path(p) for p in paths]
        if not tracks:
            return
        self._create_and_activate_queue(None, "", tracks, 0)

    def _refresh_queue_pane_if_active(self):
        if self.rail.current() == svc.RAIL_QUEUES:
            self._refresh_panes()

    def _paths_from_mime(self, mime):
        return playlist_file.expand_paths(dnd.local_paths_from_mime(mime))

    def _has_droppable_files(self, mime):
        return any(playlist_file.is_droppable(p)
                  for p in dnd.local_paths_from_mime(mime))

    def _can_append(self):
        return self.rail.current() == svc.RAIL_QUEUES

    def dragEnterEvent(self, event):
        if self._can_append() and self._has_droppable_files(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self._can_append() and self._has_droppable_files(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not self._can_append():
            return
        paths = self._paths_from_mime(event.mimeData())
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    def _display_artist_for(self, track):
        if track.album_id is None or track.library_id is None:
            return track.artist
        album_artist = self.service.album_artist_for(track.library_id, track.album_id)
        return display_artist(track.artist, album_artist)

    _SLOW_SWITCH_S = 0.15

    def _on_current_changed(self, row):
        t0 = time.monotonic()
        if self.active_queue_id is not None:
            self.service.set_queue_position(self.active_queue_id, row)
        t1 = time.monotonic()
        track = self.queue.track_at(row)
        if track is None:
            self.transport.show_track("")
            self.panes.track_model.set_now_playing(None, None, None)
            self._sync_home_now_playing()
            self._sync_favorite_button()
            return
        artist = self._display_artist_for(track)
        t2 = time.monotonic()
        pixmap = self._load_artwork(track)
        t3 = time.monotonic()
        self.transport.show_track(track.title, artist, self._album_line(track),
                                  pixmap)
        self.panes.track_model.set_now_playing(
            track.track_id, track.library_id, track.path)
        self._sync_home_now_playing()
        self._sync_favorite_button()
        t4 = time.monotonic()
        if not self._restoring:
            self.notifications.notify(track, pixmap, artist)
        total = t4 - t0
        log.debug(
            "_on_current_changed(%r): queue_pos=%.1fms display_artist=%.1fms "
            "artwork=%.1fms rest=%.1fms total=%.1fms",
            track.title, (t1 - t0) * 1000, (t2 - t1) * 1000,
            (t3 - t2) * 1000, (t4 - t3) * 1000, total * 1000)
        if total > self._SLOW_SWITCH_S:
            log.warning(
                "slow _on_current_changed(%r): queue_pos=%.1fms "
                "display_artist=%.1fms artwork=%.1fms rest=%.1fms total=%.1fms",
                track.title, (t1 - t0) * 1000, (t2 - t1) * 1000,
                (t3 - t2) * 1000, (t4 - t3) * 1000, total * 1000)

    def _on_position_changed(self, seconds):
        self._position = seconds

    def _load_artwork(self, track):
        if track.album_id:
            cached = QPixmap(locations.art_path(track.album_id))
            if not cached.isNull():
                return cached
        data = extract_cover(track.path)
        if not data:
            return None
        pixmap = QPixmap()
        if pixmap.loadFromData(data) and not pixmap.isNull():
            return pixmap
        return None

    def _on_state_changed(self, state):
        self.transport.set_playing(state == "playing")
        if state == "playing":
            if (self._pending_resume_seconds > 0
                    and self.queue.current_index() == self._pending_resume_row):
                self.engine.seek(self._pending_resume_seconds)
            self._pending_resume_row = None
            self._pending_resume_seconds = 0.0

    def _stop(self):
        self._pending_resume_row = None
        self._pending_resume_seconds = 0.0
        self.controller.stop()

    def _on_error(self, message):
        log.warning("playback error: %s", message)
        self.transport.set_now_playing(message, "")
        QTimer.singleShot(5000, self, self._restore_now_playing)

    def _restore_now_playing(self):
        track = self.queue.current_track()
        if track is not None:
            self.transport.set_now_playing(
                track.title, self._display_artist_for(track),
                self._album_line(track))
        else:
            self.transport.set_now_playing("")

    def _refresh_transport_enabled(self, *_args):
        self.transport.set_enabled_controls(self.queue.rowCount() > 0)

    def _toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()

    def _start_hover_correction_timer(self):
        self._hover_corrected_widget = None
        self._hover_override_shape = None
        timer = QTimer(self)
        timer.setInterval(250)

        timer.timeout.connect(self._poll_hover_correction)
        timer.start()
        self._hover_correction_timer = timer

    def _poll_hover_correction(self):
        cursor_widget = QApplication.widgetAt(QCursor.pos())
        target = (cursor_widget if cursor_widget is not None
                 and cursor_widget.window() is self else None)

        previous = self._hover_corrected_widget
        if previous is not None and not shiboken6.isValid(previous):
            previous = self._hover_corrected_widget = None
        if target is not previous:
            if previous is not None and previous.underMouse():
                QApplication.sendEvent(previous, QEvent(QEvent.Leave))
            self._hover_corrected_widget = target
        if target is not None and not target.underMouse():
            QApplication.sendEvent(target, QEvent(QEvent.Enter))

        shape = target.cursor().shape() if target is not None else None
        if shape == Qt.ArrowCursor:
            shape = None
        if shape != self._hover_override_shape:
            if self._hover_override_shape is not None:
                QApplication.restoreOverrideCursor()
            if shape is not None:
                QApplication.setOverrideCursor(QCursor(shape))
            self._hover_override_shape = shape

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self.title_bar.set_maximized(bool(self.windowState() & Qt.WindowMaximized))
        elif event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self.resync_hover_at_cursor()

    def resync_hover_at_cursor(self):
        pos = QCursor.pos()
        widget = QApplication.widgetAt(pos)
        log.debug("resync_hover_at_cursor: cursor=%s widgetAt=%r "
                 "window_match=%s underMouse=%s", pos, widget,
                 widget is not None and widget.window() is self,
                 widget.underMouse() if widget is not None else None)
        if widget is not None and widget.window() is self and not widget.underMouse():
            QApplication.sendEvent(widget, QEvent(QEvent.Enter))
            log.debug("resync_hover_at_cursor: sent Enter to %r, "
                     "underMouse now %s", widget, widget.underMouse())

    def showEvent(self, event):
        super().showEvent(event)
        if not self._frameless_installed:
            self._frameless_installed = True
            frameless.install(self)
            self.media_keys.install(self)
            self.power_watcher.install(QApplication.instance())
        self._maybe_align_initial_split()

    def _maybe_align_initial_split(self):
        if (self._split_aligned or not self.isVisible()
                or self.root_stack.currentWidget() is not self.browse_page):
            return
        self._split_aligned = True
        QTimer.singleShot(0, self, self._align_initial_split)

    def _align_initial_split(self):
        dropdown_right = self.library_bar.mapTo(
            self, self.library_bar.rect().topRight()).x()
        panes_left = self.panes.mapTo(self, self.panes.rect().topLeft()).x()
        self.panes.align_split(dropdown_right - panes_left)

    def closeEvent(self, event):
        if self._closed:
            super().closeEvent(event)
            return
        self._closed = True
        self.media_keys.uninstall()
        self.idle_release.stop()
        self._hover_correction_timer.stop()
        if self._hover_override_shape is not None:
            QApplication.restoreOverrideCursor()
            self._hover_override_shape = None
        self.service.set_state("volume", str(self.transport.unmuted_volume()))
        self.service.set_state("repeat", self.controller.repeat)
        self.service.set_state("shuffle", "1" if self.controller.shuffle else "0")
        self.service.set_state(
            "position_seconds",
            "0" if self.queue.is_detached() else str(self._position))
        self.service.set_state(
            "window_geometry", bytes(self.saveGeometry().toBase64()).decode("ascii"))
        self.engine.stop()
        self.engine.shutdown_wait()
        progress = self.play_tracker.serialize()
        if progress is None:
            self.service.set_state("now_playing_track_id", "")
            self.service.set_state("now_playing_library_id", "")
            self.service.set_state("now_playing_accumulated", "0")
            self.service.set_state("now_playing_credited", "0")
        else:
            track_id, library_id, accumulated, credited = progress
            self.service.set_state("now_playing_track_id", track_id)
            self.service.set_state("now_playing_library_id", library_id or "")
            self.service.set_state("now_playing_accumulated", str(accumulated))
            self.service.set_state("now_playing_credited", "1" if credited else "0")
        self.notifications.close()
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            if not self._scan_worker.wait(5000):
                log.warning("scan still running 5 s after cancel at quit; "
                            "waiting for it to stop")
                self._scan_worker.wait()
            self._scan_worker = None
        self.service.close()
        super().closeEvent(event)
