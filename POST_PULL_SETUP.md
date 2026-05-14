# SignConnect — Run Perfectly After Pull

This guide eliminates the most common errors that happen after a fresh `git pull` or clone.

## TL;DR — One Command

```powershell
.\setup_and_run.ps1
```

If something breaks, read the sections below.

---

## What Breaks After a Pull and Why

| Issue | Cause | Fix |
|-------|-------|-----|
| `.venv311` missing | Gitignored — never committed | Recreate with Python 3.11 |
| `.env` missing | Gitignored for security | Copy from `.env.example` |
| `models/gesture_model.h5` missing | Gitignored (large binary) | Generate demo model or copy trained model |
| `models/gesture_model.demo` stale | Left over from old demo gen | Delete the marker file |
| Port 5000 busy | Another app is using it | Change `PORT` in `.env` |
| Camera not found | No webcam / driver issue | App still runs; stream shows retry placeholder |
| TTS offline | No internet / gTTS blocked | Falls back to pyttsx3 automatically |
| MediaPipe import error | Wrong protobuf or MP version | Use exact pins: `mediapipe==0.10.30`, `protobuf>=3.20,<4` |

---

## Step-by-Step Manual Setup

### 1. Python 3.11 (or 3.12)

The launcher scripts are hard-coded to `.venv311`. Install Python 3.11 from [python.org](https://www.python.org/downloads/) and make sure the **py launcher** is on PATH.

Verify:
```powershell
py -3.11 --version
```

### 2. Create the Virtual Environment

```powershell
py -3.11 -m venv .venv311
```

If you already have a `.venv311` from a different machine, it is likely broken. Delete it and recreate:
```powershell
Remove-Item -Recurse -Force .venv311
py -3.11 -m venv .venv311
```

### 3. Install Dependencies

```powershell
.\.venv311\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
```

**Windows-specific note:** TensorFlow in `requirements.txt` is pinned to `2.15.1` (CPU-only). Native Windows GPU support was dropped after TF 2.10. Do not try to install `tensorflow-gpu` on Windows.

**If pip hangs on protobuf / mediapipe resolution:**
```powershell
.\.venv311\Scripts\python.exe -m pip install mediapipe==0.10.30 protobuf "numpy>=1.26.0,<2.0"
.\.venv311\Scripts\python.exe -m pip install -r requirements.txt
```

### 4. Create `.env`

```powershell
Copy-Item .env.example .env
```

At minimum the defaults work for local development. Before production, change:
- `SECRET_KEY` — any random long string
- `API_KEY` — for admin endpoints (`/api/model/reload`, `/api/config` POST, DELETE history)

### 5. Ensure Directories Exist

```powershell
New-Item -ItemType Directory -Force -Path models,database,static\audio,logs
```

These are auto-created at runtime, but creating them now prevents race-condition edge cases.

### 6. Generate a Model (or Copy Your Trained One)

The repo does **not** include `gesture_model.h5` because it is large and changes after every training run.

**Option A — Demo model (untrained, runs instantly):**
```powershell
.\.venv311\Scripts\python.exe scripts\generate_demo_model.py
```

**Option B — Trained model:**
Copy your `gesture_model.h5` and `norm_stats.npz` into `models/`. Ensure `label_map.json` matches the model output classes. If you switch from MLP to temporal (BiGRU) models, also set in `.env`:
```env
MODEL_TYPE=temporal_landmark
SEQUENCE_LENGTH=30
```

**Important:** If a file named `models/gesture_model.demo` exists, the app treats the `.h5` as a placeholder and still runs in demo mode. Delete the marker if you deployed a real model:
```powershell
Remove-Item models/gesture_model.demo -ErrorAction SilentlyContinue
```

### 7. Verify with Diagnostics

```powershell
.\.venv311\Scripts\python.exe scripts\diagnose.py
```

Check these lines:
- `Camera opened: True` — expected if you have a webcam; `False` is okay, the app degrades gracefully.
- `MediaPipe Hands: OK`
- `Model loaded: OK` and `Input contract OK: True`
- `Output-label contract OK: True`

### 8. Run

```powershell
.\run.ps1
```

Or the full setup-and-run script:
```powershell
.\setup_and_run.ps1
```

Open `http://localhost:5000`.

---

## Common Runtime Errors & Fixes

### `ModuleNotFoundError: No module named 'tensorflow'`
You are running with the global Python instead of `.venv311`. Always use:
```powershell
.\.venv311\Scripts\python.exe app.py
```
or `run.ps1` / `setup_and_run.ps1`.

### `Camera not found or busy` (red error at startup)
The camera manager tries indices 0, 1, 2. If none work:
- The app still starts.
- The video stream shows a retrying placeholder.
- Upload video translation (`/api/upload_video`) still works.
- To suppress the error entirely, set `CAMERA_INDEX=-1` in `.env` (not officially supported but the error handler swallows it gracefully).

### `Model input dimension mismatch: expected 126, got X`
Your model was trained with a different feature shape. Re-train with the contract `2 hands × 21 landmarks × 3 coords = 126` values, or regenerate the demo model.

### `ValueError: numpy.dtype size changed`
You have a NumPy 2.x incompatibility. Pin it:
```powershell
.\.venv311\Scripts\python.exe -m pip install "numpy>=1.26.0,<2.0"
```

### `OSError: [WinError 10048] Address already in use`
Port 5000 is taken. Edit `.env`:
```env
PORT=5001
```

### `SECRET_KEY is set to the insecure default value`
You set `DEBUG=false` (production) but left the default `SECRET_KEY`. In `.env`:
```env
DEBUG=true
```
for local dev, or set a real `SECRET_KEY` for production.

---

## CI / Fresh-Machine Checklist

Use this if you are writing a Dockerfile, GitHub Actions workflow, or setting up a new teammate:

1. Python 3.11 installed
2. `py -3.11 -m venv .venv311`
3. `.venv311\Scripts\python.exe -m pip install -r requirements.txt`
4. `Copy-Item .env.example .env`
5. Ensure `models/label_map.json` is present (it is in the repo)
6. Generate demo model: `.venv311\Scripts\python.exe scripts\generate_demo_model.py`
7. Run diagnostics: `.venv311\Scripts\python.exe scripts\diagnose.py`
8. Start: `.\run.ps1`

---

## Need More Help?

- Run diagnostics and read every line: `scripts\diagnose.py`
- Check logs in the terminal; log level is controlled by `LOG_LEVEL` in `.env`
- Open an issue with the **full terminal output** of `diagnose.py`
