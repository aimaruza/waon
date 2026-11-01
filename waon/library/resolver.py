
import os

from waon.library import paths


class Resolver:

    def __init__(self, roots):
        self._roots = list(roots)
        self._offline = set()

    @property
    def offline_ids(self):
        return set(self._offline)

    def mark_offline(self, root_id):
        self._offline.add(root_id)

    def resolve(self, rel_path, root_hint_id=None):
        for root in self._ordered(root_hint_id):
            if root.id in self._offline:
                continue
            if not os.path.isdir(root.path):
                self._offline.add(root.id)
                continue
            candidate = paths.to_abs(root.path, rel_path)
            if os.path.exists(candidate):
                return candidate, root.id
        return None, None

    def _ordered(self, root_hint_id):
        if root_hint_id is None:
            return self._roots
        hinted = [r for r in self._roots if r.id == root_hint_id]
        return hinted + [r for r in self._roots if r.id != root_hint_id]


def availability_pass(repo, resolver=None):
    if resolver is None:
        resolver = Resolver(repo.roots())

    found_ids = []
    missing_ids = []
    rows = repo.all_tracks()
    for row in rows:
        path, root_id = resolver.resolve(row.rel_path, row.root_hint_id)
        if path is None:
            missing_ids.append(row.id)
        else:
            found_ids.append((row.id, root_id))

    repo.touch_tracks(found_ids)
    repo.mark_unavailable(missing_ids)
    return len(found_ids), len(missing_ids)
