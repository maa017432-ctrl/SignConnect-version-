(function () {
  "use strict";

  /* ── Element refs ─────────────────────────────────────────── */
  const themeToggle = document.getElementById("theme-toggle");
  const video = document.getElementById("video-stream");
  const videoOverlay = document.getElementById("video-overlay");
  const recognizedText = document.getElementById("recognized-text");
  const confidenceBadge = document.getElementById("confidence-badge");
  const sentenceDisplay = document.getElementById("sentence-display");
  const commitProgress = document.getElementById("commit-progress");
  const progressHint = document.getElementById("progress-hint");
  const historyList = document.getElementById("history-list");
  const cameraStatus = document.getElementById("camera-status");
  const cameraDot = document.getElementById("camera-dot");
  const modelStatus = document.getElementById("model-status");
  const modelDot = document.getElementById("model-dot");
  const fpsStatus = document.getElementById("fps-status") || document.getElementById("fps-display");
  const liveBadge = document.getElementById("sc-live-badge");
  const startBtn = document.getElementById("start-btn");
  const pauseBtn = document.getElementById("pause-btn");
  const clearBtn = document.getElementById("clear-btn");
  const copyBtn = document.getElementById("copy-btn");
  const deleteWordBtn = document.getElementById("delete-word-btn");
  const speakBtn = document.getElementById("speak-btn");
  const autoSpeakBtn = document.getElementById("auto-speak-btn");
  const refreshHistBtn = document.getElementById("refresh-history-btn");
  const clearHistBtn = document.getElementById("clear-history-btn");
  const uploadVideoBtn = document.getElementById("upload-video-btn");
  const uploadVideoInput = document.getElementById("upload-video-input");
  const uploadVideoStatus = document.getElementById("upload-video-status");
  const uploadVideoProgress = document.getElementById("upload-video-progress");
  const langSelect = document.getElementById("lang-select");
  const thresholdSlider = document.getElementById("threshold-slider");
  const thresholdVal = document.getElementById("threshold-val");
  const trainingModeToggle = document.getElementById("training-mode-toggle");
  const topkPanel = document.getElementById("topk-panel");
  const topkList = document.getElementById("topk-list");
  const confidenceFill = document.getElementById("confidence-bar-fill");
  const predictionOverlay = document.getElementById("prediction-overlay");
  const predictionOverlayLabel = document.getElementById("prediction-overlay-label");
  const predictionOverlayConfidence = document.getElementById("prediction-overlay-confidence");
  const clearHistoryPageBtn = document.getElementById("clear-history-page-btn");
  const downloadHistoryBtn = document.getElementById("download-history-btn");
  const SUPPORTED_UI_LANGS = new Set(["en", "asl"]);

  /* ── Coaching System Elements ──────────────────────────────── */
  const coachingContainer = document.getElementById("coaching-container");
  const coachingMessage = document.getElementById("coaching-message");
  const coachingIcon = document.getElementById("coaching-icon");
  const coachingText = document.getElementById("coaching-text");

  /* ── Session Statistics Elements ───────────────────────────── */
  const statCount = document.getElementById("stat-count");
  const statAvgConf = document.getElementById("stat-avg-conf");
  const statAccuracy = document.getElementById("stat-accuracy");
  const statDuration = document.getElementById("stat-duration");
  const statBest = document.getElementById("stat-best");
  const statCommon = document.getElementById("stat-common");

  /* ── Practice Mode / Gesture Learning Elements ──────────────── */
  const practiceBtn = document.getElementById("practice-btn");
  const practicePanel = document.getElementById("practice-panel");
  const practiceCloseBtn = document.getElementById("practice-close-btn");
  const practiceSearchInput = document.getElementById("practice-search-input");
  const practiceList = document.getElementById("practice-list");
  const practiceVisualizer = document.getElementById("practice-visualizer");
  const practiceBackBtn = document.getElementById("practice-back-btn");
  const gestureCanvas = document.getElementById("gesture-canvas");

  /* ── Settings Panel Elements ───────────────────────────────── */
  const settingsBtn = document.getElementById("settings-btn");
  const settingsModal = document.getElementById("settings-modal");
  const settingsCloseBtn = document.getElementById("settings-close-btn");
  const settingsResetBtn = document.getElementById("settings-reset-btn");
  const settingsSaveBtn = document.getElementById("settings-save-btn");
  const settingsOverlay = document.querySelector(".settings-overlay");

  // Settings inputs
  const settingsCameraSelect = document.getElementById("camera-select");
  const settingsThresholdSlider = document.getElementById("settings-threshold-slider");
  const settingsThresholdVal = document.getElementById("settings-threshold-val");
  const settingsLangSelect = document.getElementById("settings-lang-select");
  const settingsTrainingToggle = document.getElementById("settings-training-toggle");
  const settingsAudioToggle = document.getElementById("settings-audio-toggle");
  const settingsThemeToggle = document.getElementById("settings-theme-toggle");
  const settingsThemeLabel = document.getElementById("settings-theme-label");

  /* ── Stream state ─────────────────────────────────────────── */
  const FRAME_MS = 80;    // ~12.5 fps camera polling target
  const STATUS_MS = 4000;
  const PREDICT_MS = 300;   // HTTP fallback prediction poll interval

  const ICON_PAUSE = '<svg viewBox="0 0 24 24" fill="currentColor" class="sc-btn-icon" style="width:14px;height:14px"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>';
  const ICON_PLAY  = '<svg viewBox="0 0 24 24" fill="currentColor" class="sc-btn-icon" style="width:14px;height:14px"><polygon points="5 3 19 12 5 21 5 3"/></svg>';

  let streamTimer = null;
  let predictionTimer = null; // set only when socket.io unavailable
  let checkVideoTimer = null; // MJPEG stream readiness probe
  let statusPollTimer = null;
  let fpsPollTimer = null;
  let paused = true;
  let frameInFlight = false;
  let blobUrl = null;
  let prevFrameAt = 0;
  let fpsWindow = [];   // sliding window of frame intervals (ms)
  let renderState = {
    label: "",
    confidencePct: -1,
    sentence: "",
    progressWidth: "",
    topCandidatesKey: "",
    overlayLabel: "",
    overlayConfText: "",
  };

  /* ── Auto-speak ────────────────────────────────────────────── */
  const AUTO_SPEAK_STORAGE_KEY = "signconnect_auto_speak";
  let autoSpeak = localStorage.getItem(AUTO_SPEAK_STORAGE_KEY) === "1";
  let _prevSentenceWordCount = 0;  // tracks word count to detect new commits
  let _autoSpeakInFlight = false;  // prevents overlapping TTS requests
  let _activeAudio = null;
  let cameraNotificationSent = false;

  function _applyAutoSpeakButton() {
    if (!autoSpeakBtn) return;
    if (autoSpeak) {
      autoSpeakBtn.classList.add("sc-btn--active");
      autoSpeakBtn.setAttribute("aria-pressed", "true");
      autoSpeakBtn.title = "Auto-speak ON — click to disable";
    } else {
      autoSpeakBtn.classList.remove("sc-btn--active");
      autoSpeakBtn.setAttribute("aria-pressed", "false");
      autoSpeakBtn.title = "Auto-speak OFF — click to enable";
    }
  }

  function toggleAutoSpeak() {
    autoSpeak = !autoSpeak;
    localStorage.setItem(AUTO_SPEAK_STORAGE_KEY, autoSpeak ? "1" : "0");
    if (!autoSpeak && _activeAudio) {
      _activeAudio.pause();
      _activeAudio.currentTime = 0;
    }
    _applyAutoSpeakButton();
  }

  function playAudioUrl(audioUrl) {
    if (!audioUrl) return;
    if (_activeAudio) {
      _activeAudio.pause();
      _activeAudio.currentTime = 0;
    }
    const audio = new Audio(audioUrl);
    _activeAudio = audio;
    audio.addEventListener("ended", () => {
      if (_activeAudio === audio) _activeAudio = null;
    }, { once: true });
    audio.play().catch(() => { });
  }

  async function _autoSpeakSentence(sentence) {
    if (_autoSpeakInFlight) return;
    _autoSpeakInFlight = true;
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sentence, lang: getSelectedLang() }),
      });
      if (!res.ok) return;
      const data = await res.json();
      playAudioUrl(data.audio_url);
    } catch { /* network/playback errors are non-fatal */ }
    finally { _autoSpeakInFlight = false; }
  }

  /* ── WebSocket (socket.io) — push-based predictions ─────────── */
  let socketConnected = false;
  let _socket = null; // module-level ref so visibilitychange can reach it
  let _visibilityListenerAttached = false; // guard against duplicate registration

  /* ── User Coaching System ──────────────────────────────────── */
  const COACHING_CONFIG = {
    DEBOUNCE_MS: 350,        // Delay before updating coaching message (avoid flicker)
    SUCCESS_TIMEOUT_MS: 2000, // Duration to show success message
    STABILITY_THRESHOLD: 0.15, // Confidence variance threshold for stability
  };

  let coachingState = {
    currentMessage: null,
    currentState: null,
    lastGestureLabel: null,
    confidenceHistory: [],
    debounceTimer: null,
    successTimer: null,
    isVisible: false,
  };

  const COACHING_MESSAGES = {
    no_hand: {
      state: "error",
      icon: "❌",
      text: "Hand not detected",
      priority: 1,
    },
    low_confidence: {
      state: "error",
      icon: "❌",
      text: "Gesture not recognized",
      priority: 1,
    },
    hand_not_centered: {
      state: "warning",
      icon: "⚠️",
      text: "Center your hand",
      priority: 2,
    },
    adjust_distance: {
      state: "warning",
      icon: "⚠️",
      text: "Move hand closer",
      priority: 2,
    },
    hold_steady: {
      state: "warning",
      icon: "⚠️",
      text: "Hold steady",
      priority: 2,
    },
    unstable: {
      state: "warning",
      icon: "⚠️",
      text: "Avoid quick movement",
      priority: 2,
    },
    info: {
      state: "info",
      icon: "ℹ️",
      text: "Keep hand steady to confirm",
      priority: 3,
    },
    good_detection: {
      state: "success",
      icon: "✅",
      text: "Good position",
      priority: 4,
    },
    gesture_captured: {
      state: "success",
      icon: "✅",
      text: "Gesture captured successfully",
      priority: 4,
    },
  };

  /**
   * Determine the coaching message based on current prediction state
   */
  function determineCoachingMessage(data) {
    // If paused or no data, hide coaching
    if (paused || !data) {
      return null;
    }

    if (data.coaching && typeof data.coaching === "object") {
      const coaching = data.coaching;
      return {
        state: coaching.state || "info",
        icon: coaching.state === "error" ? "❌" : coaching.state === "success" ? "✅" : coaching.state === "warning" ? "⚠️" : "ℹ️",
        text: coaching.message || "Center your hand",
      };
    }

    const label = data.smoothed_label || data.label;
    const confidence = data.confidence || 0;
    const coolingDown = data.is_cooling_down || false;

    // Track confidence history for stability detection
    coachingState.confidenceHistory.push(confidence);
    if (coachingState.confidenceHistory.length > 10) {
      coachingState.confidenceHistory.shift();
    }

    // Detect if hand disappeared
    const hadGesture = coachingState.lastGestureLabel !== null && coachingState.lastGestureLabel !== "—" && coachingState.lastGestureLabel !== "…";
    const hasGesture = label && label !== "—" && label !== "…";
    coachingState.lastGestureLabel = label;

    // ── Message priority logic (high to low) ──

    // 1. ERROR priority: No gesture detected
    if (!hasGesture && hadGesture && !coolingDown) {
      return COACHING_MESSAGES.no_hand;
    }

    if (!hasGesture) {
      return COACHING_MESSAGES.no_hand;
    }

    // 2. ERROR priority: Very low confidence
    if (hasGesture && confidence < 0.5) {
      return COACHING_MESSAGES.low_confidence;
    }

    // 3. WARNING priority: Gesture unstable
    const isUnstable = detectUnstability();
    if (hasGesture && isUnstable && confidence < 0.8) {
      return COACHING_MESSAGES.unstable;
    }

    // 4. WARNING priority: Low-medium confidence (hold steady)
    if (hasGesture && confidence >= 0.5 && confidence < 0.7) {
      return COACHING_MESSAGES.hold_steady;
    }

    // 5. WARNING priority: Medium confidence (info hint)
    if (hasGesture && confidence >= 0.7 && confidence < 0.85) {
      return COACHING_MESSAGES.info;
    }

    // 6. SUCCESS priority: Good detection (high confidence)
    if (hasGesture && confidence >= 0.85 && coolingDown) {
      return COACHING_MESSAGES.gesture_captured;
    }

    if (hasGesture && confidence >= 0.85) {
      return COACHING_MESSAGES.good_detection;
    }

    return null;
  }

  /**
   * Detect if gesture is unstable (high variance in recent confidence)
   */
  function detectUnstability() {
    if (coachingState.confidenceHistory.length < 5) return false;

    const recent = coachingState.confidenceHistory.slice(-5);
    const mean = recent.reduce((a, b) => a + b, 0) / recent.length;
    const variance = recent.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / recent.length;
    const stdDev = Math.sqrt(variance);

    return stdDev > COACHING_CONFIG.STABILITY_THRESHOLD;
  }

  /**
   * Update coaching UI with debouncing
   */
  function updateCoachingUI(data) {
    if (!coachingContainer || !coachingMessage) return;

    // Clear any pending debounce or success timers
    if (coachingState.debounceTimer) {
      clearTimeout(coachingState.debounceTimer);
    }
    if (coachingState.successTimer) {
      clearTimeout(coachingState.successTimer);
    }

    // Determine which message to show
    const message = determineCoachingMessage(data);

    // If no message, hide coaching
    if (!message) {
      hideCoaching();
      return;
    }

    // Debounce message updates to prevent flickering
    coachingState.debounceTimer = setTimeout(() => {
      showCoachingMessage(message);

      // Auto-hide success messages after timeout
      if (message.state === "success") {
        coachingState.successTimer = setTimeout(() => {
          hideCoaching();
        }, COACHING_CONFIG.SUCCESS_TIMEOUT_MS);
      }
    }, COACHING_CONFIG.DEBOUNCE_MS);
  }

  /**
   * Display coaching message with smooth animation
   */
  function showCoachingMessage(message) {
    if (!coachingContainer || !coachingMessage || !coachingIcon || !coachingText) return;

    // Update message content
    coachingIcon.textContent = message.icon;
    coachingText.textContent = message.text;

    // Remove all previous state classes
    coachingMessage.classList.remove("info", "warning", "error", "success");

    // Add new state class with animation
    coachingMessage.classList.add(message.state);

    // Show container
    coachingContainer.classList.remove("hidden");
    coachingState.isVisible = true;
    coachingState.currentState = message.state;
  }

  /**
   * Hide coaching container
   */
  function hideCoaching() {
    if (!coachingContainer) return;
    coachingContainer.classList.add("hidden");
    coachingState.isVisible = false;
    coachingState.currentState = null;
  }

  /**
   * Reset coaching state (called when stream pauses)
   */
  function resetCoachingState() {
    coachingState.confidenceHistory = [];
    coachingState.lastGestureLabel = null;
    coachingState.currentMessage = null;
    coachingState.currentState = null;
    hideCoaching();
  }

  /* ── Session Statistics System ─────────────────────────────── */
  let sessionStats = {
    totalGestures: 0,
    confidenceScores: [],
    gestureCount: {}, // { label: count }
    bestGesture: null,
    bestConfidence: 0,
    startTime: null,
    durationTimer: null,
    currentThreshold: 0.75,
  };

  function updateSessionStats(data) {
    const label = data.smoothed_label || data.label;
    const confidence = data.confidence || 0;

    // Skip empty labels
    if (!label || label === "—" || label === "…") return;

    // Track gesture
    sessionStats.totalGestures++;
    sessionStats.confidenceScores.push(confidence);

    // Track gesture frequency
    if (!sessionStats.gestureCount[label]) {
      sessionStats.gestureCount[label] = 0;
    }
    sessionStats.gestureCount[label]++;

    // Track best gesture
    if (confidence > sessionStats.bestConfidence) {
      sessionStats.bestConfidence = confidence;
      sessionStats.bestGesture = label;
    }

    // Update UI
    renderSessionStats(data.confidence_threshold || 0.75);
  }

  function renderSessionStats(threshold) {
    if (!statCount) return;

    sessionStats.currentThreshold = threshold;

    // Total gestures
    if (statCount) statCount.textContent = sessionStats.totalGestures;

    // Average confidence
    if (statAvgConf && sessionStats.confidenceScores.length > 0) {
      const avg = sessionStats.confidenceScores.reduce((a, b) => a + b, 0) / sessionStats.confidenceScores.length;
      statAvgConf.textContent = Math.round(avg * 100) + "%";
    }

    // Accuracy (% above threshold)
    if (statAccuracy && sessionStats.confidenceScores.length > 0) {
      const accurateCount = sessionStats.confidenceScores.filter((c) => c >= threshold).length;
      const accuracy = (accurateCount / sessionStats.confidenceScores.length) * 100;
      statAccuracy.textContent = Math.round(accuracy) + "%";
    }

    // Best gesture
    if (statBest && sessionStats.bestGesture) {
      statBest.textContent = sessionStats.bestGesture + " (" + Math.round(sessionStats.bestConfidence * 100) + "%)";
    }

    // Most common gesture
    if (statCommon && Object.keys(sessionStats.gestureCount).length > 0) {
      const mostCommon = Object.entries(sessionStats.gestureCount).reduce((a, b) =>
        b[1] > a[1] ? b : a
      );
      statCommon.textContent = mostCommon[0] + " (" + mostCommon[1] + "x)";
    }
  }

  function startSessionTimer() {
    if (sessionStats.durationTimer) clearInterval(sessionStats.durationTimer);
    sessionStats.startTime = Date.now();

    sessionStats.durationTimer = setInterval(() => {
      if (paused || !sessionStats.startTime) return;
      const elapsed = Math.floor((Date.now() - sessionStats.startTime) / 1000);
      const minutes = Math.floor(elapsed / 60);
      const seconds = elapsed % 60;

      if (statDuration) {
        if (minutes > 0) {
          statDuration.textContent = minutes + "m " + seconds + "s";
        } else {
          statDuration.textContent = seconds + "s";
        }
      }
    }, 1000);
  }

  function resetSessionStats() {
    const timerToCancel = sessionStats.durationTimer;
    sessionStats = {
      totalGestures: 0,
      confidenceScores: [],
      gestureCount: {},
      bestGesture: null,
      bestConfidence: 0,
      startTime: null,
      durationTimer: null,
      currentThreshold: 0.75,
    };

    // Reset UI
    if (statCount) statCount.textContent = "0";
    if (statAvgConf) statAvgConf.textContent = "0%";
    if (statAccuracy) statAccuracy.textContent = "0%";
    if (statDuration) statDuration.textContent = "0s";
    if (statBest) statBest.textContent = "—";
    if (statCommon) statCommon.textContent = "—";

    if (timerToCancel) clearInterval(timerToCancel);
  }

  /* ── Practice Mode / Gesture Learning System ────────────────── */
  let practiceState = {
    gestureReferences: {},
    currentGesture: null,
    isOpen: false,
    filteredGestures: [],
  };

  /**
   * Load gesture references from JSON file
   */
  async function loadGestureReferences() {
    try {
      const response = await fetch("/static/data/gesture_references.json");
      if (!response.ok) throw new Error("Failed to load gesture references");
      practiceState.gestureReferences = await response.json();
      return true;
    } catch (error) {
      console.error("Error loading gesture references:", error);
      return false;
    }
  }

  /**
   * Render gesture list in practice panel
   */
  function renderGestureList(gestures = null) {
    if (!practiceList) return;

    const items = gestures || Object.entries(practiceState.gestureReferences);
    practiceList.innerHTML = "";

    if (items.length === 0) {
      practiceList.innerHTML = '<p style="color: var(--text-muted); text-align: center; padding: var(--space-4);">No gestures found</p>';
      return;
    }

    items.forEach(([key, gesture]) => {
      const item = document.createElement("div");
      item.className = "gesture-item";
      item.innerHTML = `
        <div class="gesture-item-left">
          <span class="gesture-item-name">${escHtml(gesture.name)}</span>
          <span class="gesture-item-desc">${escHtml(gesture.description)}</span>
        </div>
        <span class="gesture-item-difficulty ${safeClass(gesture.difficulty)}">${escHtml(gesture.difficulty)}</span>
      `;

      item.addEventListener("click", () => {
        selectGesture(key, gesture);
      });

      practiceList.appendChild(item);
    });
  }

  /**
   * Select a gesture and show visualizer
   */
  function selectGesture(key, gesture) {
    practiceState.currentGesture = { key, ...gesture };

    // Update visualizer header
    document.getElementById("visualizer-title").textContent = gesture.name;
    document.getElementById("visualizer-description").textContent = gesture.description;
    const diffBadge = document.getElementById("visualizer-difficulty");
    diffBadge.textContent = gesture.difficulty;
    diffBadge.className = `visualizer-badge ${gesture.difficulty}`;

    // Switch views
    practiceList.style.display = "none";
    document.querySelector(".practice-search").style.display = "none";
    practiceVisualizer.classList.remove("hidden");

    // Draw gesture on canvas
    drawGestureReference(gesture);
  }

  /**
   * Go back to gesture list
   */
  function backToGestureList() {
    practiceList.style.display = "grid";
    document.querySelector(".practice-search").style.display = "block";
    practiceVisualizer.classList.add("hidden");
    practiceState.currentGesture = null;
  }

  /**
   * Draw gesture reference on canvas
   */
  function drawGestureReference(gesture) {
    if (!gestureCanvas) return;

    const ctx = gestureCanvas.getContext("2d");
    const width = gestureCanvas.width;
    const height = gestureCanvas.height;

    // Clear canvas with gradient background
    const gradient = ctx.createLinearGradient(0, 0, width, height);
    gradient.addColorStop(0, "rgba(30, 40, 60, 0.5)");
    gradient.addColorStop(1, "rgba(20, 30, 45, 0.5)");
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, width, height);

    const landmarks = gesture.landmarks || [];
    const connections = gesture.connections || [];

    // Draw connections (bones) first
    ctx.strokeStyle = "rgba(100, 150, 255, 0.6)";
    ctx.lineWidth = 2;
    ctx.lineCap = "round";

    connections.forEach(([from, to]) => {
      if (from < landmarks.length && to < landmarks.length) {
        const fromLm = landmarks[from];
        const toLm = landmarks[to];

        const x1 = fromLm.x * width;
        const y1 = fromLm.y * height;
        const x2 = toLm.x * width;
        const y2 = toLm.y * height;

        ctx.beginPath();
        ctx.moveTo(x1, y1);
        ctx.lineTo(x2, y2);
        ctx.stroke();
      }
    });

    // Draw landmarks (joints) as circles
    landmarks.forEach((landmark, idx) => {
      const x = landmark.x * width;
      const y = landmark.y * height;
      const radius = 6;

      // Color code landmarks (wrist = blue, fingertips = green)
      const isWrist = idx === 0;
      const isFingertip = [4, 8, 12, 16, 20].includes(idx);

      ctx.fillStyle = isWrist ? "#3B82F6" : isFingertip ? "#10B981" : "#60A5FA";
      ctx.beginPath();
      ctx.arc(x, y, radius, 0, Math.PI * 2);
      ctx.fill();

      // Draw highlight
      ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
      ctx.lineWidth = 1.5;
      ctx.stroke();
    });
  }

  /**
   * Filter gestures by search
   */
  function filterGestures(query) {
    if (!query.trim()) {
      renderGestureList();
      return;
    }

    const filtered = Object.entries(practiceState.gestureReferences).filter(([key, gesture]) =>
      gesture.name.toLowerCase().includes(query.toLowerCase()) ||
      gesture.description.toLowerCase().includes(query.toLowerCase())
    );

    renderGestureList(filtered);
  }

  /**
   * Toggle practice mode panel
   */
  function togglePracticeMode() {
    practiceState.isOpen = !practiceState.isOpen;

    if (practiceState.isOpen) {
      practicePanel.classList.remove("hidden");
      practiceList.style.display = "grid";
      document.querySelector(".practice-search").style.display = "block";
      practiceVisualizer.classList.add("hidden");
      practiceSearchInput.value = "";
      renderGestureList();
    } else {
      practicePanel.classList.add("hidden");
      backToGestureList();
    }
  }

  /* ── Settings Management System ────────────────────────────── */
  let settingsState = {
    camera: "1",
    threshold: 75,
    language: "en",
    training: false,
    audioEnabled: true,
    theme: "dark",
  };

  const SETTINGS_STORAGE_KEY = "signconnect_settings";
  const DEFAULTS = {
    camera: "1",
    threshold: 75,
    language: "en",
    training: false,
    audioEnabled: true,
    theme: "dark",
  };

  /**
   * Load settings from localStorage
   */
  function loadSettings() {
    try {
      const saved = localStorage.getItem(SETTINGS_STORAGE_KEY);
      if (saved) {
        settingsState = { ...DEFAULTS, ...JSON.parse(saved) };
      } else {
        settingsState = { ...DEFAULTS };
      }
      applySettings();
    } catch (error) {
      console.error("Error loading settings:", error);
      settingsState = { ...DEFAULTS };
    }
  }

  /**
   * Save settings to localStorage
   */
  function saveSettings() {
    try {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settingsState));
      applySettings();
      showSettingsFeedback("Settings saved successfully");
    } catch (error) {
      console.error("Error saving settings:", error);
      showSettingsFeedback("Error saving settings", true);
    }
  }

  /**
   * Apply settings to UI and app
   */
  function applySettings() {
    // Camera
    if (settingsCameraSelect) {
      settingsCameraSelect.value = settingsState.camera;
    }

    // Threshold
    if (settingsThresholdSlider) {
      settingsThresholdSlider.value = settingsState.threshold;
      if (settingsThresholdVal) {
        settingsThresholdVal.textContent = settingsState.threshold + "%";
      }
    }
    // Also update inline threshold if it exists
    if (thresholdSlider) {
      thresholdSlider.value = settingsState.threshold;
      if (thresholdVal) {
        thresholdVal.textContent = settingsState.threshold + "%";
      }
    }

    // Language
    if (settingsLangSelect) {
      settingsLangSelect.value = settingsState.language;
    }
    if (langSelect) {
      langSelect.value = settingsState.language;
    }

    // Training mode
    if (settingsTrainingToggle) {
      settingsTrainingToggle.checked = settingsState.training;
    }
    if (trainingModeToggle) {
      trainingModeToggle.checked = settingsState.training;
    }

    // Audio
    if (settingsAudioToggle) {
      settingsAudioToggle.checked = settingsState.audioEnabled;
    }

    // Theme
    if (settingsThemeToggle) {
      settingsThemeToggle.checked = settingsState.theme === "light";
      if (settingsThemeLabel) {
        settingsThemeLabel.textContent = settingsState.theme === "light" ? "Dark Mode" : "Light Mode";
      }
    }

    // Apply theme
    applyTheme(settingsState.theme);
  }

  /**
   * Update setting value
   */
  function updateSetting(key, value) {
    settingsState[key] = value;
  }

  /**
   * Reset to default settings
   */
  function resetSettings() {
    if (confirm("Reset all settings to defaults?")) {
      settingsState = { ...DEFAULTS };
      applySettings();
      saveSettings();
      showSettingsFeedback("Settings reset to defaults");
    }
  }

  /**
   * Show temporary feedback message
   */
  function showSettingsFeedback(message, isError = false) {
    // Create feedback element
    const feedback = document.createElement("div");
    feedback.className = `settings-feedback ${isError ? "error" : "success"}`;
    feedback.textContent = message;
    feedback.style.cssText = `
      position: fixed;
      bottom: 20px;
      right: 20px;
      padding: 12px 20px;
      background: ${isError ? "var(--color-error)" : "var(--color-success)"};
      color: white;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      animation: slide-up 0.3s ease;
      z-index: 1001;
    `;

    document.body.appendChild(feedback);

    setTimeout(() => {
      feedback.style.animation = "fade-out 0.3s ease";
      setTimeout(() => feedback.remove(), 300);
    }, 2000);
  }

  /**
   * Toggle settings modal
   */
  function toggleSettingsModal() {
    if (!settingsModal) return;
    if (settingsModal.classList.contains("hidden")) {
      settingsModal.classList.remove("hidden");
      loadSettingsUI();
    } else {
      settingsModal.classList.add("hidden");
    }
  }

  /**
   * Load current settings into modal UI
   */
  function loadSettingsUI() {
    applySettings();
  }

  /**
   * Close settings modal
   */
  function closeSettingsModal() {
    if (settingsModal) settingsModal.classList.add("hidden");
  }

  function initSocket() {
    if (typeof io === "undefined") {
      startPredictionPoll();
      return;
    }
    _socket = io({
      reconnectionAttempts: Infinity,  // never give up — retries survive lid-open
      reconnectionDelay: 1000,
      reconnectionDelayMax: 30000,     // cap exponential backoff at 30 s
      timeout: 4000,
      transports: ["websocket", "polling"],
    });
    const socket = _socket;

    socket.on("connect", () => {
      socketConnected = true;
      LOGGER("WebSocket connected");
      stopPredictionPoll();
    });

    socket.on("disconnect", () => {
      socketConnected = false;
      // Restart HTTP polling as fallback while disconnected
      if (!predictionTimer) startPredictionPoll();
    });

    socket.on("connect_error", () => {
      if (!socketConnected && !predictionTimer) startPredictionPoll();
    });

    socket.on("prediction", (data) => {
      updatePredictionUI(data);
    });

    // ── Lid-open / tab-focus recovery ────────────────────────────
    // When the OS suspends the network stack (lid close, sleep), both the
    // WebSocket TCP connection and the MJPEG <img> HTTP stream stall silently.
    // visibilitychange fires the moment JS resumes after wake-up, giving us
    // the earliest possible hook to force reconnection of both channels.
    // Guard ensures only one listener is ever registered, even if initSocket()
    // were called more than once.
    if (!_visibilityListenerAttached) {
      _visibilityListenerAttached = true;
      document.addEventListener("visibilitychange", () => {
        if (document.visibilityState !== "visible") return;
        // Force MJPEG stream reconnect — a stalled <img> never self-recovers
        if (!paused && video && video.src) {
          video.src = mjpegUrl() + "?_=" + Date.now();
        }
        // Force socket reconnect if it drifted offline while the tab was hidden
        if (_socket && !_socket.connected) {
          _socket.connect();
        }
      });
    }

  }

  function stopPredictionPoll() {
    if (!predictionTimer) return;
    clearInterval(predictionTimer);
    predictionTimer = null;
  }

  function startPredictionPoll() {
    if (predictionTimer) return;
    predictionTimer = setInterval(pollPrediction, PREDICT_MS);
    pollPrediction();
  }

  function LOGGER(msg) {
    if (typeof console !== "undefined") console.debug("[SignConnect]", msg);
  }

  /* ── Frame URLs ────────────────────────────────────────────── */
  function mjpegUrl() {
    return (video && video.dataset.mjpegUrl) || "/video_feed";
  }

  function frameUrl() {
    return (video && video.dataset.frameUrl) || "/api/camera_frame";
  }

  /* ── Loading overlay ──────────────────────────────────────── */
  function showOverlay(text) {
    if (!videoOverlay) return;
    const msg = videoOverlay.querySelector(".overlay-msg");
    if (msg) msg.textContent = text || "Connecting to camera…";
    videoOverlay.classList.remove("hidden");
  }

  function hideOverlay() {
    if (videoOverlay) videoOverlay.classList.add("hidden");
  }

  /* ── Theme toggle ─────────────────────────────────────────── */
  function initTheme() {
    const saved = settingsState.theme || localStorage.getItem("sc_theme") || "dark";
    applyTheme(saved);

    if (themeToggle) {
      themeToggle.setAttribute("aria-pressed", saved === "light");
      themeToggle.addEventListener("click", () => {
        const current = document.body.getAttribute("data-theme") || "dark";
        const next = current === "dark" ? "light" : "dark";
        applyTheme(next);
        themeToggle.setAttribute("aria-pressed", next === "light");
        updateSetting("theme", next);
        localStorage.setItem("sc_theme", next);
      });
    }
  }

  /**
   * Apply theme to document
   */
  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme || "dark");
    document.body.setAttribute("data-theme", theme || "dark");
  }

  /* ── Status dot helpers ───────────────────────────────────── */
  function setDot(dot, state) {
    if (!dot) return;
    dot.className = "status-dot " + (state || "");
  }

  /* ── Poll /api/status (slow — health chips only) ──────────── */
  async function pollStatus() {
    try {
      const res = await fetch("/api/status", { cache: "no-store" });
      const data = await res.json();

      if (cameraStatus) {
        const ok = data.camera && data.camera_frame_route !== false;
        cameraStatus.textContent = ok ? "Camera: OK" : "Camera: DOWN";
        setDot(cameraDot, ok ? "ok" : "err");
        if (ok) {
          cameraNotificationSent = false;
        } else if (!cameraNotificationSent) {
          notifyUser("camera", "Camera unavailable", "Check camera connection and browser permissions.");
          cameraNotificationSent = true;
        }

        // If camera is definitively down, show a clear message in the overlay
        if (!ok && videoOverlay && !videoOverlay.classList.contains("hidden")) {
          const msg = videoOverlay.querySelector(".overlay-msg");
          if (msg && msg.textContent.includes("Connecting")) {
            msg.textContent = "Camera unavailable. It may be in use by another app or permissions are denied.";
            const spinner = videoOverlay.querySelector(".spinner");
            if (spinner) spinner.style.display = "none";
            
            // Add retry button if it doesn't exist
            const existing = videoOverlay.querySelector(".overlay-retry");
            if (!existing) {
              const btn = document.createElement("button");
              btn.className = "sc-btn sc-btn--sm overlay-retry";
              btn.style.marginTop = "12px";
              btn.textContent = "Retry Connection";
              btn.addEventListener("click", () => {
                showOverlay("Connecting to camera…");
                if (spinner) spinner.style.display = "block";
                btn.remove();
                if (video) video.src = mjpegUrl() + "?_=" + Date.now();
              });
              videoOverlay.appendChild(btn);
            }
          }
        }
      }
      if (modelStatus) {
        const label = data.model_demo_mode ? "DEMO" : data.model ? "OK" : "DOWN";
        const type = data.model_type ? String(data.model_type) : "unknown";
        const classes = data.label_count ? `${data.label_count} classes` : "unknown classes";
        const sequence = type === "temporal_landmark" && data.sequence_length
          ? `, ${data.sequence_length} frames`
          : "";
        modelStatus.textContent = `Model: ${label} (${type}, ${classes}${sequence})`;
        setDot(modelDot, data.model_demo_mode ? "warn" : data.model ? "ok" : "err");
      }
      updateFpsDisplay();
    } catch {
      if (cameraStatus) cameraStatus.textContent = "Camera: ERR";
      setDot(cameraDot, "err");
      if (!cameraNotificationSent) {
        notifyUser("camera", "Camera error", "SignConnect could not read from the selected camera.");
        cameraNotificationSent = true;
      }
    }
  }

  function updateFpsDisplay() {
    if (!fpsStatus) return;
    if (paused || fpsWindow.length === 0) {
      fpsStatus.textContent = "—";
      return;
    }
    const avg = fpsWindow.reduce((a, b) => a + b, 0) / fpsWindow.length;
    fpsStatus.textContent = `${Math.min(60, Math.max(1, Math.round(1000 / Math.max(16, avg))))}`;
  }

  /* ── Shared prediction UI updater (called by socket OR poll) ── */
  function updatePredictionUI(data) {
    if (paused) return;
    const display = data.smoothed_label || data.label;
    if (recognizedText) {
      const nextLabel = display || "—";
      if (renderState.label !== nextLabel) {
        recognizedText.textContent = nextLabel;
        renderState.label = nextLabel;
      }
    }
    updateConfidence(display ? data.confidence : 0);
    updateVideoPredictionOverlay(display, data.confidence);
    updateSentenceDisplay(data.sentence || "");
    updateProgressBar(data.current_run, data.stable_frames, data.is_cooling_down);
    updateTopCandidates(data.top_candidates || []);
    updateCoachingUI(data);
    updateSessionStats(data);
  }

  function updateTopCandidates(candidates) {
    if (!topkList) return;
    const key = JSON.stringify((Array.isArray(candidates) ? candidates : []).slice(0, 3));
    if (renderState.topCandidatesKey === key) return;
    renderState.topCandidatesKey = key;
    topkList.innerHTML = "";
    if (!Array.isArray(candidates) || candidates.length === 0) {
      const li = document.createElement("li");
      li.textContent = "No candidate predictions yet.";
      topkList.appendChild(li);
      return;
    }
    candidates.slice(0, 3).forEach((item, idx) => {
      const label = item && item.label ? String(item.label) : "Unknown";
      const score = Math.round((Number(item?.confidence) || 0) * 100);
      const li = document.createElement("li");
      li.innerHTML = `
        <span class="topk-label">${idx + 1}. ${escHtml(label)}</span>
        <span class="topk-score">${score}%</span>
      `;
      topkList.appendChild(li);
    });
  }

  /* ── HTTP fallback poll for /api/prediction ───────────────── */
  async function pollPrediction() {
    try {
      const res = await fetch("/api/prediction", { cache: "no-store" });
      const data = await res.json();
      updatePredictionUI(data);
    } catch { /* ignore */ }
  }

  /* ── Sentence display ─────────────────────────────────────── */
  function updateSentenceDisplay(sentence) {
    if (!sentenceDisplay) return;
    if (sentence) {
      if (renderState.sentence === sentence) return;
      sentenceDisplay.textContent = sentence;
      renderState.sentence = sentence;
      sentenceDisplay.classList.add("has-content");
      // Auto-speak: fire when the sentence has grown by at least one word.
      const wordCount = sentence.trim().split(/\s+/).length;
      if (autoSpeak && wordCount > _prevSentenceWordCount) {
        _autoSpeakSentence(sentence);
      }
      if (wordCount > _prevSentenceWordCount) {
        notifyUser("gesture", "New translation captured", sentence);
      }
      _prevSentenceWordCount = wordCount;
    } else {
      if (renderState.sentence === "") return;
      sentenceDisplay.textContent = "…";
      sentenceDisplay.classList.remove("has-content");
      renderState.sentence = "";
      _prevSentenceWordCount = 0;
    }
  }

  /* ── Progress bar ─────────────────────────────────────────── */
  function updateProgressBar(currentRun, stableFrames, coolingDown) {
    if (!commitProgress) return;

    if (coolingDown) {
      if (renderState.progressWidth !== "100%") {
        commitProgress.style.width = "100%";
        renderState.progressWidth = "100%";
      }
      commitProgress.classList.add("cooling");
      if (progressHint) progressHint.textContent = "Word committed! Lower hand to continue.";
      return;
    }

    commitProgress.classList.remove("cooling");

    const fraction = stableFrames > 0
      ? Math.min(1, (currentRun || 0) / stableFrames)
      : 0;
    const nextWidth = `${Math.round(fraction * 100)}%`;
    if (renderState.progressWidth !== nextWidth) {
      commitProgress.style.width = nextWidth;
      renderState.progressWidth = nextWidth;
    }

    if (progressHint) {
      if (fraction === 0) {
        progressHint.textContent = "Hold a gesture steadily to build a word";
      } else if (fraction < 1) {
        const remaining = stableFrames - (currentRun || 0);
        progressHint.textContent = `Hold… ${remaining} frame${remaining === 1 ? "" : "s"} to commit`;
      } else {
        progressHint.textContent = "Committing…";
      }
    }
  }

  function formatConfidencePercent(raw, fraction = true) {
    const baseValue = fraction ? Number(raw || 0) * 100 : Number(raw || 0);
    const rounded = Math.max(0, Math.min(100, Math.round(baseValue * 100) / 100));
    return {
      numeric: rounded,
      text: `${rounded.toFixed(2)}%`,
    };
  }

  /* ── Confidence badge ─────────────────────────────────────── */
  function updateConfidence(raw) {
    const formatted = formatConfidencePercent(raw, true);
    const pct = formatted.numeric;
    if (pct === renderState.confidencePct) return;
    renderState.confidencePct = pct;

    // Update old badge if it exists (for backward compatibility)
    if (confidenceBadge) {
      confidenceBadge.textContent = `${pct}%`;
      confidenceBadge.className =
        "badge " + (pct > 85 ? "high" : pct > 70 ? "mid" : "low");
    }

    // Update new confidence circle value if it exists
    const confidenceValue = document.getElementById("confidence-value");
    if (confidenceValue) {
      confidenceValue.textContent = formatted.text;
    }
    if (confidenceFill) {
      confidenceFill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }
  }

  function updateVideoPredictionOverlay(label, confidence) {
    if (!predictionOverlay || !predictionOverlayLabel || !predictionOverlayConfidence) return;
    const cleanLabel = label && label !== "Unknown" ? String(label).toUpperCase() : "—";
    const confText = formatConfidencePercent(confidence, true).text;
    if (cleanLabel === "—") {
      predictionOverlay.classList.add("sc-prediction-overlay--hidden");
      return;
    }
    if (renderState.overlayLabel !== cleanLabel) {
      predictionOverlayLabel.textContent = cleanLabel;
      renderState.overlayLabel = cleanLabel;
    }
    if (renderState.overlayConfText !== confText) {
      predictionOverlayConfidence.textContent = confText;
      renderState.overlayConfText = confText;
    }
    predictionOverlay.classList.remove("sc-prediction-overlay--hidden");
  }

  /* ── Language selector ────────────────────────────────────── */
  function getSelectedLang() {
    const lang = langSelect
      ? langSelect.value
      : (settingsState.language || localStorage.getItem("sc_lang") || localStorage.getItem(i18n.STORAGE_KEY) || "en");
    return SUPPORTED_UI_LANGS.has(lang) ? lang : "en";
  }

  function initLanguageSelector() {
    const normalizeLang = (value) => (SUPPORTED_UI_LANGS.has(value) ? value : "en");
    // Use settings state or fallback to localStorage / i18n
    const saved = normalizeLang(settingsState.language || localStorage.getItem("sc_lang") || localStorage.getItem(i18n.STORAGE_KEY) || "en");
    updateSetting("language", saved);
    localStorage.setItem("sc_lang", saved);

    if (!langSelect) {
      if (typeof i18n !== "undefined" && i18n.setLanguage) {
        i18n.setLanguage(saved);
      }
      return;
    }
    langSelect.value = saved;

    // Sync settings language select when main language select changes
    langSelect.addEventListener("change", () => {
      const newLang = normalizeLang(langSelect.value);
      langSelect.value = newLang;
      updateSetting("language", newLang);
      localStorage.setItem("sc_lang", newLang);
      if (settingsLangSelect) settingsLangSelect.value = newLang;
      // Update i18n
      if (typeof i18n !== "undefined" && i18n.setLanguage) {
        i18n.setLanguage(newLang);
      }
    });

    // Sync settings language select with main select
    if (settingsLangSelect) {
      settingsLangSelect.addEventListener("change", () => {
        const newLang = normalizeLang(settingsLangSelect.value);
        settingsLangSelect.value = newLang;
        updateSetting("language", newLang);
        localStorage.setItem("sc_lang", newLang);
        if (langSelect) langSelect.value = newLang;
        // Update i18n
        if (typeof i18n !== "undefined" && i18n.setLanguage) {
          i18n.setLanguage(newLang);
        }
      });
      settingsLangSelect.value = saved;
    }

    // Initialize i18n with the saved language
    if (typeof i18n !== "undefined" && i18n.setLanguage) {
      i18n.setLanguage(saved);
    }

    // Listen for language changes from i18n module
    window.addEventListener("languageChanged", (event) => {
      const newLang = normalizeLang(event.detail.lang);
      if (langSelect) langSelect.value = newLang;
      if (settingsLangSelect) settingsLangSelect.value = newLang;
      updateSetting("language", newLang);
      localStorage.setItem("sc_lang", newLang);
    });
  }

  /* ── Confidence threshold slider ──────────────────────────── */
  function initThresholdSlider() {
    if (!thresholdSlider) return;

    // Load current server value or from settings
    fetch("/api/config", { cache: "no-store" })
      .then((r) => r.json())
      .then((data) => {
        const pct = settingsState.threshold || Math.round((data.confidence_threshold || 0.75) * 100);
        thresholdSlider.value = pct;
        if (thresholdVal) thresholdVal.textContent = `${pct}%`;
        updateSetting("threshold", pct);
      })
      .catch(() => { });

    let debounce = null;
    thresholdSlider.addEventListener("input", () => {
      const pct = parseInt(thresholdSlider.value, 10);
      if (thresholdVal) thresholdVal.textContent = `${pct}%`;
      updateSetting("threshold", pct);
      if (settingsThresholdSlider) settingsThresholdSlider.value = pct;
      if (settingsThresholdVal) settingsThresholdVal.textContent = `${pct}%`;

      clearTimeout(debounce);
      debounce = setTimeout(() => {
        fetch("/api/config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confidence_threshold: pct / 100 }),
        }).catch(() => { });
      }, 350);
    });
  }

  function setTrainingMode(enabled) {
    if (topkPanel) topkPanel.classList.toggle("hidden", !enabled);
    if (trainingModeToggle) trainingModeToggle.checked = !!enabled;
    updateSetting("training", enabled);
    localStorage.setItem("sc_training_mode", enabled ? "1" : "0");
    if (settingsTrainingToggle) settingsTrainingToggle.checked = enabled;
  }

  function initTrainingMode() {
    if (!trainingModeToggle && !topkPanel) return;
    const saved = settingsState.training !== undefined
      ? settingsState.training
      : localStorage.getItem("sc_training_mode");
    // Default to OFF for new users (was incorrectly defaulting to true)
    const enabled = saved === null || saved === undefined ? false : (saved === "1" || saved === true);
    setTrainingMode(enabled);
    if (trainingModeToggle) {
      trainingModeToggle.addEventListener("change", () => {
        setTrainingMode(trainingModeToggle.checked);
      });
    }
  }

  /* ── Speak ────────────────────────────────────────────────── */
  async function speakText() {
    /* Prefer the full sentence; fall back to current gesture label */
    const sentence =
      sentenceDisplay && sentenceDisplay.classList.contains("has-content")
        ? sentenceDisplay.textContent.trim()
        : null;
    const text =
      sentence || (recognizedText ? recognizedText.textContent.trim() : "");

    if (!text || text === "—" || text === "…") return;

    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: getSelectedLang() }),
      });
      if (!res.ok) return;
      const data = await res.json();
      playAudioUrl(data.audio_url);
      refreshHistorySidebar();
    } catch { /* ignore */ }
  }

  /* ── Delete last word ─────────────────────────────────────── */
  async function deleteLastWord() {
    try {
      const res = await fetch("/api/sentence/delete", { method: "POST" });
      const data = await res.json();
      updateSentenceDisplay(data.sentence || "");
    } catch { /* ignore */ }
  }

  /* ── Clear sentence ───────────────────────────────────────── */
  async function clearSentence() {
    try {
      await fetch("/api/sentence/clear", { method: "POST" });
    } catch { /* ignore */ }
    updateSentenceDisplay("");
    updateProgressBar(0, 15, false);
    resetSessionStats();
  }

  /* ── Copy sentence ────────────────────────────────────────── */
  async function copySentence() {
    const text = sentenceDisplay?.textContent || "";
    if (!text || text === "…") {
      return; // Nothing to copy
    }
    try {
      await navigator.clipboard.writeText(text);
      // Optional: Show a brief feedback
      if (copyBtn) {
        const originalText = copyBtn.textContent;
        copyBtn.textContent = "✓ Copied!";
        setTimeout(() => {
          copyBtn.textContent = originalText;
        }, 2000);
      }
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  }

  /* ── Clear history (history page) ────────────────────────── */
  async function clearHistory() {
    try {
      const response = await fetch("/api/history", {
        method: "DELETE",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
        body: new URLSearchParams({ csrf_token: getCsrfToken() }).toString(),
      });
      if (!response.ok) {
        throw new Error(`Failed with status ${response.status}`);
      }
      const payload = await response.json().catch(() => ({ deleted: 0 }));
      await refreshHistoryPage();
      showToast(`History cleared (${payload.deleted || 0} entries removed).`, "success");
      notifyUser("system", "History cleared", `${payload.deleted || 0} entries removed`);
      return;
    } catch { /* network error */ }
    showToast("Failed to clear history.", "error");
    notifyUser("system", "History clear failed", "Could not remove history entries.");
  }

  async function downloadHistoryCsv() {
    if (!downloadHistoryBtn) return;
    const initialText = downloadHistoryBtn.textContent;
    downloadHistoryBtn.disabled = true;
    downloadHistoryBtn.textContent = "⏳ Preparing…";
    try {
      const response = await fetch("/api/export_history", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`Failed with status ${response.status}`);
      }
      const blob = await response.blob();
      const objectUrl = URL.createObjectURL(blob);
      const disposition = response.headers.get("Content-Disposition") || "";
      const nameMatch = disposition.match(/filename=([^;]+)/i);
      const filename = (nameMatch ? nameMatch[1] : "signconnect_history.csv").replace(/"/g, "");
      const link = document.createElement("a");
      link.href = objectUrl;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(objectUrl);
      showToast("History CSV downloaded.", "success");
    } catch {
      showToast("Failed to download CSV.", "error");
    } finally {
      downloadHistoryBtn.disabled = false;
      downloadHistoryBtn.textContent = initialText || "⬇ Download History CSV";
    }
  }

  function setUploadStatus(message, isError = false) {
    if (!uploadVideoStatus) return;
    uploadVideoStatus.textContent = message || "";
    uploadVideoStatus.style.color = isError ? "var(--color-danger, #ef4444)" : "var(--text-secondary)";
  }

  function resetUploadProgress() {
    if (!uploadVideoProgress) return;
    uploadVideoProgress.value = 0;
    uploadVideoProgress.style.display = "none";
  }

  function uploadVideoFile(file) {
    if (!file) return;
    if (file.type && file.type !== "video/mp4") {
      setUploadStatus("Please upload an MP4 video file.", true);
      return;
    }
    if (!/\.mp4$/i.test(file.name || "")) {
      setUploadStatus("Please select an MP4 file.", true);
      return;
    }

    pauseStream();
    showOverlay("Processing uploaded video…");
    setUploadStatus("Uploading video for analysis...");
    if (uploadVideoBtn) uploadVideoBtn.disabled = true;
    if (pauseBtn) pauseBtn.disabled = true;
    if (uploadVideoProgress) {
      uploadVideoProgress.style.display = "block";
      uploadVideoProgress.value = 0;
    }

    const formData = new FormData();
    formData.append("video", file);

    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/upload_video");

    xhr.upload.onprogress = (event) => {
      if (!uploadVideoProgress || !event.lengthComputable) return;
      if (event.total === 0) return;
      const pct = Math.max(0, Math.min(100, Math.round((event.loaded / event.total) * 100)));
      uploadVideoProgress.value = pct;
      setUploadStatus(`Uploading... ${pct}%`);
    };

    xhr.onload = () => {
      let payload = {};
      try { payload = JSON.parse(xhr.responseText || "{}"); } catch { }

      if (xhr.status !== 200) {
        setUploadStatus(payload.error || "Video upload failed.", true);
        showOverlay("Upload failed");
        if (uploadVideoBtn) uploadVideoBtn.disabled = false;
        if (pauseBtn) pauseBtn.disabled = false;
        resetUploadProgress();
        return;
      }

      const text = String(payload.translation_text || "").trim();
      const topGesture = String(payload.top_gesture || "");
      const avg = Number(payload.average_confidence || 0);

      if (recognizedText) recognizedText.textContent = topGesture || "—";
      updateConfidence(avg);
      updateSentenceDisplay(text);
      updateProgressBar(0, 15, false);

      const summary = text
        ? `Video processed (${payload.frames_processed || 0} frames). Translation: ${text}`
        : `Video processed (${payload.frames_processed || 0} frames). No strong gesture detected.`;
      setUploadStatus(summary, false);
      showOverlay("Upload complete — press Resume to return to live camera");
      if (uploadVideoBtn) uploadVideoBtn.disabled = false;
      if (pauseBtn) pauseBtn.disabled = false;
      resetUploadProgress();
    };

    xhr.onerror = () => {
      setUploadStatus("Network error while uploading video.", true);
      showOverlay("Upload failed");
      if (uploadVideoBtn) uploadVideoBtn.disabled = false;
      if (pauseBtn) pauseBtn.disabled = false;
      resetUploadProgress();
    };

    xhr.send(formData);
  }

  /* ── History (translator sidebar) ────────────────────────── */
  async function refreshHistorySidebar() {
    if (!historyList) return;
    try {
      const res = await fetch("/api/history", { cache: "no-store" });
      const data = await res.json();
      historyList.innerHTML = "";
      if (data.length === 0) {
        const li = document.createElement("li");
        li.textContent = "No translations yet.";
        historyList.appendChild(li);
        return;
      }
      data.slice(0, 10).forEach((item) => {
        const li = document.createElement("li");
        li.textContent = `${item.gesture_label} · ${item.created_at ? item.created_at.slice(0, 16) : ""
          }`;
        historyList.appendChild(li);
      });
      historyList.scrollTop = historyList.scrollHeight;
    } catch { /* ignore */ }
  }

  /* ── History page (full table) ───────────────────────────── */
  async function refreshHistoryPage() {
    const tbody = document.getElementById("history-tbody");
    if (!tbody) return;
    try {
      const res = await fetch("/api/history", { cache: "no-store" });
      const data = await res.json();
      tbody.innerHTML = "";
      if (data.length === 0) {
        tbody.innerHTML =
          '<tr><td colspan="4" class="sc-empty-state"><p>No translation history yet.</p></td></tr>';
        updateHistorySummary(data);
        return;
      }
      data.forEach((item) => {
        const tr = document.createElement("tr");
        const audio = item.audio_path
          ? `<audio src="${escHtml(item.audio_path)}" controls preload="none" class="sc-audio"></audio>`
          : "—";
        const confidenceText = item.confidence != null
          ? formatConfidencePercent(item.confidence, true).text
          : "—";
        const relative = formatRelativeTime(item.created_at);
        tr.innerHTML = `
          <td><span class="sc-gesture-tag">${escHtml(item.gesture_label)}</span></td>
          <td>${confidenceText}</td>
          <td>${audio}</td>
          <td><span class="sc-muted">${escHtml(relative)}</span></td>
        `;
        tbody.appendChild(tr);
      });
      updateHistorySummary(data);
    } catch { /* ignore */ }
  }

  function formatRelativeTime(rawTimestamp) {
    if (!rawTimestamp) return "—";
    try {
      const date = new Date(String(rawTimestamp).replace(" ", "T") + "Z");
      const diffSeconds = Math.floor((Date.now() - date.getTime()) / 1000);
      if (diffSeconds < 60) return "Just now";
      if (diffSeconds < 3600) return `${Math.floor(diffSeconds / 60)}m ago`;
      if (diffSeconds < 86400) return `${Math.floor(diffSeconds / 3600)}h ago`;
      return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
    } catch {
      return String(rawTimestamp);
    }
  }

  function updateHistorySummary(rows) {
    const cardValues = document.querySelectorAll(".sc-history-sidebar .sc-stat-mini-val");
    if (!cardValues || cardValues.length < 3) return;
    const total = rows.length;
    const withAudio = rows.filter((row) => Boolean(row.audio_path || row.audio_file)).length;
    const confRows = rows.filter((row) => row.confidence != null);
    const avgConf = confRows.length
      ? (confRows.reduce((sum, row) => sum + Number(row.confidence || 0), 0) / confRows.length) * 100
      : 0;
    cardValues[0].textContent = String(total);
    cardValues[1].textContent = formatConfidencePercent(avgConf, false).text;
    cardValues[2].textContent = String(withAudio);
    const badge = document.querySelector(".sc-history-main .sc-badge");
    if (badge) badge.textContent = `${total} entries`;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
  }

  async function applyPreferredCameraFromSettings() {
    const raw = localStorage.getItem("sc_cameraIndex");
    const preferred = Number.parseInt(raw || "1", 10);
    if (!Number.isInteger(preferred) || preferred < 0 || preferred > 10) return;
    try {
      await fetch("/api/camera", {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8" },
        body: new URLSearchParams({ camera_index: String(preferred), csrf_token: getCsrfToken() }).toString(),
      });
    } catch {
      // non-fatal; stream startup fallback still works
    }
  }

  function showToast(message, type = "success") {
    if (!message) return;
    let toast = document.getElementById("sc-global-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.id = "sc-global-toast";
      toast.className = "sc-toast";
      toast.setAttribute("role", "status");
      toast.setAttribute("aria-live", "polite");
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.className = `sc-toast sc-toast--show ${type === "error" ? "sc-toast--error" : "sc-toast--success"}`;
    clearTimeout(showToast._timer);
    showToast._timer = setTimeout(() => {
      toast.classList.remove("sc-toast--show");
    }, 2500);
  }

  function getBooleanPref(key, fallback = false) {
    try {
      const raw = localStorage.getItem(`sc_${key}`);
      if (raw === null) return fallback;
      return raw === "true";
    } catch {
      return fallback;
    }
  }

  function notificationsEnabled(kind) {
    if (kind === "gesture") return getBooleanPref("gestureNotif", true);
    if (kind === "camera") return getBooleanPref("cameraNotif", true);
    return true;
  }

  function notifyUser(kind, title, body) {
    if (!notificationsEnabled(kind)) return;
    if (!("Notification" in window)) return;
    try {
      if (Notification.permission === "granted") {
        new Notification(title, { body, icon: "/static/icons/icon-192.png", silent: false });
      } else if (Notification.permission === "default") {
        Notification.requestPermission().then((permission) => {
          if (permission === "granted") {
            new Notification(title, { body, icon: "/static/icons/icon-192.png", silent: false });
          }
        }).catch(() => { });
      }
    } catch (error) {
      console.warn("Notification delivery failed:", error);
    }
  }

  /** Strip non-word characters so a value is safe as a CSS class name. */
  function safeClass(str) {
    return String(str).replace(/[^a-zA-Z0-9_-]/g, "");
  }

  /* ── Camera frame polling ─────────────────────────────────── */
  async function tickFrame() {
    if (paused || frameInFlight || !video) return;
    frameInFlight = true;
    try {
      const res = await fetch(`${frameUrl()}?_=${Date.now()}`, {
        cache: "no-store",
      });
      if (!res.ok) {
        showOverlay(
          res.status === 404
            ? "Route not found — restart app.py"
            : "Camera error"
        );
        return;
      }
      const blob = await res.blob();
      if (!blob.type || !blob.type.startsWith("image/")) return;

      const url = URL.createObjectURL(blob);
      if (blobUrl) URL.revokeObjectURL(blobUrl);
      blobUrl = url;
      video.src = url;

      /* Per-frame FPS */
      const now = Date.now();
      if (prevFrameAt > 0) {
        fpsWindow.push(now - prevFrameAt);
        if (fpsWindow.length > 10) fpsWindow.shift();
      }
      prevFrameAt = now;
      hideOverlay();
    } catch { /* network hiccup */ } finally {
      frameInFlight = false;
    }
  }

  function startStream() {
    paused = false;
    cameraNotificationSent = false;
    renderState.overlayLabel = "";
    renderState.overlayConfText = "";
    if (streamTimer) clearInterval(streamTimer);
    streamTimer = null;

    if (video) {
      video.src = mjpegUrl() + "?_=" + Date.now();
      video.onload = () => {
        if (video.naturalWidth > 1) hideOverlay();
      };
      video.onerror = () => {
        showOverlay("Camera error — retrying…");
        setTimeout(() => { if (!paused && video) video.src = mjpegUrl() + "?_=" + Date.now(); }, 3000);
      };

      // Fallback: Some browsers (Chrome) don't fire onload for MJPEG streams
      // Clear any previous probe timer before creating a new one.
      if (checkVideoTimer) { clearInterval(checkVideoTimer); checkVideoTimer = null; }
      checkVideoTimer = setInterval(() => {
        if (paused || !video) {
          clearInterval(checkVideoTimer);
          checkVideoTimer = null;
          return;
        }
        if (video.naturalWidth > 1) { // >1 ensures it's not a 1x1 placeholder frame
          hideOverlay();
          clearInterval(checkVideoTimer);
          checkVideoTimer = null;
        }
      }, 500);
    }

    showOverlay("Connecting to camera…");
    if (startBtn) startBtn.disabled = true;
    if (pauseBtn) {
      pauseBtn.disabled = false;
      pauseBtn.innerHTML = ICON_PAUSE + ' Pause';
    }
    if (liveBadge) liveBadge.style.display = "";
    setDot(cameraDot, "pulsing");
    startSessionTimer();
    if (!socketConnected) startPredictionPoll();

    // ── Camera connection timeout (30 s) ──
    setTimeout(() => {
      if (!paused && videoOverlay && !videoOverlay.classList.contains("hidden")) {
        const msg = videoOverlay.querySelector(".overlay-msg");
        if (msg && msg.textContent.includes("Connecting")) {
          msg.textContent = "Camera failed to connect — check permissions.";
          if (!cameraNotificationSent) {
            notifyUser("camera", "Camera failed to connect", "Please confirm camera permission and selected source.");
            cameraNotificationSent = true;
          }
          // Add retry button dynamically
          const existing = videoOverlay.querySelector(".overlay-retry");
          if (!existing) {
            const btn = document.createElement("button");
            btn.className = "sc-btn sc-btn--sm overlay-retry";
            btn.style.marginTop = "12px";
            btn.textContent = "Retry";
            btn.addEventListener("click", () => {
              showOverlay("Connecting to camera…");
              if (video) video.src = mjpegUrl() + "?_=" + Date.now();
            });
            videoOverlay.appendChild(btn);
          }
        }
      }
    }, 30000);
  }

  function pauseStream() {
    paused = true;
    if (streamTimer) { clearInterval(streamTimer); streamTimer = null; }
    stopPredictionPoll();
    if (checkVideoTimer) { clearInterval(checkVideoTimer); checkVideoTimer = null; }
    if (video) video.removeAttribute("src");
    if (blobUrl) { URL.revokeObjectURL(blobUrl); blobUrl = null; }
    prevFrameAt = 0;
    fpsWindow = [];
    showOverlay("Stream paused");
    if (startBtn) startBtn.disabled = false;
    if (pauseBtn) {
      pauseBtn.disabled = false;
      pauseBtn.innerHTML = ICON_PLAY + ' Resume';
    }
    if (liveBadge) liveBadge.style.display = "none";
    updateFpsDisplay();
    resetCoachingState();
    if (predictionOverlay) predictionOverlay.classList.add("sc-prediction-overlay--hidden");
    if (sessionStats.durationTimer) clearInterval(sessionStats.durationTimer);
  }

  /* ── Bind buttons ─────────────────────────────────────────── */
  function bindButtons() {
    if (startBtn) startBtn.addEventListener("click", startStream);
    if (pauseBtn) {
      pauseBtn.addEventListener("click", () => paused ? startStream() : pauseStream());
    }
    if (speakBtn) speakBtn.addEventListener("click", speakText);
    if (autoSpeakBtn) autoSpeakBtn.addEventListener("click", toggleAutoSpeak);
    if (copyBtn) copyBtn.addEventListener("click", copySentence);
    if (deleteWordBtn) deleteWordBtn.addEventListener("click", deleteLastWord);
    if (clearBtn) clearBtn.addEventListener("click", clearSentence);
    if (refreshHistBtn) refreshHistBtn.addEventListener("click", refreshHistoryPage);
    if (clearHistBtn) clearHistBtn.addEventListener("click", clearHistory);
    if (clearHistoryPageBtn) clearHistoryPageBtn.addEventListener("click", () => {
      if (!confirm("Clear all translation history? This cannot be undone.")) return;
      clearHistory();
    });
    if (downloadHistoryBtn) downloadHistoryBtn.addEventListener("click", downloadHistoryCsv);
    if (uploadVideoBtn && uploadVideoInput) {
      uploadVideoBtn.addEventListener("click", () => uploadVideoInput.click());
      uploadVideoInput.addEventListener("change", () => {
        const file = uploadVideoInput.files && uploadVideoInput.files[0];
        uploadVideoFile(file);
        uploadVideoInput.value = "";
      });
    }

    // Practice mode listeners
    if (practiceBtn) practiceBtn.addEventListener("click", togglePracticeMode);
    if (practiceCloseBtn) practiceCloseBtn.addEventListener("click", () => togglePracticeMode());
    if (practiceBackBtn) practiceBackBtn.addEventListener("click", backToGestureList);
    if (practiceSearchInput) {
      practiceSearchInput.addEventListener("input", (e) => {
        filterGestures(e.target.value);
      });
    }

    // Settings mode listeners
    if (settingsBtn) settingsBtn.addEventListener("click", toggleSettingsModal);
    if (settingsCloseBtn) settingsCloseBtn.addEventListener("click", closeSettingsModal);
    if (settingsOverlay) settingsOverlay.addEventListener("click", closeSettingsModal);
    if (settingsSaveBtn) settingsSaveBtn.addEventListener("click", () => {
      // Gather all settings
      if (settingsCameraSelect) updateSetting("camera", settingsCameraSelect.value);
      if (settingsThresholdSlider) updateSetting("threshold", parseInt(settingsThresholdSlider.value));
      if (settingsLangSelect) updateSetting("language", settingsLangSelect.value);
      if (settingsTrainingToggle) updateSetting("training", settingsTrainingToggle.checked);
      if (settingsAudioToggle) updateSetting("audioEnabled", settingsAudioToggle.checked);
      if (settingsThemeToggle) updateSetting("theme", settingsThemeToggle.checked ? "light" : "dark");
      saveSettings();
      closeSettingsModal();
    });
    if (settingsResetBtn) settingsResetBtn.addEventListener("click", resetSettings);

    // Settings input listeners for live updates
    if (settingsThresholdSlider) {
      settingsThresholdSlider.addEventListener("input", (e) => {
        if (settingsThresholdVal) {
          settingsThresholdVal.textContent = e.target.value + "%";
        }
      });
    }

    if (settingsThemeToggle) {
      settingsThemeToggle.addEventListener("change", (e) => {
        if (settingsThemeLabel) {
          settingsThemeLabel.textContent = e.target.checked ? "Dark Mode" : "Light Mode";
        }
      });
    }
  }

  /* ── Mark active nav link ─────────────────────────────────── */
  function markActiveNav() {
    document.querySelectorAll(".site-header nav a").forEach((a) => {
      if (a.href === location.href) a.classList.add("active");
    });
  }

  /* ── Boot ─────────────────────────────────────────────────── */
  loadSettings();
  initTheme();
  initLanguageSelector();
  initThresholdSlider();
  initTrainingMode();
  bindButtons();
  _applyAutoSpeakButton();  // reflect persisted auto-speak state on load
  markActiveNav();
  loadGestureReferences();

  /* Translator page */
  if (video) {
    applyPreferredCameraFromSettings().finally(() => {
      startStream();
      initSocket();           // WebSocket push; HTTP poll used only as fallback
      refreshHistorySidebar().catch(() => { });
      updateConfidence(0);
      updateProgressBar(0, 15, false);
    });
  }

  /* History page */
  if (document.getElementById("history-tbody")) {
    refreshHistoryPage().catch(() => { });
  }

  /* All pages — status poll only on translator where it's useful */
  if (video) {
    statusPollTimer = setInterval(pollStatus, STATUS_MS);
    pollStatus();
  }
  fpsPollTimer = setInterval(updateFpsDisplay, 1000);
})();
