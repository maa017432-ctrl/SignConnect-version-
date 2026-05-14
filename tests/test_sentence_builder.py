"""Tests for SentenceBuilder commit/cooldown logic."""

from __future__ import annotations

from core.prediction_smoother import SentenceBuilder


class TestSentenceBuilder:
    def test_commit_after_stable_frames(self) -> None:
        builder = SentenceBuilder(stable_frames=3, cooldown_frames=0, max_words=10)
        for _ in range(2):
            assert builder.update("hello") is False
        assert builder.update("hello") is True
        assert builder.sentence == "hello"

    def test_cooldown_blocks_immediate_repeat(self) -> None:
        builder = SentenceBuilder(stable_frames=2, cooldown_frames=5, max_words=10)
        builder.update("hello")
        builder.update("hello")
        for _ in range(5):
            assert builder.update("hello") is False
        assert builder.is_cooling_down is False

    def test_different_label_after_commit(self) -> None:
        builder = SentenceBuilder(stable_frames=2, cooldown_frames=0, max_words=10)
        builder.update("hello")
        builder.update("hello")
        builder.update("world")
        assert builder.update("world") is True
        assert builder.sentence == "hello world"

    def test_same_label_not_repeated(self) -> None:
        builder = SentenceBuilder(stable_frames=2, cooldown_frames=0, max_words=10)
        builder.update("hello")
        builder.update("hello")
        for _ in range(5):
            result = builder.update("hello")
        assert result is False
        assert builder.sentence == "hello"

    def test_max_words_cap(self) -> None:
        builder = SentenceBuilder(stable_frames=1, cooldown_frames=0, max_words=2)
        builder.update("a")
        builder.update("b")
        committed = builder.update("c")
        assert committed is False
        assert len(builder.words) == 2

    def test_delete_last_word(self) -> None:
        builder = SentenceBuilder(stable_frames=1, cooldown_frames=0, max_words=10)
        builder.update("a")
        builder.update("b")
        builder.update("c")
        deleted = builder.delete_last_word()
        assert deleted == "c"
        assert builder.sentence == "a b"

    def test_delete_from_empty(self) -> None:
        builder = SentenceBuilder(stable_frames=1, cooldown_frames=0, max_words=10)
        assert builder.delete_last_word() is None

    def test_clear_resets_everything(self) -> None:
        builder = SentenceBuilder(stable_frames=1, cooldown_frames=0, max_words=10)
        builder.update("hello")
        builder.clear()
        assert builder.sentence == ""
        assert builder.words == []
        assert builder.current_label is None
        assert builder.current_run == 0
        assert builder.is_cooling_down is False

    def test_none_label_resets_run(self) -> None:
        builder = SentenceBuilder(stable_frames=3, cooldown_frames=0, max_words=10)
        builder.update("hello")
        builder.update("hello")
        builder.update(None)
        assert builder.current_run == 0
        assert builder.current_label is None
