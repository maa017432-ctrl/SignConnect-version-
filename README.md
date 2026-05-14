# SignConnect

SignConnect is an AI-based real-time sign language translator built with Flask, OpenCV, MediaPipe, TensorFlow/Keras, gTTS, and SQLite.

## Features

- Real-time MJPEG webcam stream with WebSocket push predictions
- MediaPipe hand landmark extraction and model-based gesture classification
- Temporal BiGRU/BiGRU-Attention model for sequence-based WLASL gesture recognition
- Real-time coaching system — confidence-aware feedback messages below the video feed
- Text-to-speech output via gTTS (online) with pyttsx3 offline fallback
- Translation history stored in SQLite, scoped per signed-in user
- User accounts (sign-up / sign-in / sign-out) with session-based auth
- Multi-language UI and TTS support (English, Arabic, French, Spanish, German, Chinese, Japanese, Korean)
- Demo mode when no trained model is present
- Dark/light theme with localStorage persistence

## Setup

1. Create the Python 3.11 virtual environment expected by the launch scripts:
   - `py -3.11 -m venv .venv311`
2. Install dependencies:
   - `.venv311\Scripts\python.exe -m pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and adjust values.
4. Run:
   - `.\run.ps1`
5. Open:
   - `http://localhost:5000`

## Environment Notes

- Python 3.11 or 3.12 is supported. The launch scripts default to a `.venv311` environment.
- TensorFlow runs CPU-only on Windows. NVIDIA/CUDA GPU acceleration requires TF ≤ 2.10 on Windows native.
- `mediapipe==0.10.30` is pinned with `protobuf>=3.20,<4` — versions 0.10.31+ removed the legacy solutions API.
- To check the runtime environment before debugging, run:
  - `.venv311\Scripts\python.exe scripts\diagnose.py`

## Model Training (Overview)

1. Collect labeled hand landmark samples or processed frame data.
2. Train a Keras model that outputs probabilities for the labels in `models/label_map.json`.
3. Export model to `models/gesture_model.h5`.
4. Keep `models/label_map.json` aligned with output indices.
5. Keep the input feature contract at `126` values: two hands × 21 landmarks × 3 coordinates.

For WLASL temporal training:

1. Audit local data: `.venv311\Scripts\python.exe scripts\audit_wlasl.py`
2. Extract sequences: `.venv311\Scripts\python.exe scripts\wlasl_to_sequences.py --max-classes 50`
3. Train temporal model:
   - `.venv311\Scripts\python.exe scripts\train_temporal.py --max-classes 50 --arch bigru_attention --epochs 150 --augment`
   - Key flags: `--arch bigru|bigru_attention`, `--epochs N`, `--dropout F`, `--batch-size N`, `--augment`, `--exact-classes N`, `--drive-checkpoint DIR`
4. Set `MODEL_TYPE=temporal_landmark` and `SEQUENCE_LENGTH=30` in `.env` before starting the app.
5. Review `models/temporal_metrics.json` and `models/temporal_confusion_matrix.csv`; do not treat per-frame accuracy as the ground truth.

To run staged tier training end-to-end:

`.venv311\Scripts\python.exe scripts\run_wlasl_tiers.py --tiers 50 100 300`

## API Documentation

Interactive Swagger UI is available at `/api/docs`.

| Method | Endpoint | Description |
|---|---|---|
| GET | `/api/status` | Service health — camera, model, TTS state |
| GET | `/api/prediction` | Latest gesture prediction (label, confidence) |
| GET | `/api/camera_frame` | Single JPEG frame snapshot |
| POST | `/api/tts` | Synthesise TTS audio from text body — returns `{audio_url}`, no history entry |
| POST | `/api/translate` | Synthesise TTS audio from text body — returns `{audio_url}`, saves to history |
| POST | `/api/sentence/delete` | Remove last word from active sentence |
| POST | `/api/sentence/clear` | Clear entire active sentence |
| GET | `/api/history` | Last 50 translation entries for the signed-in user |
| DELETE | `/api/history` | Clear translation history for the signed-in user |
| GET | `/api/config` | Read live prediction thresholds |
| POST | `/api/config` | Update live prediction thresholds |
| POST | `/api/model/reload` | Hot-reload model from disk (admin API key required) |
| GET | `/api/labels` | All gesture labels from the loaded label map |
| GET | `/api/translations/<lang>` | UI string translations for the given language code |
