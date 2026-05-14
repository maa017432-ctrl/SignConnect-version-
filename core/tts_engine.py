"""Text-to-speech generation with online/offline fallbacks."""
# STATUS: graceful-degradation pattern applied — safe for startup

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

try:
    from gtts import gTTS
except ImportError:  # pragma: no cover
    gTTS = None  # type: ignore[assignment,misc]

try:
    import pyttsx3
except ImportError:  # pragma: no cover
    pyttsx3 = None


LOGGER = logging.getLogger(__name__)


class TTSEngine:
    """Generate speech audio files and cache repeated requests."""

    # Run a stale-file sweep every this many synthesis calls.
    _CLEANUP_INTERVAL: int = 50

    def __init__(self, audio_dir: str, cache_ttl_seconds: int = 60) -> None:
        self.audio_dir = Path(audio_dir)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}
        self._available = False
        self._backend: Optional[str] = None
        self._unavailable_warned = False
        self._synthesize_count: int = 0
        self._try_init()
        self._cleanup_stale_files()

    @property
    def is_available(self) -> bool:
        """Return whether at least one TTS backend is available."""
        return self._available

    def _try_init(self) -> None:
        """Try to initialize gTTS first, then pyttsx3 without raising errors."""
        self._available = False
        self._backend = None
        try:
            os.makedirs(self.audio_dir, exist_ok=True)
        except Exception as error:
            LOGGER.warning("Failed to create audio directory: %s", error)
            return

        try:
            if gTTS is None:
                raise RuntimeError("gTTS is not installed")
            _ = gTTS(text="startup check", lang="en")
            self._backend = "gtts"
            self._available = True
            LOGGER.info("TTS engine initialized successfully with gTTS")
            return
        except Exception as error:
            LOGGER.warning("gTTS initialization failed: %s", error)

        try:
            if pyttsx3 is None:
                raise RuntimeError("pyttsx3 is not installed")
            engine = pyttsx3.init()
            engine.stop()
            self._backend = "pyttsx3"
            self._available = True
            LOGGER.info("TTS engine initialized successfully with pyttsx3")
        except Exception as error:
            self._available = False
            self._backend = None
            LOGGER.warning("TTS engine initialization failed: %s", error)

    def synthesize(self, text: str, lang: str = "en") -> Optional[str]:
        """Generate MP3 audio for text in the requested language and return the filename.

        Args:
            text: The text to synthesise. Must be non-empty.
            lang: BCP-47 language code accepted by gTTS (e.g. ``"en"``, ``"ar"``,
                ``"fr"``).  Ignored when the pyttsx3 fallback is active.

        Returns:
            Filename (not full path) of the saved MP3, or ``None`` on failure.

        Raises:
            ValueError: If ``text`` is empty after stripping.
        """
        if not self._available:
            if not self._unavailable_warned:
                LOGGER.warning("TTS engine unavailable; synthesis skipped")
                self._unavailable_warned = True
            return None

        normalized = text.strip()
        if not normalized:
            raise ValueError("Text cannot be empty")

        safe_lang = (lang or "en").strip().lower()

        now = time.time()
        cache_key = f"{normalized.lower()}::{safe_lang}"
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] <= self.cache_ttl_seconds:
            return cached[1]

        file_hash = hashlib.sha256(cache_key.encode()).hexdigest()[:20]
        filename = f"tts_{file_hash}.mp3"
        output_path = self.audio_dir / filename

        if output_path.exists():
            self._cache[cache_key] = (now, filename)
            return filename

        try:
            if self._backend == "gtts":
                if gTTS is None:
                    raise RuntimeError("gTTS is not installed")
                tts = gTTS(text=normalized, lang=safe_lang)
                tts.save(str(output_path))
            elif self._backend == "pyttsx3":
                if pyttsx3 is None:
                    raise RuntimeError("pyttsx3 is not installed")
                engine = pyttsx3.init()
                try:
                    engine.save_to_file(normalized, str(output_path))
                    engine.runAndWait()
                finally:
                    # Always stop the engine to release COM/native resources.
                    engine.stop()
            else:
                return None
        except Exception as error:
            LOGGER.warning("TTS synthesis failed: %s", error)
            return None

        self._cache[cache_key] = (now, filename)

        # Periodically prune stale in-memory cache entries and disk files to
        # prevent unbounded memory and disk growth during long-running sessions.
        self._synthesize_count += 1
        if self._synthesize_count % self._CLEANUP_INTERVAL == 0:
            self._prune_cache(now)
            self._cleanup_stale_files()

        return filename

    def _prune_cache(self, now: float) -> None:
        """Remove in-memory cache entries whose TTL has elapsed."""
        expired = [
            key
            for key, (ts, _) in self._cache.items()
            if now - ts > self.cache_ttl_seconds
        ]
        for key in expired:
            del self._cache[key]
        if expired:
            LOGGER.debug("TTS: pruned %d expired in-memory cache entries", len(expired))

    def _cleanup_stale_files(self) -> None:
        """Remove TTS audio files older than twice the cache TTL."""
        if not self.audio_dir.exists():
            return
        max_age = self.cache_ttl_seconds * 2
        now = time.time()
        for path in self.audio_dir.iterdir():
            if not path.is_file() or not path.name.startswith("tts_"):
                continue
            try:
                if now - path.stat().st_mtime > max_age:
                    path.unlink()
            except OSError:
                pass
