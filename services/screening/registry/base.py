"""Storage-independent contract for immutable rule versions."""

from abc import ABC, abstractmethod
from pathlib import Path


class BaseRegistry(ABC):
    @abstractmethod
    def publish(self, path: str | Path) -> None:
        """Validate and atomically publish rules, preserving existing versions on failure.

        A changed definition requires a new version. Republishing an identical
        version must not change the current version of the scale.
        """

    @abstractmethod
    def get(self, scale: str, version: str | None = None) -> dict:
        """Return an independent copy of the exact or current version, or raise KeyError."""
