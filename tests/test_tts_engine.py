"""Unit tests for core.tts_engine.TTSEngine."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def audio_dir(tmp_path: Path) -> Path:
    return tmp_path / "audio"


def _make_engine(audio_dir: Path, **kwargs):
    """Create a TTSEngine with gTTS mocked out at module level."""
    from core.tts_engine import TTSEngine

    with patch("core.tts_engine.gTTS") as mock_cls:
        mock_cls.return_value = MagicMock()
        engine = TTSEngine(audio_dir=str(audio_dir), **kwargs)

    # Keep the mock reachable for post-construction assertions
    engine.__mock_gtts__ = mock_cls  # type: ignore[attr-defined]
    return engine, mock_cls


class TestInit:
    def test_is_available_with_gtts(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        assert engine.is_available is True
        assert engine._backend == "gtts"

    def test_unavailable_when_both_backends_missing(self, audio_dir: Path) -> None:
        from core.tts_engine import TTSEngine

        with (
            patch("core.tts_engine.gTTS", None),
            patch("core.tts_engine.pyttsx3", None),
        ):
            engine = TTSEngine(audio_dir=str(audio_dir))

        assert engine.is_available is False
        assert engine._backend is None

    def test_audio_directory_created(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "audio"
        assert not nested.exists()
        engine, _ = _make_engine(nested)
        assert nested.exists()


class TestSynthesize:
    def test_returns_mp3_filename(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            result = engine.synthesize("hello")
        assert result is not None
        assert result.endswith(".mp3")

    def test_passes_lang_to_gtts(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            engine.synthesize("bonjour", lang="fr")
        mock_cls.assert_called_once_with(text="bonjour", lang="fr")

    def test_defaults_lang_to_en(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            engine.synthesize("hello")
        mock_cls.assert_called_once_with(text="hello", lang="en")

    def test_empty_text_raises_value_error(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with pytest.raises(ValueError, match="empty"):
            engine.synthesize("")

    def test_whitespace_only_raises_value_error(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with pytest.raises(ValueError):
            engine.synthesize("   ")

    def test_unavailable_engine_returns_none(self, audio_dir: Path) -> None:
        from core.tts_engine import TTSEngine

        with (
            patch("core.tts_engine.gTTS", None),
            patch("core.tts_engine.pyttsx3", None),
        ):
            engine = TTSEngine(audio_dir=str(audio_dir))

        result = engine.synthesize("hello")
        assert result is None


class TestCache:
    def test_same_text_same_lang_returns_cached_filename(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            r1 = engine.synthesize("hello")
            r2 = engine.synthesize("hello")
        # gTTS should only be called once (second call hits cache)
        assert r1 == r2
        assert mock_cls.call_count == 1

    def test_different_lang_produces_different_filename(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            r_en = engine.synthesize("hello", lang="en")
            r_fr = engine.synthesize("hello", lang="fr")
        assert r_en != r_fr
        assert mock_cls.call_count == 2

    def test_expired_cache_triggers_new_synthesis(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir, cache_ttl_seconds=0)
        with patch("core.tts_engine.gTTS") as mock_cls, \
             patch("core.tts_engine.time") as mock_time:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            mock_time.time.side_effect = [0.0, 1.0, 2.0, 3.0]
            engine.synthesize("hello")
            engine.synthesize("hello")  # cache TTL=0, should re-synthesise
        assert mock_cls.call_count == 2


class TestCachePruning:
    def test_prune_cache_removes_expired_entries(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir, cache_ttl_seconds=60)
        now = 1000.0
        engine._cache["old::en"] = (now - 61, "old.mp3")
        engine._cache["new::en"] = (now - 10, "new.mp3")

        engine._prune_cache(now)

        assert "old::en" not in engine._cache
        assert "new::en" in engine._cache

    def test_prune_cache_keeps_fresh_entries(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir, cache_ttl_seconds=60)
        now = 1000.0
        engine._cache["a::en"] = (now - 5, "a.mp3")
        engine._cache["b::en"] = (now - 30, "b.mp3")

        engine._prune_cache(now)

        assert "a::en" in engine._cache
        assert "b::en" in engine._cache

    def test_periodic_cleanup_triggered(self, audio_dir: Path) -> None:
        """After _CLEANUP_INTERVAL syntheses the cache prune is called."""
        from core.tts_engine import TTSEngine

        engine, _ = _make_engine(audio_dir)
        engine._synthesize_count = TTSEngine._CLEANUP_INTERVAL - 1

        with patch("core.tts_engine.gTTS") as mock_cls, \
             patch.object(engine, "_prune_cache") as mock_prune, \
             patch.object(engine, "_cleanup_stale_files") as mock_cleanup:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            engine.synthesize("trigger cleanup")

        mock_prune.assert_called_once()
        mock_cleanup.assert_called_once()

    def test_synthesize_count_increments(self, audio_dir: Path) -> None:
        engine, _ = _make_engine(audio_dir)
        initial = engine._synthesize_count
        with patch("core.tts_engine.gTTS") as mock_cls:
            mock_cls.return_value = MagicMock()
            engine._backend = "gtts"
            engine.synthesize("hello world")
        assert engine._synthesize_count == initial + 1


class TestPyttsx3ResourceRelease:
    def test_pyttsx3_engine_stop_called(self, audio_dir: Path) -> None:
        """engine.stop() must be called after runAndWait() to free native resources."""
        from core.tts_engine import TTSEngine

        with (
            patch("core.tts_engine.gTTS", None),
        ):
            with patch("core.tts_engine.pyttsx3") as mock_pyttsx3:
                fake_engine = MagicMock()
                mock_pyttsx3.init.return_value = fake_engine
                engine = TTSEngine(audio_dir=str(audio_dir))

        engine._backend = "pyttsx3"
        with patch("core.tts_engine.pyttsx3") as mock_pyttsx3:
            fake_engine = MagicMock()
            mock_pyttsx3.init.return_value = fake_engine
            engine.synthesize("test stop")

        fake_engine.stop.assert_called_once()

    def test_pyttsx3_engine_stop_called_on_runandwait_failure(
        self, audio_dir: Path
    ) -> None:
        """engine.stop() must be called even when runAndWait() raises."""
        from core.tts_engine import TTSEngine

        with (
            patch("core.tts_engine.gTTS", None),
        ):
            with patch("core.tts_engine.pyttsx3") as mock_pyttsx3:
                fake_engine = MagicMock()
                mock_pyttsx3.init.return_value = fake_engine
                engine = TTSEngine(audio_dir=str(audio_dir))

        engine._backend = "pyttsx3"
        with patch("core.tts_engine.pyttsx3") as mock_pyttsx3:
            fake_engine = MagicMock()
            fake_engine.runAndWait.side_effect = RuntimeError("boom")
            mock_pyttsx3.init.return_value = fake_engine
            result = engine.synthesize("fails gracefully")

        fake_engine.stop.assert_called_once()
        assert result is None
