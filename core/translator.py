"""Label translation utilities for SignConnect."""

from __future__ import annotations

import json
import logging
from pathlib import Path


LOGGER = logging.getLogger(__name__)


class Translator:
    """Resolve model output indices to human-readable text labels."""

    def __init__(self, label_map_path: str) -> None:
        self.label_map_path = Path(label_map_path)
        self.label_map: dict[str, str] = {}
        self._load_label_map()

    def _load_label_map(self) -> None:
        """Load index-to-label mapping from JSON file."""
        try:
            with self.label_map_path.open("r", encoding="utf-8") as file_obj:
                self.label_map = json.load(file_obj)
        except FileNotFoundError:
            LOGGER.warning("Label map file missing: %s", self.label_map_path)
            self.label_map = {}
        except json.JSONDecodeError:
            LOGGER.exception("Invalid label map JSON")
            self.label_map = {}

    def reload(self) -> None:
        """Reload label mappings from disk."""
        self._load_label_map()

    def get_label(self, index: int) -> str:
        """Return label text for a prediction index."""
        return self.label_map.get(str(index), "Unknown")

    def get_all_labels(self) -> list[str]:
        """Return all known labels sorted by numeric index."""
        return [
            self.label_map[key]
            for key in sorted(self.label_map.keys(), key=lambda k: int(k))
        ]
