
try:
    import mutagen
except ImportError:
    mutagen = None


def extract_cover(path):
    if not path or mutagen is None:
        return None
    try:
        mf = mutagen.File(path)
    except Exception:
        return None
    if mf is None:
        return None

    pics = getattr(mf, "pictures", None)
    if pics:
        try:
            return bytes(pics[0].data)
        except Exception:
            pass

    tags = getattr(mf, "tags", None)
    if tags is None:
        return None

    getall = getattr(tags, "getall", None)
    if callable(getall):
        try:
            frames = getall("APIC")
            if frames:
                return bytes(frames[0].data)
        except Exception:
            pass

    try:
        covr = tags.get("covr")
        if covr:
            return bytes(covr[0])
    except Exception:
        pass

    try:
        for key, value in tags.items():
            if str(key).startswith("APIC") and getattr(value, "data", None):
                return bytes(value.data)
    except Exception:
        pass

    return None
