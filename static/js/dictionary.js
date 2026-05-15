(function () {
  "use strict";

  const grid = document.getElementById("dict-grid");
  const searchInput = document.getElementById("dict-search");
  const meta = document.getElementById("dict-search-meta");
  const empty = document.getElementById("dict-no-results");
  const modal = document.getElementById("gesture-modal");
  const modalBox = modal?.querySelector(".sc-gesture-modal-box");
  const closeBtn = document.getElementById("gesture-modal-close");
  const titleEl = document.getElementById("gesture-modal-title");
  const descEl = document.getElementById("gesture-modal-desc");
  const loadingEl = document.getElementById("gesture-modal-loading");
  const previewImage = document.getElementById("gesture-preview-image");
  const fallbackEl = document.getElementById("gesture-preview-fallback");

  if (!grid || !searchInput || !modal || !modalBox || !titleEl || !descEl || !loadingEl || !previewImage || !fallbackEl) {
    return;
  }

  const cards = Array.from(grid.querySelectorAll(".sc-dict-card")).map((card) => ({
    element: card,
    label: String(card.dataset.label || "").toLowerCase(),
    displayLabel: String(card.dataset.displayLabel || "").trim(),
    landmarkKey: String(card.dataset.landmarkKey || "").trim(),
  }));
  const state = {
    total: cards.length,
    visible: cards.length,
    query: "",
    debounceTimer: null,
    assetToken: 0,
    isOpen: false,
    lastFocusedCard: null,
  };
  const imageAvailability = new Map();

  function landmarkImageUrl(key) {
    return `/static/data/landmarks/${encodeURIComponent(key)}.png`;
  }

  function updateMeta(visibleCount) {
    state.visible = visibleCount;
    if (meta) {
      meta.textContent = `Showing ${visibleCount} of ${state.total} signs`;
    }
    if (empty) {
      empty.hidden = visibleCount !== 0;
    }
  }

  function applySearch(query) {
    const normalized = query.trim().toLowerCase();
    if (state.query === normalized) return;
    state.query = normalized;

    let visibleCount = 0;
    for (const card of cards) {
      const matches = !normalized || card.label.includes(normalized);
      card.element.classList.toggle("sc-dict-card--hidden", !matches);
      if (matches) visibleCount += 1;
    }
    updateMeta(visibleCount);
  }

  function debounceSearch() {
    clearTimeout(state.debounceTimer);
    state.debounceTimer = window.setTimeout(() => {
      applySearch(searchInput.value);
    }, 120);
  }

  function showFallback() {
    loadingEl.hidden = true;
    previewImage.hidden = true;
    fallbackEl.hidden = false;
    previewImage.removeAttribute("src");
    previewImage.alt = "";
  }

  function showImage(src, altText) {
    loadingEl.hidden = true;
    fallbackEl.hidden = true;
    previewImage.hidden = false;
    previewImage.src = src;
    previewImage.alt = altText;
  }

  function startLoading(label) {
    loadingEl.hidden = false;
    fallbackEl.hidden = true;
    previewImage.hidden = true;
    previewImage.removeAttribute("src");
    previewImage.alt = "";
    descEl.textContent = `Optimized landmark reference for ${label}. Compare finger pose, wrist angle, and hand orientation without replaying live rendering.`;
  }

  function openModal(card) {
    const displayLabel = card.displayLabel || card.label;
    titleEl.textContent = displayLabel;
    startLoading(displayLabel);
    modal.setAttribute("aria-hidden", "false");
    modal.classList.add("sc-gesture-modal--open");
    document.documentElement.classList.add("sc-modal-open");
    document.body.classList.add("sc-modal-open");
    state.isOpen = true;
    state.lastFocusedCard = card.element;
    window.requestAnimationFrame(() => modalBox.focus());

    const key = card.landmarkKey;
    const token = ++state.assetToken;
    if (!key) {
      showFallback();
      return;
    }

    if (imageAvailability.get(key) === false) {
      showFallback();
      return;
    }

    const image = new Image();
    image.decoding = "async";
    image.loading = "eager";
    image.onload = () => {
      if (token !== state.assetToken) return;
      imageAvailability.set(key, true);
      showImage(landmarkImageUrl(key), `${displayLabel} landmark preview`);
    };
    image.onerror = () => {
      if (token !== state.assetToken) return;
      imageAvailability.set(key, false);
      showFallback();
    };
    image.src = landmarkImageUrl(key);
  }

  function closeModal() {
    if (!state.isOpen) return;
    state.isOpen = false;
    state.assetToken += 1;
    modal.classList.remove("sc-gesture-modal--open");
    modal.setAttribute("aria-hidden", "true");
    document.documentElement.classList.remove("sc-modal-open");
    document.body.classList.remove("sc-modal-open");
    if (state.lastFocusedCard instanceof HTMLElement) {
      state.lastFocusedCard.focus();
    }
  }

  searchInput.addEventListener("input", debounceSearch, { passive: true });

  grid.addEventListener("click", (event) => {
    const card = event.target instanceof Element ? event.target.closest(".sc-dict-card") : null;
    if (!(card instanceof HTMLElement)) return;
    const match = cards.find((item) => item.element === card);
    if (match) openModal(match);
  });

  closeBtn?.addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.hasAttribute("data-modal-close")) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && state.isOpen) closeModal();
  });

  updateMeta(cards.length);
})();
