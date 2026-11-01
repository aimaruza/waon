
from PySide6.QtCore import QThread, Signal

from waon.library import db
from waon.library.library_repo import LibraryRepo
from waon.library.scan_runner import ScanRunner


class ScanWorker(QThread):

    progress = Signal(object)
    finished_ok = Signal(object)
    failed = Signal(str)

    def __init__(self, db_path, root_ids=None, parent=None):
        super().__init__(parent)
        self._db_path = db_path
        self._root_ids = root_ids
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        conn = None
        try:
            conn = db.open_library_db(self._db_path)
            runner = ScanRunner(LibraryRepo(conn),
                                on_progress=self.progress.emit,
                                should_cancel=lambda: self._cancelled)
            result = runner.scan(root_ids=self._root_ids)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        finally:
            if conn is not None:
                conn.close()
        self.finished_ok.emit(result)
