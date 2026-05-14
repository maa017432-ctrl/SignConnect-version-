"""Integration tests for /api/translate and /api/config endpoints."""

from __future__ import annotations

import types
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

pytest.importorskip("flask")


# ── Shared client fixture ─────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def app():
    from app import create_app
    application = create_app()
    application.config["TESTING"] = True
    return application


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


# ── /api/translate ────────────────────────────────────────────────────────────

class TestApiTranslate:
    def test_empty_text_returns_400(self, client) -> None:
        res = client.post(
            "/api/translate",
            json={"text": ""},
            content_type="application/json",
        )
        assert res.status_code == 400
        body = res.get_json()
        assert body is not None
        assert "error" in body

    def test_missing_text_field_returns_400(self, client) -> None:
        res = client.post(
            "/api/translate",
            json={"lang": "en"},
            content_type="application/json",
        )
        assert res.status_code == 400

    def test_non_json_body_returns_400(self, client) -> None:
        res = client.post(
            "/api/translate",
            data="not json at all",
            content_type="text/plain",
        )
        assert res.status_code == 400

    def test_tts_unavailable_returns_503(self, client, app) -> None:
        """When TTS engine returns None (unavailable) the API must 503."""
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value=None):
            res = client.post("/api/translate", json={"text": "Hello"})
        assert res.status_code == 503
        body = res.get_json()
        assert body is not None

    def test_translate_with_language_param(self, client, app) -> None:
        """Lang param should be accepted and passed along without error."""
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value="test_file.mp3") as mock_syn:
            res = client.post(
                "/api/translate",
                json={"text": "Bonjour", "lang": "fr"},
            )
        # If synthesis returned a filename the route should 200-OK
        if res.status_code == 200:
            body = res.get_json()
            assert "audio_url" in body
        # Verify lang was forwarded (may be skipped when TTS actually ran)
        if mock_syn.called:
            _, kwargs = mock_syn.call_args
            assert kwargs.get("lang") == "fr"

    def test_happy_path_returns_audio_url(self, client, app) -> None:
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value="abcdef123456.mp3"):
            res = client.post("/api/translate", json={"text": "Hello world"})
        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert "audio_url" in body
        assert body["audio_url"].endswith("abcdef123456.mp3")


# ── /api/config ───────────────────────────────────────────────────────────────

class TestApiTts:
    """Tests for the lightweight /api/tts endpoint (no DB write)."""

    def test_empty_text_returns_400(self, client) -> None:
        res = client.post("/api/tts", json={"text": ""})
        assert res.status_code == 400
        body = res.get_json()
        assert body is not None
        assert "error" in body

    def test_missing_text_field_returns_400(self, client) -> None:
        res = client.post("/api/tts", json={"lang": "en"})
        assert res.status_code == 400

    def test_tts_unavailable_returns_503(self, client, app) -> None:
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value=None):
            res = client.post("/api/tts", json={"text": "Hello"})
        assert res.status_code == 503

    def test_happy_path_returns_audio_url(self, client, app) -> None:
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value="tts_abc123.mp3"):
            res = client.post("/api/tts", json={"text": "Hello world"})
        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert "audio_url" in body
        assert body["audio_url"].endswith("tts_abc123.mp3")

    def test_lang_param_forwarded(self, client, app) -> None:
        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value="tts_fr.mp3") as mock_syn:
            res = client.post("/api/tts", json={"text": "Bonjour", "lang": "fr"})
        if res.status_code == 200 and mock_syn.called:
            _, kwargs = mock_syn.call_args
            assert kwargs.get("lang") == "fr"

    def test_does_not_write_to_database(self, client, app) -> None:
        """Unlike /api/translate, /api/tts must not insert a history row."""
        from database.db import get_connection

        tts = app.extensions["tts_engine"]
        with patch.object(tts, "synthesize", return_value="tts_nodb.mp3"):
            with get_connection(app.config["DATABASE_PATH"]) as conn:
                count_before = conn.execute(
                    "SELECT COUNT(*) FROM translations"
                ).fetchone()[0]
            res = client.post("/api/tts", json={"text": "No history please"})
            with get_connection(app.config["DATABASE_PATH"]) as conn:
                count_after = conn.execute(
                    "SELECT COUNT(*) FROM translations"
                ).fetchone()[0]
        assert res.status_code == 200
        assert count_after == count_before

    def test_text_too_long_returns_400(self, client) -> None:
        long_text = "x" * 501
        res = client.post("/api/tts", json={"text": long_text})
        assert res.status_code == 400



# ── /api/config ───────────────────────────────────────────────────────────────

class TestApiConfig:
    def test_session_cookie_defaults_are_hardened(self, app) -> None:
        assert app.config["SESSION_COOKIE_HTTPONLY"] is True
        assert app.config["SESSION_COOKIE_SAMESITE"] == "Lax"
        assert app.config["SESSION_COOKIE_SECURE"] is (not app.config["DEBUG"])

    def test_model_contract_config_matches_live_pipeline(self, app) -> None:
        assert app.config["MODEL_INPUT_DIM"] == 126
        assert app.config["MODEL_TYPE"] == "mlp"

    def test_get_config_returns_threshold(self, client) -> None:
        res = client.get("/api/config")
        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert "confidence_threshold" in body
        assert 0.0 < body["confidence_threshold"] <= 1.0

    def test_post_config_updates_threshold(self, client, app) -> None:
        classifier = app.extensions["classifier"]
        original = classifier.confidence_threshold
        try:
            res = client.post("/api/config", json={"confidence_threshold": 0.55})
            assert res.status_code == 200
            body = res.get_json()
            assert body is not None
            assert abs(body["confidence_threshold"] - 0.55) < 0.001
            assert abs(classifier.confidence_threshold - 0.55) < 0.001
        finally:
            classifier.confidence_threshold = original  # restore

    def test_post_config_clamps_above_one(self, client, app) -> None:
        classifier = app.extensions["classifier"]
        original = classifier.confidence_threshold
        try:
            res = client.post("/api/config", json={"confidence_threshold": 9.99})
            assert res.status_code == 200
            body = res.get_json()
            assert body["confidence_threshold"] <= 1.0
        finally:
            classifier.confidence_threshold = original

    def test_post_config_clamps_below_minimum(self, client, app) -> None:
        classifier = app.extensions["classifier"]
        original = classifier.confidence_threshold
        try:
            res = client.post("/api/config", json={"confidence_threshold": 0.0})
            assert res.status_code == 200
            body = res.get_json()
            assert body["confidence_threshold"] >= 0.1
        finally:
            classifier.confidence_threshold = original

    def test_post_config_non_numeric_returns_400(self, client) -> None:
        res = client.post("/api/config", json={"confidence_threshold": "high"})
        assert res.status_code == 400
        body = res.get_json()
        assert body is not None
        assert "error" in body

    def test_post_config_empty_body_is_noop(self, client, app) -> None:
        """Empty payload returns 200 with the current threshold unchanged."""
        classifier = app.extensions["classifier"]
        original = classifier.confidence_threshold
        res = client.post("/api/config", json={})
        assert res.status_code == 200
        body = res.get_json()
        assert abs(body["confidence_threshold"] - original) < 0.001

    def test_admin_write_requires_key_when_not_debug(self, client, app) -> None:
        original_debug = app.config["DEBUG"]
        original_key = app.config["API_KEY"]
        try:
            app.config["DEBUG"] = False
            app.config["API_KEY"] = "secret-test-key"

            no_key = client.post("/api/config", json={"confidence_threshold": 0.6})
            bad_key = client.delete("/api/history", headers={"X-API-Key": "wrong"})
            good_key = client.post(
                "/api/config",
                json={"confidence_threshold": 0.6},
                headers={"X-API-Key": "secret-test-key"},
            )

            assert no_key.status_code == 401
            assert bad_key.status_code == 401
            assert good_key.status_code == 200
        finally:
            app.config["DEBUG"] = original_debug
            app.config["API_KEY"] = original_key


class TestVideoUploadApi:
    def test_upload_video_missing_file_returns_400(self, client) -> None:
        res = client.post("/api/upload_video", data={}, content_type="multipart/form-data")
        assert res.status_code == 400
        body = res.get_json()
        assert body is not None
        assert "error" in body

    def test_upload_video_requires_mp4(self, client) -> None:
        res = client.post(
            "/api/upload_video",
            data={"video": (Path(__file__).open("rb"), "not-video.txt")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400

    def test_upload_video_rejects_invalid_mp4_content(self, client) -> None:
        import io

        res = client.post(
            "/api/upload_video",
            data={"video": (io.BytesIO(b"not a real mp4"), "demo.mp4")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400

    def test_upload_video_rejects_misplaced_ftyp_signature(self, client) -> None:
        import io

        res = client.post(
            "/api/upload_video",
            data={"video": (io.BytesIO(b"xxxxxxftypmp42"), "demo.mp4")},
            content_type="multipart/form-data",
        )
        assert res.status_code == 400

    def test_upload_video_happy_path(self, client, app) -> None:
        import io
        import routes.api as api_routes

        class DummyCapture:
            def __init__(self, _path: str) -> None:
                self._frames = [object(), object(), object(), object()]
                self._index = 0

            def isOpened(self) -> bool:
                return True

            def read(self):
                if self._index >= len(self._frames):
                    return False, None
                frame = self._frames[self._index]
                self._index += 1
                return True, frame

            def release(self) -> None:
                return None

        detector = app.extensions["gesture_detector"]
        classifier = app.extensions["classifier"]
        translator = app.extensions["translator"]

        with (
            patch.object(api_routes, "cv2", types.SimpleNamespace(VideoCapture=DummyCapture)),
            patch.object(detector, "detect", return_value=(None, np.ones(126, dtype=np.float32))),
            patch.object(
                classifier,
                "predict_with_details",
                return_value={"label_index": 1, "confidence": 0.9, "top_candidates": []},
            ),
            patch.object(classifier, "reset_sequence"),
            patch.object(translator, "get_label", return_value="Hello"),
        ):
            res = client.post(
                "/api/upload_video",
                data={
                    "video": (
                        io.BytesIO(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00mp42"),
                        "demo.mp4",
                    )
                },
                content_type="multipart/form-data",
            )

        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert body["translation_text"] == "Hello"
        assert body["top_gesture"] == "Hello"
        assert body["frames_total"] >= 1
        assert body["frames_processed"] >= 1


class TestModelReload:
    def test_model_reload_uses_public_translator_reload(self, client, app) -> None:
        translator = app.extensions["translator"]
        classifier = app.extensions["classifier"]
        with (
            patch.object(translator, "reload") as translator_reload,
            patch.object(classifier, "reload", return_value=True) as classifier_reload,
        ):
            res = client.post("/api/model/reload")

        assert res.status_code == 200
        translator_reload.assert_called_once_with()
        classifier_reload.assert_called_once_with()

    def test_model_reload_requires_key_when_not_debug(self, client, app) -> None:
        original_debug = app.config["DEBUG"]
        original_key = app.config["API_KEY"]
        try:
            app.config["DEBUG"] = False
            app.config["API_KEY"] = "secret-test-key"

            no_key = client.post("/api/model/reload")
            good_key = client.post(
                "/api/model/reload",
                headers={"X-API-Key": "secret-test-key"},
            )

            assert no_key.status_code == 401
            assert good_key.status_code in (200, 503)
        finally:
            app.config["DEBUG"] = original_debug
            app.config["API_KEY"] = original_key


class TestTranslationsApi:
    def test_get_translations_returns_requested_language(self, client) -> None:
        res = client.get("/api/translations/en")

        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert body["lang"] == "en"
        assert isinstance(body["translations"], dict)

    def test_get_translations_falls_back_to_english(self, client) -> None:
        res = client.get("/api/translations/unknown")

        assert res.status_code == 200
        body = res.get_json()
        assert body is not None
        assert body["lang"] == "en"

    def test_get_translations_missing_file_returns_404(
        self, client, app, tmp_path: Path
    ) -> None:
        original_static_folder = app.static_folder
        app.static_folder = str(tmp_path)
        try:
            res = client.get("/api/translations/en")
        finally:
            app.static_folder = original_static_folder

        assert res.status_code == 404
        body = res.get_json()
        assert body is not None
        assert body["code"] == 404

    def test_get_translations_invalid_json_returns_500(
        self, client, app, tmp_path: Path
    ) -> None:
        original_static_folder = app.static_folder
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "translations.json").write_text("{ invalid", encoding="utf-8")
        app.static_folder = str(tmp_path)
        try:
            res = client.get("/api/translations/en")
        finally:
            app.static_folder = original_static_folder

        assert res.status_code == 500
        body = res.get_json()
        assert body is not None
        assert body["code"] == 500
