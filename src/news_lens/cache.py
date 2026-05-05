"""On-disk JSON cache for expensive pipeline steps.

The cache key incorporates both the input identifier and a short hash of the
prompt used, so prompt edits during development automatically invalidate
prior entries instead of returning stale results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional


class Cache:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _key(*parts: str) -> str:
        joined = "::".join(parts)
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]

    def _path(self, namespace: str, key: str) -> Path:
        return self.root / namespace / f"{key}.json"

    def get(self, namespace: str, *parts: str) -> Optional[Any]:
        path = self._path(namespace, self._key(*parts))
        if not path.exists():
            return None
        return json.loads(path.read_text())

    def set(self, namespace: str, value: Any, *parts: str) -> None:
        path = self._path(namespace, self._key(*parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, default=str))
