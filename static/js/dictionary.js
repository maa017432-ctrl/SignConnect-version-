(function () {
  "use strict";

  const grid = document.getElementById("dict-grid");
  const searchInput = document.getElementById("dict-search");
  const meta = document.getElementById("dict-search-meta");
  const empty = document.getElementById("dict-no-results");

  if (!grid || !searchInput) {
    return;
  }

  const cards = Array.from(grid.querySelectorAll(".sc-dict-card")).map((card) => ({
    element: card,
    label: String(card.dataset.label || "").toLowerCase(),
  }));
  const state = {
    total: cards.length,
    visible: cards.length,
    query: "",
    debounceTimer: null,
  };

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

  searchInput.addEventListener("input", debounceSearch, { passive: true });

  updateMeta(cards.length);
})();
