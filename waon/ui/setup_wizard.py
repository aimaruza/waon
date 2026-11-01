
import logging
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QProgressBar, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout,
    QWidget,
)

from waon.library import paths
from waon.library.porting import FILE_FILTER
from waon.ui import theme
from waon.ui.elided_label import ElidedLabel
from waon.ui.icons import IconButton, render_icon
from waon.ui.library_dialog import LibraryInfoForm
from waon.ui.welcome_page import WelcomePage

log = logging.getLogger(__name__)

PAGE_WELCOME, PAGE_LIBRARY, PAGE_FOLDERS, PAGE_SCANNING, PAGE_IMPORT = range(5)

_STEP_OF_PAGE = {PAGE_WELCOME: 0, PAGE_LIBRARY: 1, PAGE_FOLDERS: 2,
                 PAGE_SCANNING: 2, PAGE_IMPORT: 3}
STEP_COUNT = 4

NEXT_SIZE = 52
NEXT_ICON = 22
FOOTER_H = NEXT_SIZE + 32
_NEXT_TIP = {PAGE_WELCOME: "Get started", PAGE_LIBRARY: "Next",
             PAGE_FOLDERS: "Scan", PAGE_IMPORT: "Finish"}


def _same(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


class StepDots(QWidget):

    DOT = 8
    GAP = 10

    def __init__(self, count, parent=None):
        super().__init__(parent)
        self._count = count
        self._current = 0
        self.setFixedSize(count * self.DOT + (count - 1) * self.GAP, self.DOT)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def count(self):
        return self._count

    def current(self):
        return self._current

    def set_current(self, index):
        self._current = index
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        for i in range(self._count):
            painter.setBrush(QColor(theme.BRAND if i == self._current
                                    else theme.TOGGLE_OFF))
            painter.drawEllipse(i * (self.DOT + self.GAP), 0, self.DOT, self.DOT)
        painter.end()


CRUMB = u" \u203a "
ELLIPSIS = u"\u2026"


def _crumbs(path):
    drive, rest = os.path.splitdrive(os.path.normpath(path))
    parts = [p for p in rest.replace("\\", "/").split("/") if p]
    return ([drive] if drive else []) + parts


class BreadcrumbLabel(QLabel):

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self._parts = _crumbs(path)
        self.setToolTip(os.path.normpath(path))
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(40)
        self._refit()

    def full_text(self):
        return CRUMB.join(self._parts)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refit()

    def _refit(self):
        metrics = self.fontMetrics()
        width = max(self.width(), 1)
        parts = self._parts
        text = CRUMB.join(parts)
        dropped = 0
        while metrics.horizontalAdvance(text) > width and len(parts) - dropped > 2:
            dropped += 1
            text = CRUMB.join(parts[:1] + [ELLIPSIS] + parts[1 + dropped:])
        if metrics.horizontalAdvance(text) > width:
            text = metrics.elidedText(text, Qt.ElideMiddle, width)
        super().setText(text)


class _PathRow(QWidget):

    removeRequested = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.setObjectName("FolderRow")
        self.path = path
        self.remove_button = IconButton("minus-circle", "Remove", icon_size=18,
                                        diameter=28, pill_hover=False)
        self.remove_button.clicked.connect(lambda: self.removeRequested.emit(self.path))
        self.path_label = BreadcrumbLabel(path)
        self.path_label.setObjectName("RootPath")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 12, 4)
        layout.setSpacing(8)
        layout.addWidget(self.remove_button)
        layout.addWidget(self.path_label, 1)


class _PathList(QWidget):

    addRequested = Signal()
    removeRequested = Signal(str)

    def __init__(self, caption, add_text, parent=None):
        super().__init__(parent)
        title = QLabel(caption)
        title.setObjectName("WizardSectionTitle")

        self.card = QWidget()
        self.card.setObjectName("FolderCard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        self.list_widget = QListWidget()
        self.list_widget.setObjectName("FolderCardList")
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setFrameShape(QListWidget.NoFrame)
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        divider = QWidget()
        divider.setObjectName("FolderCardDivider")
        divider.setFixedHeight(1)
        divider.setAttribute(Qt.WA_StyledBackground, True)
        self.add_button = QPushButton(add_text, self.card)
        self.add_button.setObjectName("FolderCardAdd")
        self.add_button.setIcon(QIcon(render_icon("plus", theme.TEXT, 18)))
        self.add_button.setIconSize(QSize(18, 18))
        self.add_button.setCursor(Qt.PointingHandCursor)
        self.add_button.clicked.connect(self.addRequested)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(1, 1, 1, 1)
        card_layout.setSpacing(0)
        card_layout.addWidget(self.list_widget, 1)
        card_layout.addWidget(divider)
        card_layout.addWidget(self.add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self.card, 1)

    def set_paths(self, folder_paths):
        for i in range(self.list_widget.count()):
            widget = self.list_widget.itemWidget(self.list_widget.item(i))
            if widget is not None:
                widget.setParent(None)
        self.list_widget.clear()
        for path in folder_paths:
            row = _PathRow(path)
            row.removeRequested.connect(self.removeRequested)
            item = QListWidgetItem()
            item.setSizeHint(QSize(1, row.sizeHint().height()))
            self.list_widget.addItem(item)
            self.list_widget.setItemWidget(item, row)

    def row(self, index):
        return self.list_widget.itemWidget(self.list_widget.item(index))

    def paths(self):
        return [self.row(i).path for i in range(self.list_widget.count())]


COLUMN_W = 640


def _centered_row(widget):
    widget.setMaximumWidth(COLUMN_W)
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addStretch(1)
    row.addWidget(widget, 100)
    row.addStretch(1)
    return row


def _column_page(*items, fill=False):
    column = QWidget()
    column_layout = QVBoxLayout(column)
    column_layout.setContentsMargins(0, 0, 0, 0)
    column_layout.setSpacing(10)
    for index, item in enumerate(items):
        if isinstance(item, int):
            column_layout.addSpacing(item)
        else:
            last = index == len(items) - 1
            column_layout.addWidget(item, 1 if (fill and last) else 0)
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(32, 32 if fill else 24, 32, 24)
    if not fill:
        layout.addStretch(1)
    layout.addLayout(_centered_row(column), 1 if fill else 0)
    if not fill:
        layout.addStretch(1)
    return page


def _page(title, subtext, body, fill=False):
    heading = QLabel(title)
    heading.setObjectName("WizardTitle")
    if not subtext:
        return _column_page(heading, 28, body, fill=fill)
    sub = QLabel(subtext)
    sub.setObjectName("WizardSubtext")
    sub.setWordWrap(True)
    return _column_page(heading, sub, 28, body, fill=fill)


class SetupWizard(QWidget):
    createRequested = Signal(dict)
    cancelRequested = Signal()
    scanCancelRequested = Signal()
    scanEnded = Signal(object)
    scanFailed = Signal(str)
    importRequested = Signal(str)
    finishRequested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SetupWizard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._can_cancel = False
        self._includes = []
        self._excludes = []
        self._build()
        self.begin(can_cancel=False)

    def _build(self):
        self.welcome_page = WelcomePage()

        self.form = LibraryInfoForm(relaxed=True)
        self.form.validityChanged.connect(self._refresh_footer)
        self.form.setMaximumWidth(560)
        library_body = QWidget()
        library_row = QHBoxLayout(library_body)
        library_row.setContentsMargins(0, 0, 0, 0)
        library_row.addWidget(self.form)
        library_row.addStretch(1)
        library_page = _page(
            "Create a library",
            "A library is a collection of music files. waon supports "
            "multiple libraries, so give yours a name.", library_body)

        self.include_list = _PathList("Folders to include", "Add folder")
        self.include_list.addRequested.connect(self._on_add_include)
        self.include_list.removeRequested.connect(self._on_remove_include)
        self.exclude_list = _PathList("Folders to exclude", "Exclude a subfolder")
        self.exclude_list.addRequested.connect(self._on_add_exclude)
        self.exclude_list.removeRequested.connect(self._on_remove_exclude)
        self.folders_error = QLabel("")
        self.folders_error.setObjectName("DialogError")
        self.folders_error.setWordWrap(True)
        cards = QHBoxLayout()
        cards.setContentsMargins(0, 0, 0, 0)
        cards.setSpacing(16)
        cards.addWidget(self.include_list, 1)
        cards.addWidget(self.exclude_list, 1)
        folders_body = QWidget()
        folders_layout = QVBoxLayout(folders_body)
        folders_layout.setContentsMargins(0, 0, 0, 0)
        folders_layout.setSpacing(10)
        folders_layout.addLayout(cards, 1)
        folders_layout.addWidget(self.folders_error)
        folders_page = _page(
            "Where is your music?", None, folders_body, fill=True)

        self.scan_title = QLabel("")
        self.scan_title.setObjectName("WizardTitle")
        self.scan_detail = QLabel("")
        self.scan_detail.setObjectName("WizardSubtext")
        self.scan_dir = ElidedLabel("")
        self.scan_dir.setObjectName("WizardSubtext")
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ScanBar")
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.cancel_scan_button = QPushButton("Cancel scan")
        self.cancel_scan_button.setObjectName("WizardSecondary")
        self.cancel_scan_button.clicked.connect(self._on_cancel_scan)
        cancel_row = QWidget()
        cancel_layout = QHBoxLayout(cancel_row)
        cancel_layout.setContentsMargins(0, 0, 0, 0)
        cancel_layout.addWidget(self.cancel_scan_button)
        cancel_layout.addStretch(1)
        scanning_page = _column_page(self.scan_title, self.scan_detail,
                                     self.scan_dir, 8, self.progress_bar, 8,
                                     cancel_row)

        self.import_summary = QLabel("")
        self.import_summary.setObjectName("WizardSubtext")
        question = QLabel("Do you want to restore play history and playlists "
                          "from a previous backup?")
        question.setWordWrap(True)
        self.import_button = QPushButton("Restore")
        self.import_button.setObjectName("WizardSecondary")
        self.import_button.clicked.connect(self._on_import_clicked)
        self.import_status = QLabel("")
        self.import_status.setWordWrap(True)
        self.import_error = QLabel("")
        self.import_error.setObjectName("DialogError")
        self.import_error.setWordWrap(True)
        import_body = QWidget()
        import_layout = QVBoxLayout(import_body)
        import_layout.setContentsMargins(0, 0, 0, 0)
        import_layout.setSpacing(10)
        import_layout.addWidget(question)
        import_layout.addWidget(self.import_button, alignment=Qt.AlignLeft)
        import_layout.addWidget(self.import_status)
        import_layout.addWidget(self.import_error)
        import_heading = QLabel("Your library has been created")
        import_heading.setObjectName("WizardTitle")
        import_page = _column_page(import_heading, self.import_summary, 28,
                                   import_body)

        self.stack = QStackedWidget()
        for page in (self.welcome_page, library_page, folders_page,
                     scanning_page, import_page):
            self.stack.addWidget(page)

        self.back_button = QPushButton()
        self.back_button.setObjectName("WizardBackButton")
        self.back_button.setToolTip("Back")
        self.back_button.setFixedSize(NEXT_SIZE, NEXT_SIZE)
        self.back_button.setIcon(QIcon(render_icon(
            "caret-left-bold", theme.BRAND, NEXT_ICON)))
        self.back_button.setIconSize(QSize(NEXT_ICON, NEXT_ICON))
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.clicked.connect(self._on_back)
        self.footer = QWidget()
        self.footer.setFixedHeight(FOOTER_H)
        footer_outer = QVBoxLayout(self.footer)
        footer_outer.setContentsMargins(0, 0, 0, 0)
        footer_outer.setSpacing(0)
        divider = QWidget()
        divider.setObjectName("WizardDivider")
        divider.setFixedHeight(1)
        divider.setAttribute(Qt.WA_StyledBackground, True)
        footer_outer.addWidget(divider)
        buttons = QWidget()
        footer_row = QHBoxLayout(buttons)
        footer_row.setContentsMargins(0, 0, 0, 0)
        footer_row.setSpacing(10)
        footer_row.addWidget(self.back_button)
        footer_row.addStretch(1)
        centered = _centered_row(buttons)
        centered.setContentsMargins(32, 0, 32, 0)
        footer_outer.addLayout(centered)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.stack, 1)
        layout.addWidget(self.footer)

        self.dots = StepDots(STEP_COUNT, self)
        self.next_button = QPushButton(self)
        self.next_button.setObjectName("WizardNextButton")
        self.next_button.setFixedSize(NEXT_SIZE, NEXT_SIZE)
        self.next_button.setIcon(QIcon(render_icon(
            "caret-right-bold", "#FFFFFF", NEXT_ICON)))
        self.next_button.setIconSize(QSize(NEXT_ICON, NEXT_ICON))
        self.next_button.setCursor(Qt.PointingHandCursor)
        self.next_button.clicked.connect(self._on_next)
        self.cancel_button = IconButton("close", "Cancel", icon_size=18,
                                        diameter=36, pill_hover=False, parent=self)
        self.cancel_button.clicked.connect(self.cancelRequested)

    def begin(self, can_cancel):
        self._can_cancel = can_cancel
        self.form.set_values("")
        self._includes, self._excludes = [], []
        self._reload_folders()
        self.folders_error.setText("")
        self._go(PAGE_LIBRARY if can_cancel else PAGE_WELCOME)

    def resume(self, values, includes, excludes, can_cancel):
        self._can_cancel = can_cancel
        self.form.set_values(values["name"], values["color"], values["icon"])
        self._includes, self._excludes = list(includes), list(excludes)
        self._reload_folders()
        self.folders_error.setText("")

    def page(self):
        return self.stack.currentIndex()

    def show_folders(self, error=""):
        self.folders_error.setText(error)
        self._go(PAGE_FOLDERS)

    def show_import(self, track_count):
        self.import_summary.setText(
            "1 track was found." if track_count == 1
            else "{:,} tracks were found.".format(track_count))
        self.import_status.setText("")
        self.import_error.setText("")
        self.import_button.setEnabled(True)
        self._go(PAGE_IMPORT)

    def show_import_error(self, message):
        self.import_error.setText(message)

    def mark_imported(self, summary):
        self.import_status.setText(summary)
        self.import_error.setText("")
        self.import_button.setEnabled(False)

    def start(self, library_name):
        self.scan_title.setText("Building your library")
        self.scan_detail.setText("0 files seen • 0 tracks found")
        self.scan_dir.setText("")
        self.cancel_scan_button.setEnabled(True)
        self._go(PAGE_SCANNING)

    def set_progress(self, progress):
        self.scan_detail.setText(u"{:,} files seen • {:,} tracks found".format(
            progress.files_seen, progress.tracks_found))
        self.scan_dir.setText(progress.current_dir)

    def show_result(self, result):
        self.scanEnded.emit(result)

    def show_failure(self, message):
        self.scanFailed.emit(message)

    def pick_folder(self, start=""):
        return QFileDialog.getExistingDirectory(self, "Choose a folder", start)

    def pick_import_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Restore from backup", "", FILE_FILTER)
        return path

    def _go(self, page):
        self.stack.setCurrentIndex(page)
        self._refresh_footer()
        self.dots.set_current(_STEP_OF_PAGE[page])
        self._place_overlays()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_overlays()

    def _place_overlays(self):
        center_y = self.height() - FOOTER_H // 2
        self.dots.move((self.width() - self.dots.width()) // 2,
                       center_y - self.dots.height() // 2)
        column = min(COLUMN_W, self.width() - 64)
        right = (self.width() + column) // 2
        self.next_button.move(right - NEXT_SIZE, center_y - NEXT_SIZE // 2)
        self.cancel_button.move(right - self.cancel_button.width(), 16)
        self.cancel_button.raise_()
        self.dots.raise_()
        self.next_button.raise_()

    def _refresh_footer(self, *_):
        page = self.stack.currentIndex()
        self.footer.setVisible(page in (PAGE_LIBRARY, PAGE_FOLDERS, PAGE_IMPORT))
        self.back_button.setVisible(
            page == PAGE_FOLDERS or (page == PAGE_LIBRARY and not self._can_cancel))
        self.cancel_button.setVisible(
            self._can_cancel and page in (PAGE_LIBRARY, PAGE_FOLDERS))
        self.next_button.setVisible(page != PAGE_SCANNING)
        self.next_button.setToolTip(_NEXT_TIP.get(page, ""))
        if page == PAGE_LIBRARY:
            self.next_button.setEnabled(self.form.is_valid())
        elif page == PAGE_FOLDERS:
            self.next_button.setEnabled(bool(self._includes))
        else:
            self.next_button.setEnabled(True)

    def _on_back(self):
        if self.page() == PAGE_FOLDERS:
            self._go(PAGE_LIBRARY)
        elif self.page() == PAGE_LIBRARY:
            self._go(PAGE_WELCOME)

    def _on_next(self):
        page = self.page()
        if page == PAGE_WELCOME:
            self._go(PAGE_LIBRARY)
        elif page == PAGE_LIBRARY:
            self._go(PAGE_FOLDERS)
        elif page == PAGE_FOLDERS:
            values = self.form.values()
            values["roots"] = list(self._includes)
            values["exclusions"] = list(self._excludes)
            self.folders_error.setText("")
            self.createRequested.emit(values)
        elif page == PAGE_IMPORT:
            self.finishRequested.emit()

    def _reload_folders(self):
        self.include_list.set_paths(self._includes)
        self.exclude_list.set_paths(self._excludes)
        self._refresh_footer()

    def _refuse(self, message):
        log.info("setup wizard refused a folder: %s", message)
        self.folders_error.setText(message)

    def _on_add_include(self):
        path = self.pick_folder()
        if not path:
            return
        path = os.path.normpath(path)
        conflict = paths.nested_conflict(path, self._includes)
        if conflict is not None:
            self._refuse("{} overlaps {}, which is already included.".format(
                path, conflict))
            return
        self.folders_error.setText("")
        self._includes.append(path)
        self._reload_folders()

    def _on_remove_include(self, path):
        self._includes = [p for p in self._includes if p != path]
        self._excludes = [e for e in self._excludes if paths.to_rel(path, e) is None]
        self.folders_error.setText("")
        self._reload_folders()

    def _on_add_exclude(self):
        path = self.pick_folder(self._includes[0] if self._includes else "")
        if not path:
            return
        path = os.path.normpath(path)
        if any(_same(root, path) for root in self._includes):
            self._refuse(u"That's a whole included folder — remove it instead "
                         "of excluding it.")
            return
        if not any(paths.to_rel(root, path) is not None for root in self._includes):
            self._refuse("{} is not inside any included folder.".format(path))
            return
        if any(_same(existing, path) for existing in self._excludes):
            self._refuse("That folder is already excluded.")
            return
        self.folders_error.setText("")
        self._excludes.append(path)
        self._reload_folders()

    def _on_remove_exclude(self, path):
        self._excludes = [e for e in self._excludes if e != path]
        self._reload_folders()

    def _on_cancel_scan(self):
        self.cancel_scan_button.setEnabled(False)
        self.scanCancelRequested.emit()

    def _on_import_clicked(self):
        path = self.pick_import_file()
        if path:
            self.import_error.setText("")
            self.importRequested.emit(path)
