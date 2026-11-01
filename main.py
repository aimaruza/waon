

import logging
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

import waon
from waon.library import locations
from waon.logging_setup import setup_logging
from waon.player import engine as player_engine
from waon.ui.theme import build_stylesheet
from waon.ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("waon")
    problem = locations.data_dir_problem()
    if problem is not None:
        QMessageBox.critical(None, "{} can't start".format(waon.APP_NAME), problem)
        return 1
    log_file = setup_logging()

    log = logging.getLogger(__name__)
    log.info("waon starting (log: %s)", log_file)

    app.setStyleSheet(build_stylesheet())
    window = MainWindow()
    window.show()
    status = app.exec()
    player_engine.shutdown()
    log.info("waon exited with status %s", status)
    return status


if __name__ == "__main__":
    sys.exit(main())
