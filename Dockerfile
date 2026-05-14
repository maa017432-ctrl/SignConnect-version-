# ── Stage 1: build deps ────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# System libraries needed to compile/install OpenCV and MediaPipe native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# opencv-python-headless replaces opencv-python: identical C extensions, no
# Qt/X11 GUI bindings — saves ~60 MB in the final image.  The sed substitution
# rewrites only the package name; the version constraint (>=4.9.0) is kept as-is.
RUN sed 's/^opencv-python\([^-]\)/opencv-python-headless\1/' requirements.txt \
    | pip install --no-cache-dir --prefix=/install -r /dev/stdin

# ── Stage 2: runtime image ─────────────────────────────────────────────────
FROM python:3.11-slim

LABEL maintainer="SignConnect"
LABEL description="AI-powered real-time sign language translator"

WORKDIR /app

# Runtime C libraries required by OpenCV (headless) and MediaPipe.
# libgl1     — OpenGL symbols used by MediaPipe even in headless mode.
# libglib2.0 — GLib, required by MediaPipe's native protobuf layer.
# libgomp1   — GNU OpenMP, required by TensorFlow CPU kernels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user: reduces blast radius if the application is ever compromised.
RUN groupadd --system signconnect \
    && useradd --system --gid signconnect --no-create-home signconnect

# Copy pre-built packages from builder stage
COPY --from=builder /install /usr/local

# Copy application source — owned by the runtime user from the start so that
# no root-owned files remain in the final image layer.
COPY --chown=signconnect:signconnect . .

# Ensure all writable runtime directories exist and belong to the app user
# BEFORE the VOLUME declaration.  Named volumes created by docker-compose
# inherit the ownership of the mount-point directory in the image, so this
# guarantees the app can write to each volume without running as root.
RUN mkdir -p database data models static/audio \
    && chown -R signconnect:signconnect database data models static/audio

# Persistent volumes — mount these to keep data between container restarts
VOLUME ["/app/database", "/app/data", "/app/models", "/app/static/audio"]

EXPOSE 5000

ENV HOST=0.0.0.0 \
    PORT=5000 \
    LOG_LEVEL=INFO \
    DEBUG=false

USER signconnect

# run_production.py applies production-tuned Waitress settings:
#   connection_limit=500, channel_timeout=120, asyncore_use_poll=True
# asyncore_use_poll is required so MJPEG frame chunks flush immediately
# rather than being coalesced inside Waitress's async loop.
# WebSocket upgrades fall back to long-polling (threading async_mode);
# place a reverse proxy in front for full WebSocket support if needed.
CMD ["python", "run_production.py"]
