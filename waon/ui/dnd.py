
import os


def local_paths_from_mime(mime):
    if not mime.hasUrls():
        return []
    paths = []
    for url in mime.urls():
        local = url.toLocalFile()
        if local:
            paths.append(os.path.normpath(local))
    return paths
