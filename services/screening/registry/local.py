"""In-process storage for immutable rule versions."""

import json
from copy import deepcopy
from pathlib import Path
from threading import Lock

from ..rules import RuleConfigError, load_rules
from .base import BaseRegistry


class LocalRegistry(BaseRegistry):
    """Keep exact versions and the current version of each scale in memory."""

    def __init__(self):
        self._versions = {}
        self._current = {}
        self._lock = Lock()

    def publish(self, path: str | Path) -> None:
        rules = load_rules(path)
        scale, version = rules["id"], rules["weights_version"]
        with self._lock:
            key = (scale, version)
            if key not in self._versions:
                self._versions[key] = rules
                self._current[scale] = version
                return
            if json.dumps(self._versions[key], sort_keys=True) == json.dumps(rules, sort_keys=True):
                return
            raise RuleConfigError(
                version, "$.weights_version", f"rules for {scale!r} require a new version",
            )

    def get(self, scale: str, version: str | None = None) -> dict:
        with self._lock:
            selected = self._current[scale] if version is None else version
            return deepcopy(self._versions[scale, selected])
