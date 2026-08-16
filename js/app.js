/* WeatherVision — frontend application logic (v2).
 * Renders the payload produced by js/weather.js (same shape as the Flask API).
 * Unit switches are applied client-side from the raw metric snapshot, so they
 * never require a network round-trip.
 */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#39;");

  const storage = (() => {
    try {
      localStorage.setItem("__wv__", "1");
      localStorage.removeItem("__wv__");
      return { get: (k) => localStorage.getItem(k), set: (k, v) => localStorage.setItem(k, v) };
    } catch (_e) {
      const mem = {};
      return { get: (k) => mem[k] ?? null, set: (k, v) => { mem[k] = String(v); } };
    }
  })();

  const NA = "Not available";
  const SAMPLE_PLACES = ["Lahore, Pakistan", "London, United Kingdom", "Tokyo, Japan", "New York, USA"];

  const state = {
    query: "",
    units: storage.get("wv-units") || "metric",
    payload: null,        // last serialized payload (display units)
    raw: null,            // last raw metric snapshot (from payload._raw)
    loading: false,
    chartTab: "temp",
    suggestionIndex: -1,
  };

  // ------------------------------------------------------------------
  // Theme
  // ------------------------------------------------------------------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    storage.set("wv-theme", theme);
  }
  function currentTheme() {
    return storage.get("wv-theme")
      || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  }

  // ------------------------------------------------------------------
  // Units — re-serialize the raw snapshot, no network
  // ------------------------------------------------------------------
  function setUnits(units) {
    state.units = units;
    storage.set("wv-units", units);
    document.querySelectorAll("#unit-toggle button").forEach((b) => {
      b.classList.toggle("active", b.dataset.units === units);
    });
    if (state.raw) {
      const payload = WV.serializePayload(state.raw, units);
      state.payload = payload;
      render(payload);
    }
  }

  // ------------------------------------------------------------------
  // Time helpers
  // ------------------------------------------------------------------
  function timeAgo(iso) {
    if (!iso) return "";
    const then = new Date(iso).getTime();
    if (Number.isNaN(then)) return "";
    const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
    if (seconds < 60) return "Updated moments ago";
    if (seconds < 3600) return `Updated ${Math.floor(seconds / 60)} min ago`;
    if (seconds < 86400) return `Updated ${Math.floor(seconds / 3600)} h ago`;
    return `Updated ${Math.floor(seconds / 86400)} d ago`;
  }
  function localTimeNow(tz) {
    try {
      return new Intl.DateTimeFormat("en-GB", {
        timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
      }).format(new Date());
    } catch (_e) {
      return new Date().toTimeString().slice(0, 5);
    }
  }

  // ------------------------------------------------------------------
  // State UI helpers
  // ------------------------------------------------------------------
  function showState(which) {
    ["empty", "loading", "error"].forEach((k) => $("state-" + k).hidden = k !== which);
    $("state").hidden = false;
    $("dashboard").hidden = true;
  }
  function showDashboard() {
    $("state").hidden = true;
    $("dashboard").hidden = false;
  }
  function showError(title, message) {
    $("error-title").textContent = title;
    $("error-message").textContent = message;
    $("use-cached-btn").hidden = !WV.lastPayload();
    showState("error");
  }

  function setDemoNotice(on) {
    $("demo-notice").hidden = !on;
  }

  // ------------------------------------------------------------------
  // Fetching
  // ------------------------------------------------------------------
  async function loadWeather(query) {
    if (state.loading) return;
    state.query = query;
    state.loading = true;
    showState("loading");
    try {
      const payload = await WV.weather(query, state.units);
      state.payload = payload;
      state.raw = payload._raw;
      try { WV.saveLastPayload(payload); } catch (_e) { /* ignore */ }
      setDemoNotice(payload.meta.demo);
      render(payload);
      showDashboard();
      refreshSaved();
    } catch (err) {
      showError("Weather data unavailable", err.message || "Please try again.");
    } finally {
      state.loading = false;
    }
  }

  /** Error recovery: render the last successfully fetched snapshot as stale. */
  function useLastAvailable() {
    const payload = WV.lastPayload();
    if (!payload) return;
    state.payload = payload;
    state.raw = null; // re-fetch required for unit switches
    payload.meta.stale = true;
    render(payload);
    showDashboard();
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------
  function render(data) {
    const c = data.current;
    const loc = data.location;

    $("loc-name").textContent = loc.display_name;
    $("loc-local-time").textContent = "Local time " + loc.local_time;
    $("updated-text").textContent = (data.meta.stale ? "Showing last available data · " : "") + timeAgo(data.meta.fetched_at);
    $("footer-updated").textContent = timeAgo(data.meta.fetched_at);
    $("hero-icon").textContent = c.icon;
    $("hero-temp").textContent = c.temperature_display;
    $("hero-condition").textContent = c.condition;
    $("hero-feels").textContent = c.feels_like_display === NA
      ? "Feels like not available"
      : `Feels like ${c.feels_like_display}`;
    $("hero-summary").textContent = data.summary || "";
    setFavoritePin(data.meta.is_favorite);

    renderQuickFacts(data);
    renderInsights(data);
    renderScore(data);
    renderActivity(data);
    renderHourly(data);
    renderDaily(data);
    renderDetails(data);
    renderAirQuality(data);
    renderSun(data);
    renderAlerts(data);
    renderCharts(data);
  }

  function setFavoritePin(on) {
    $("favorite-btn").textContent = on ? "★" : "☆";
    $("favorite-btn").setAttribute("data-fav", on ? "1" : "0");
    $("favorite-btn").setAttribute("aria-label", on ? "Remove from favorites" : "Save to favorites");
  }

  function renderQuickFacts(data) {
    const c = data.current;
    const wind = c.wind_direction !== NA && c.wind_direction
      ? `${c.wind_display} · ${c.wind_direction}`
      : c.wind_display;
    $("quick-facts").innerHTML = [
      ["Humidity", c.humidity_display],
      ["Wind", wind],
      ["Visibility", c.visibility_display],
      ["Pressure", c.pressure_display],
    ].map(([label, value]) =>
      `<div class="fact"><dt>${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("");
  }

  function renderInsights(data) {
    const list = data.insights || [];
    if (!list.length) {
      $("insights").innerHTML = `<p class="muted">No significant conditions to highlight right now.</p>`;
      return;
    }
    $("insights").innerHTML = list.map((i) => `
      <div class="insight" style="--level-color:${esc(i.color)}">
        <span class="ic" aria-hidden="true">${i.icon}</span>
        <div>
          <strong>${esc(i.title)}</strong>
          <p>${esc(i.message)}</p>
        </div>
      </div>`).join("");
  }

  function scoreColor(score) {
    if (score >= 80) return "#22c55e";
    if (score >= 60) return "#84cc16";
    if (score >= 40) return "#f59e0b";
    if (score >= 20) return "#f97316";
    return "#ef4444";
  }

  function renderScore(data) {
    const s = data.score;
    if (!s) return;
    const total = s.total;
    $("score-total").textContent = total === null ? NA : `${total}/100`;
    $("score-total").style.color = total === null ? "var(--muted)" : s.color;
    $("score-grade").textContent = s.grade;
    $("score-grade").style.color = total === null ? "var(--muted)" : s.color;
    const pct = total === null ? 0 : Math.max(4, Math.min(100, total));
    $("gauge-arc").setAttribute("stroke", total === null ? "var(--border)" : s.color);
    $("gauge-arc").setAttribute("stroke-dasharray", `${(pct / 100) * 326}, 326`);
    if (s.available_factors < s.factor_count) {
      $("score-factor-note").textContent = s.note;
      $("score-factor-note").hidden = false;
    } else {
      $("score-factor-note").hidden = true;
    }
  }

  function renderActivity(data) {
    const a = data.activity;
    if (!a) return;
    $("activity-verdict-icon").textContent = a.verdict.icon;
    $("activity-verdict-text").textContent = a.verdict.text;
    $("activity-verdict-detail").textContent = a.verdict.detail;
    $("activities").innerHTML = (a.items || []).map((item) => {
      const color = scoreColor(item.score);
      return `
      <div class="activity" title="${esc(item.reasons.join(" · "))}">
        <div class="activity-head">
          <span class="nm">${item.icon} ${esc(item.name)}</span>
          <span class="activity-score-badge" style="--c:${color}">${item.score}</span>
        </div>
        <div class="activity-score"><div class="bar"><i style="width:${item.score}%;background:${color}"></i></div></div>
        <span class="activity-label" style="color:${color}">${esc(item.label)}</span>
      </div>`;
    }).join("");
  }

  function renderHourly(data) {
    $("hourly").innerHTML = (data.hourly || []).map((h, idx) => `
      <button type="button" class="hour" data-idx="${idx}" role="listitem"
              aria-label="${esc(h.condition)}, ${h.temperature_display}, ${h.precip_prob ?? NA}% rain">
        <span class="t">${esc(h.time)}${h.is_now ? ' <em class="now">now</em>' : ""}</span>
        <span class="ic" aria-hidden="true">${h.icon}</span>
        <span class="tmp">${esc(h.temperature_display)}</span>
        <span class="rain">${h.precip_prob === null || h.precip_prob === undefined ? NA : h.precip_prob + "%"}</span>
      </button>`).join("");
    $("hourly-detail").hidden = true;
    $("hourly-detail").innerHTML = "";
  }

  function showHourlyDetail(data, idx) {
    const h = (data.hourly || [])[idx];
    if (!h) return;
    const rows = [
      ["Condition", h.condition],
      ["Temperature", h.temperature_display],
      ["Feels like", h.feels_like_display],
      ["Rain chance", h.precip_prob === null || h.precip_prob === undefined ? NA : `${h.precip_prob}%`],
      ["Expected rain", h.precipitation_display],
      ["Wind", h.wind_direction && h.wind_direction !== NA ? `${h.wind_display} · ${h.wind_direction}` : h.wind_display],
      ["Visibility", h.visibility_display],
    ];
    $("hourly-detail").innerHTML = `
      <div class="hourly-detail-head">
        <strong>${esc(h.time)}${h.is_now ? " · now" : ""}</strong>
        <span class="muted">${esc(h.condition)}</span>
      </div>
      <dl class="detail-grid">
        ${rows.map(([k, v]) => `<div class="ditem"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("")}
      </dl>`;
    $("hourly-detail").hidden = false;
    $("hourly-detail").scrollIntoView({ block: "nearest" });
  }

  function renderDaily(data) {
    $("daily").innerHTML = (data.daily || []).map((d, idx) => {
      const today = idx === 0 ? '<span class="today-tag">Today</span>' : "";
      const precip = d.precip_prob === null || d.precip_prob === undefined
        ? NA : `${d.precip_prob}%`;
      return `
      <details class="day-row" data-idx="${idx}">
        <summary>
          <span class="d-day">${esc(d.day)}${today}</span>
          <span class="d-date">${esc(d.date)}</span>
          <span class="d-ic" aria-hidden="true">${d.icon}</span>
          <span class="d-cond">${esc(d.condition)}</span>
          <span class="d-temps"><b>${esc(d.high_display)}</b><span class="lo">${esc(d.low_display)}</span></span>
          <span class="d-chev" aria-hidden="true">⌄</span>
        </summary>
        <div class="day-body">
          <dl class="detail-grid">
            <div class="ditem"><dt>Condition</dt><dd>${esc(d.condition)}</dd></div>
            <div class="ditem"><dt>High / low</dt><dd>${esc(d.high_display)} / ${esc(d.low_display)}</dd></div>
            <div class="ditem"><dt>Feels like (max)</dt><dd>${esc(d.feels_like_max_display)}</dd></div>
            <div class="ditem"><dt>Rain chance</dt><dd>${esc(precip)}</dd></div>
            <div class="ditem"><dt>Expected rain</dt><dd>${esc(d.precipitation_sum_display)}</dd></div>
            <div class="ditem"><dt>UV index (max)</dt><dd>${esc(d.uv_display)}</dd></div>
            <div class="ditem"><dt>Wind (max)</dt><dd>${esc(d.wind_max_display)}</dd></div>
            <div class="ditem"><dt>Sunrise / sunset</dt><dd>${esc(d.sunrise)} / ${esc(d.sunset)}</dd></div>
          </dl>
        </div>
      </details>`;
    }).join("");
  }

  function renderDetails(data) {
    const c = data.current;
    const items = [
      ["Pressure", c.pressure_display],
      ["Dew point", c.dew_point_display],
      ["Cloud cover", c.cloud_cover_display],
      ["Wind direction", c.wind_direction],
      ["Wind gusts", c.wind_gusts_display],
      ["Rain (current)", c.precipitation_display],
      ["Rain chance", c.precipitation_probability_display],
      ["UV index", c.uv_display],
    ];
    $("details-grid").innerHTML = items.map(([k, v]) =>
      `<div class="ditem"><dt>${esc(k)}</dt><dd>${esc(v)}</dd></div>`).join("");
  }

  function renderAirQuality(data) {
    const aq = data.air_quality;
    const box = $("air-quality");
    if (!aq) {
      box.innerHTML = `<div class="aq-empty"><p class="muted">Air quality data is not available for this location.</p></div>`;
      return;
    }
    box.innerHTML = `
      <div class="aq-value">
        <span style="color:${aq.color}">${Math.round(aq.aqi)}</span>
        <small style="color:${aq.color}">${esc(aq.label)}</small>
      </div>
      <div class="aq-details">
        <div class="stat"><dt>PM2.5</dt><dd>${esc(aq.pm25_display)}</dd></div>
        <div class="stat"><dt>PM10</dt><dd>${esc(aq.pm10_display)}</dd></div>
        <p class="muted aq-note">${esc(aq.note)}</p>
      </div>`;
  }

  function renderSun(data) {
    $("sunrise").textContent = data.current.sunrise || NA;
    $("sunset").textContent = data.current.sunset || NA;
    $("vis-val").textContent = data.current.visibility_display;
  }

  function renderAlerts(data) {
    const box = $("alerts");
    const alerts = data.alerts || [];
    if (!alerts.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.innerHTML = alerts.map((a) => `
      <div class="alert" style="--alert-color:${esc(a.color)}" role="alert">
        <span class="a-icon" aria-hidden="true">${a.icon}</span>
        <div>
          <small>${esc(a.level)}</small>
          <strong>${esc(a.title)}</strong>
          <span>${esc(a.message)}</span>
        </div>
      </div>`).join("");
    box.hidden = false;
  }

  function renderCharts(data) {
    if (window.WeatherCharts) {
      try { WeatherCharts.render(data.hourly, data.units, state.chartTab); }
      catch (_e) { /* charts are non-critical */ }
    }
  }

  // ------------------------------------------------------------------
  // "Why this forecast?" modal
  // ------------------------------------------------------------------
  function openWhy() {
    const data = state.payload;
    if (!data || !data.score) return;
    const s = data.score;
    const bars = (s.components || []).map((f) => {
      const color = f.score === null ? "var(--muted)" : scoreColor(f.score);
      const width = f.score === null ? 0 : Math.max(2, Math.min(100, f.score));
      return `
      <div class="factor">
        <div class="f-info">
          <div class="f-label">${esc(f.label)} <span class="f-value">${esc(f.value ?? NA)}</span></div>
          <div class="f-note">${esc(f.note ?? "")}</div>
          <div class="f-bar"><i style="width:${width}%;background:${color}"></i></div>
        </div>
        <div class="f-score" style="color:${color}">${f.score === null ? "—" : f.score}</div>
      </div>`;
    }).join("");
    const lines = (data.why || []).map((l) => `
      <div class="why-item">
        <strong>${esc(l.title)}</strong>
        <p>${esc(l.body)}</p>
      </div>`).join("");
    $("why-content").innerHTML = `
      <div class="why-intro">${lines}</div>
      <div class="why-factors">
        <h3>Factor breakdown</h3>
        ${bars}
      </div>
      ${s.available_factors < s.factor_count
        ? `<p class="muted factor-note">${esc(s.note)}</p>` : ""}`;
    $("why-modal").hidden = false;
    $("why-modal").querySelector(".modal-box").scrollTop = 0;
  }
  function closeWhy() { $("why-modal").hidden = true; }

  // ------------------------------------------------------------------
  // Search suggestions
  // ------------------------------------------------------------------
  let suggestTimer = null;
  function attachSuggestions() {
    const input = $("search-input");
    const box = $("search-suggestions");

    function hide() {
      box.hidden = true;
      box.innerHTML = "";
      state.suggestionIndex = -1;
      input.setAttribute("aria-expanded", "false");
    }
    function show(list) {
      box.innerHTML = list.map((s, i) => `
        <li role="option" id="sugg-${i}" data-index="${i}" data-lat="${s.latitude}" data-lon="${s.longitude}">
          <span class="s-name">${esc([s.name, s.admin1, s.country].filter(Boolean).join(", "))}</span>
          <span class="s-coords">${s.latitude.toFixed(2)}, ${s.longitude.toFixed(2)}</span>
        </li>`).join("");
      box.hidden = false;
      input.setAttribute("aria-expanded", "true");
      state.suggestionIndex = -1;
      box.querySelectorAll("li").forEach((li) => li.addEventListener("click", () => {
        hide();
        input.value = `${li.dataset.lat}, ${li.dataset.lon}`;
        loadWeather(input.value);
      }));
    }
    function highlight() {
      box.querySelectorAll("li").forEach((li, i) => {
        li.classList.toggle("selected", i === state.suggestionIndex);
      });
    }

    input.addEventListener("input", () => {
      clearTimeout(suggestTimer);
      const q = input.value.trim();
      if (q.length < 2) { hide(); return; }
      suggestTimer = setTimeout(async () => {
        try {
          const list = await WV.suggest(q);
          if (document.activeElement === input) show(list);
        } catch (_e) { hide(); }
      }, 220);
    });
    input.addEventListener("keydown", (e) => {
      if (box.hidden) return;
      const items = box.querySelectorAll("li");
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        const dir = e.key === "ArrowDown" ? 1 : -1;
        state.suggestionIndex = items.length
          ? (state.suggestionIndex + dir + items.length) % items.length : -1;
        highlight();
      } else if (e.key === "Enter" && state.suggestionIndex >= 0) {
        e.preventDefault();
        const li = items[state.suggestionIndex];
        if (li) {
          hide();
          input.value = `${li.dataset.lat}, ${li.dataset.lon}`;
          loadWeather(input.value);
        }
      } else if (e.key === "Escape") {
        hide();
      }
    });
    input.addEventListener("blur", () => setTimeout(hide, 150));
  }

  // ------------------------------------------------------------------
  // Favorites & history
  // ------------------------------------------------------------------
  function toggleFavorite() {
    const data = state.payload;
    if (!data) return;
    WV.toggleFavorite(data.location);
    state.payload = { ...data, meta: { ...data.meta, is_favorite: !data.meta.is_favorite } };
    setFavoritePin(state.payload.meta.is_favorite);
    refreshSaved();
  }

  function refreshSaved() {
    renderFavorites();
    renderHistory();
  }

  function renderFavorites() {
    const list = WV.favorites() || [];
    $("favorites").innerHTML = list.length
      ? list.map((f) => `<button type="button" class="chip-item" data-lat="${f.latitude}" data-lon="${f.longitude}">⭐ ${esc(f.display_name)}</button>`).join("")
      : `<p class="muted">No favorites yet — tap the ☆ on a location to save it here.</p>`;
    document.querySelectorAll("#favorites .chip-item").forEach((b) => {
      b.addEventListener("click", () => {
        loadWeather(`${b.dataset.lat}, ${b.dataset.lon}`);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  function renderHistory() {
    const list = WV.history() || [];
    $("history").innerHTML = list.length
      ? list.map((h) => `<button type="button" class="chip-item" data-lat="${h.location.latitude}" data-lon="${h.location.longitude}">🕘 ${esc(h.location.display_name)}</button>`).join("")
      : `<p class="muted">Your recent searches will appear here.</p>`;
    $("clear-history-btn").hidden = !list.length;
    document.querySelectorAll("#history .chip-item").forEach((b) => {
      b.addEventListener("click", () => {
        loadWeather(`${b.dataset.lat}, ${b.dataset.lon}`);
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    });
  }

  // ------------------------------------------------------------------
  // Live clock ticking (local time + "updated X ago")
  // ------------------------------------------------------------------
  let ticker = null;
  function startTicker() {
    if (ticker) return;
    ticker = setInterval(() => {
      const data = state.payload;
      if (!data) return;
      $("loc-local-time").textContent = "Local time " + localTimeNow(data.location.timezone);
      const txt = (data.meta.stale ? "Showing last available data · " : "") + timeAgo(data.meta.fetched_at);
      $("updated-text").textContent = txt;
      $("footer-updated").textContent = timeAgo(data.meta.fetched_at);
    }, 30000);
  }

  // ------------------------------------------------------------------
  // Bootstrap
  // ------------------------------------------------------------------
  function init() {
    applyTheme(currentTheme());

    $("theme-toggle").addEventListener("click", () => {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
      if (state.payload) renderCharts(state.payload);
    });

    document.querySelectorAll("#unit-toggle button").forEach((b) =>
      b.addEventListener("click", () => setUnits(b.dataset.units)));
    setUnits(state.units);

    $("search-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = $("search-input").value.trim();
      if (q) loadWeather(q);
    });
    attachSuggestions();

    $("retry-btn").addEventListener("click", () => {
      if (state.query) loadWeather(state.query);
    });
    $("use-cached-btn").addEventListener("click", useLastAvailable);
    $("refresh-btn").addEventListener("click", () => {
      if (state.query) loadWeather(state.query);
    });

    $("favorite-btn").addEventListener("click", toggleFavorite);
    $("favorite-btn").addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggleFavorite(); }
    });

    $("why-btn").addEventListener("click", openWhy);
    $("why-close").addEventListener("click", closeWhy);
    $("why-modal").addEventListener("click", (e) => { if (e.target === $("why-modal")) closeWhy(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWhy(); });

    // Hourly tile detail (event delegation)
    $("hourly").addEventListener("click", (e) => {
      const btn = e.target.closest(".hour");
      if (!btn || !state.payload) return;
      showHourlyDetail(state.payload, Number(btn.dataset.idx));
    });

    // Chart tabs
    $("chart-tabs").addEventListener("click", (e) => {
      const tab = e.target.closest(".tab");
      if (!tab) return;
      state.chartTab = tab.dataset.tab;
      document.querySelectorAll("#chart-tabs .tab").forEach((t) => {
        const on = t === tab;
        t.classList.toggle("active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      if (state.payload) renderCharts(state.payload);
    });

    $("clear-history-btn").addEventListener("click", () => {
      WV.clearHistory();
      renderHistory();
    });

    // Sample chips on the empty state
    const chips = SAMPLE_PLACES.map((p) => `<button type="button" class="chip-item sample" data-q="${esc(p)}">${esc(p)}</button>`).join("");
    $("sample-chips").innerHTML = chips;
    document.querySelectorAll("#sample-chips .chip-item").forEach((b) => {
      b.addEventListener("click", () => {
        $("search-input").value = b.dataset.q;
        loadWeather(b.dataset.q);
      });
    });

    setDemoNotice(!!(window.WEATHERVISION && window.WEATHERVISION.demo));

    refreshSaved();
    startTicker();

    // Deep link: ?q=London → load immediately.
    const params = new URLSearchParams(window.location.search);
    const q = (params.get("q") || "").trim();
    if (q) {
      $("search-input").value = q;
      loadWeather(q);
    } else {
      showState("empty");
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
