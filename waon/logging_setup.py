
import faulthandler
import logging
import logging.handlers
import os
import sys
import threading

LOG_FILENAME = "waon.log"
CRASH_FILENAME = "waon-crash.log"

_MAX_BYTES = 1024 * 1024
_BACKUPS = 3
_FORMAT = "%(asctime)s %(levelname)-8s %(name)s: %(message)s"

_crash_file = None
_configured = False


def log_dir(directory=None):
    if directory is not None:
        return os.path.abspath(directory)
    from waon.library import locations
    return os.path.join(locations.app_data_dir(), "logs")


def log_path(directory=None):
    return os.path.join(log_dir(directory), LOG_FILENAME)


def setup_logging(directory=None, level=logging.DEBUG, to_stderr=True,
                  install_qt_handler=True):
    global _crash_file, _configured

    target = log_dir(directory)
    os.makedirs(target, exist_ok=True)
    path = os.path.join(target, LOG_FILENAME)

    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT)
    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    if to_stderr and sys.stderr is not None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)

    _install_excepthooks()
    _enable_faulthandler(target)
    if install_qt_handler:
        _install_qt_handler()

    _configured = True
    logging.getLogger(__name__).debug("logging configured -> %s", path)
    return path


def _install_excepthooks():
    logger = logging.getLogger("waon.crash")

    def handle(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logger.critical("unhandled exception",
                        exc_info=(exc_type, exc_value, exc_tb))

    sys.excepthook = handle

    def handle_thread(args):
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical("unhandled exception in thread %s",
                        getattr(args.thread, "name", "?"),
                        exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    threading.excepthook = handle_thread


def _enable_faulthandler(directory):
    global _crash_file
    try:
        _crash_file = open(os.path.join(directory, CRASH_FILENAME), "a",
                           encoding="utf-8")
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        logging.getLogger(__name__).exception("could not enable faulthandler")


def _install_qt_handler():
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except ImportError:
        return

    logger = logging.getLogger("qt")
    levels = {
        QtMsgType.QtDebugMsg: logging.DEBUG,
        QtMsgType.QtInfoMsg: logging.INFO,
        QtMsgType.QtWarningMsg: logging.WARNING,
        QtMsgType.QtCriticalMsg: logging.ERROR,
        QtMsgType.QtFatalMsg: logging.CRITICAL,
    }

    def handle(mode, context, message):
        logger.log(levels.get(mode, logging.INFO), "%s", message)

    qInstallMessageHandler(handle)
