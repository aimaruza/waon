
import os


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _parts(abs_path):
    drive, rest = os.path.splitdrive(abs_path)
    names = [name for name in rest.replace("\\", "/").split("/") if name]
    return [drive] + names if drive else names


def to_rel(root_path, abs_path):
    root_parts = _parts(os.path.abspath(root_path))
    target_parts = _parts(os.path.abspath(abs_path))
    if len(target_parts) <= len(root_parts):
        return None
    for want, got in zip(root_parts, target_parts):
        if os.path.normcase(want) != os.path.normcase(got):
            return None
    return "/".join(target_parts[len(root_parts):])


def to_abs(root_path, rel_path):
    return os.path.join(root_path, *rel_path.split("/"))


def norm_key(rel_path):
    return rel_path.lower()


def is_nested(path_a, path_b):
    a = _norm(path_a)
    b = _norm(path_b)
    if a == b:
        return True
    return (a.startswith(b.rstrip(os.sep) + os.sep)
            or b.startswith(a.rstrip(os.sep) + os.sep))


def nested_conflict(new_path, existing_paths):
    for existing in existing_paths:
        if is_nested(new_path, existing):
            return existing
    return None
