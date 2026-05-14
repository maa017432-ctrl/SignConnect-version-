"""Unit tests for core.translator.Translator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.translator import Translator


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def label_map(tmp_path: Path) -> Path:
    """Write a minimal label_map.json and return its path."""
    data = {"0": "A", "1": "B", "2": "C", "10": "K"}
    p = tmp_path / "label_map.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


# ── get_label ─────────────────────────────────────────────────────────────────

class TestGetLabel:
    def test_valid_index_returns_label(self, label_map: Path) -> None:
        t = Translator(str(label_map))
        assert t.get_label(0) == "A"
        assert t.get_label(1) == "B"
        assert t.get_label(2) == "C"

    def test_non_consecutive_key(self, label_map: Path) -> None:
        t = Translator(str(label_map))
        assert t.get_label(10) == "K"

    def test_unknown_index_returns_unknown(self, label_map: Path) -> None:
        t = Translator(str(label_map))
        assert t.get_label(99) == "Unknown"
        assert t.get_label(-1) == "Unknown"

    def test_empty_label_map_always_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.json"
        p.write_text("{}", encoding="utf-8")
        t = Translator(str(p))
        assert t.get_label(0) == "Unknown"


# ── get_all_labels ────────────────────────────────────────────────────────────

class TestGetAllLabels:
    def test_returns_labels_in_numeric_key_order(self, label_map: Path) -> None:
        t = Translator(str(label_map))
        labels = t.get_all_labels()
        # Numeric order: 0→A, 1→B, 2→C, 10→K
        assert labels == ["A", "B", "C", "K"]

    def test_empty_map_returns_empty_list(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.json"
        p.write_text("{}", encoding="utf-8")
        t = Translator(str(p))
        assert t.get_all_labels() == []

    def test_reload_refreshes_label_map(self, tmp_path: Path) -> None:
        p = tmp_path / "label_map.json"
        p.write_text(json.dumps({"0": "hello"}), encoding="utf-8")
        t = Translator(str(p))

        p.write_text(json.dumps({"0": "thanks", "1": "yes"}), encoding="utf-8")
        t.reload()

        assert t.get_label(0) == "thanks"
        assert t.get_label(1) == "yes"


# ── Graceful degradation ──────────────────────────────────────────────────────

class TestGracefulDegradation:
    def test_missing_file_yields_empty_map(self, tmp_path: Path) -> None:
        t = Translator(str(tmp_path / "nonexistent.json"))
        assert t.label_map == {}
        assert t.get_label(0) == "Unknown"

    def test_invalid_json_yields_empty_map(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{ this is: not valid json !!!", encoding="utf-8")
        t = Translator(str(p))
        assert t.label_map == {}
        assert t.get_all_labels() == []

    def test_label_map_property_is_dict(self, label_map: Path) -> None:
        t = Translator(str(label_map))
        assert isinstance(t.label_map, dict)
