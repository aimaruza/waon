
import os
import sys

import waon

ENV_OVERRIDE = "WAON_DATA_DIR"
LIBRARY_SUFFIX = ".mxlib"


def _app_root():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    try:
        if __compiled__.standalone and not __compiled__.onefile:
            return os.path.dirname(sys.executable)
        return __compiled__.containing_dir
    except NameError:
        pass
    return os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))


def app_data_dir():
    override = os.environ.get(ENV_OVERRIDE)
    if override:
        return os.path.abspath(override)
    return os.path.join(_app_root(), "data")


def data_dir_problem():
    directory = app_data_dir()
    probe = os.path.join(directory, ".write-test")
    try:
        os.makedirs(directory, exist_ok=True)
        with open(probe, "w"):
            pass
        os.remove(probe)
    except OSError as exc:
        return ("{name} keeps its data in a folder beside the app, but it "
                "can't write to:\n{dir}\n\n({why})\n\nMove the {name} folder "
                "somewhere you can write to, such as your Documents folder or "
                "a USB drive, and start it again.".format(
                    name=waon.APP_NAME, dir=directory, why=exc.strerror or exc))
    return None


def libraries_dir():
    return os.path.join(app_data_dir(), "libraries")


def app_db_path():
    return os.path.join(app_data_dir(), "app.db")


def library_path(library_id):
    return os.path.join(libraries_dir(), library_id + LIBRARY_SUFFIX)


def artwork_dir():
    return os.path.join(app_data_dir(), "artwork")


def art_path(album_id):
    return os.path.join(artwork_dir(), album_id + ".art")


def ensure_dirs():
    os.makedirs(app_data_dir(), exist_ok=True)
    os.makedirs(libraries_dir(), exist_ok=True)
    os.makedirs(artwork_dir(), exist_ok=True)
