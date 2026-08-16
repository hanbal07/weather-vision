/* WeatherVision — frontend application logic. */
"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;");

  const state = {
    query: "",
    units: localStorage.getItem("wv-units") || "metric",
    current: null,          // last /api/weather payload
    loading: false,
  };

  // ------------------------------------------------------------------
  // Theme
  // ------------------------------------------------------------------
  function applyTheme(theme) {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("wv-theme", theme);
  }
  function currentTheme() {
    return localStorage.getItem("wv-theme")
      || (window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark");
  }

  // ------------------------------------------------------------------
  // Unit helpers
  // ------------------------------------------------------------------
  function setUnits(units) {
    state.units = units;
    localStorage.setItem("wv-units", units);
    document.querySelectorAll("#unit-toggle button").forEach((b) => {
      b.classList.toggle("active", b.dataset.units === units);
    });
    if (state.query && state.current) loadWeather(state.query); // re-fetch in new units
  }

  // ------------------------------------------------------------------
  // State UI helpers
  // ------------------------------------------------------------------
  function showState(which, text = "") {
    ["empty", "loading", "error"].forEach((k) => $("state-" + k).hidden = k !== which);
    $("state").hidden = false;
    $("dashboard").hidden = true;
    if (text) $("loading-text").textContent = text;
  }
  function showDashboard() {
    $("state").hidden = true;
    $("dashboard").hidden = false;
  }
  function showError(title, message) {
    $("error-title").textContent = title;
    $("error-message").textContent = message;
    showState("error");
  }
  function setDemoBadge(on) {
    $("demo-badge").hidden = !on;
  }

  // ------------------------------------------------------------------
  // Fetching
  // ------------------------------------------------------------------
  async function api(path, options = {}) {
    const res = await fetch(path, {
      headers: { Accept: "application/json", ...(options.headers || {}) },
      ...options,
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || "Request failed (" + res.status + ")");
    return data;
  }

  async function loadWeather(query) {
    if (state.loading) return;
    state.query = query;
    state.loading = true;
    showState("loading", `Fetching weather for ${query}…`);
    try {
      const data = await api(`/api/weather?q=${encodeURIComponent(query)}&units=${state.units}`);
      state.current = data;
      setDemoBadge(data.meta.demo);
      render(data);
      showDashboard();
      loadFavorites();
      loadHistory();
    } catch (err) {
      showError("Unable to fetch weather", err.message);
    } finally {
      state.loading = false;
    }
  }

  // ------------------------------------------------------------------
  // Rendering
  // ------------------------------------------------------------------
  function render(data) {
    const c = data.current;
    const loc = data.location;

    $("loc-name").textContent = loc.display_name;
    $("loc-local-time").textContent = "Local time " + loc.local_time;
    $("hero-icon").textContent = c.icon;
    $("hero-temp").textContent = c.temperature_display;
    $("hero-condition").textContent = c.condition;
    $("hero-feels").textContent = `Feels like ${c.feels_like_display}`;
    $("favorite-btn").classList.toggle("fav-on", data.meta.is_favorite);
    $("favorite-btn").textContent = data.meta.is_favorite ? "★" : "☆";

    renderStats(data);
    renderScore(data);
    renderAirQuality(data);
    renderSun(data);
    renderHourly(data);
    renderDaily(data);
    renderActivities(data);
    renderInsights(data);
    renderAlerts(data);

    if (window.WeatherCharts) WeatherCharts.render(data.hourly, data.units);
  }

  function renderStats(data) {
    const c = data.current;
    const items = [
      ["💧", "Humidity", c.humidity],
      ["💨", "Wind", `${c.wind} ${c.wind_direction}`],
      ["🌪️", "Gusts", c.wind_gusts],
      ["📊", "Pressure", c.pressure],
      ["🌦️", "Rain chance", c.precipitation_probability],
      ["☔", "Precipitation", c.precipitation],
      ["🔆", "UV index", c.uv],
      ["☁️", "Cloud cover", c.cloud_cover],
    ];
    $("stat-grid").innerHTML = items.map(([ic, label, value]) => `
      <div class="stat"><dt>${ic} ${esc(label)}</dt><dd>${esc(value)}</dd></div>`).join("");
  }

  function renderScore(data) {
    if (!data.score) return;
    const s = data.score;
    const pct = Math.max(4, Math.min(100, s.total));
    const arc = $("gauge-arc");
    arc.setAttribute("stroke", s.color);
    arc.setAttribute("stroke-dasharray", `${(pct / 100) * 326}, 326`);
    $("score-total").textContent = s.total + "/100";
    $("score-total").style.color = s.color;
    $("score-grade").textContent = s.grade;
    $("score-grade").style.color = s.color;
  }

  function renderAirQuality(data) {
    const aq = data.air_quality;
    const box = $("air-quality");
    if (!aq) {
      box.innerHTML = `<p class="muted">Air quality data is currently unavailable.</p>`;
      return;
    }
    $("aqi-value").textContent = Math.round(aq.aqi);
    $("aqi-label").textContent = aq.label;
    $("aqi-details").innerHTML = `
      <div class="stat"><dt>PM2.5</dt><dd>${aq.pm25 ?? "—"}</dd></div>
      <div class="stat"><dt>PM10</dt><dd>${aq.pm10 ?? "—"}</dd></div>`;
  }

  function renderSun(data) {
    $("sunrise").textContent = data.current.sunrise;
    $("sunset").textContent = data.current.sunset;
    $("vis-val").textContent = data.current.visibility;
  }

  function renderHourly(data) {
    $("hourly").innerHTML = data.hourly.map((h) => `
      <div class="hour">
        <div class="t">${esc(h.time)}</div>
        <div class="ic">${h.icon}</div>
        <div class="tmp">${Math.round(h.temperature)}°</div>
        <div class="rain">${h.precip_prob}%</div>
      </div>`).join("");
  }

  function renderDaily(data) {
    $("daily").innerHTML = data.daily.map((d) => `
      <div class="day-card">
        <div class="d">${esc(d.day)} · ${esc(d.date)}</div>
        <div class="ic">${d.icon}</div>
        <div class="hi">${d.high_display}</div>
        <div class="lo">${d.low_display}</div>
        <div class="sun">🌅 ${esc(d.sunrise)} · 🌇 ${esc(d.sunset)}</div>
      </div>`).join("");
  }

  function scoreColor(score) {
    if (score >= 80) return "#22c55e";
    if (score >= 60) return "#84cc16";
    if (score >= 40) return "#f59e0b";
    if (score >= 20) return "#f97316";
    return "#ef4444";
  }

  function renderActivities(data) {
    if (!data.activities) { $("activities").innerHTML = ""; return; }
    $("activities").innerHTML = data.activities.map((a) => {
      const color = scoreColor(a.score);
      return `
      <div class="activity">
        <div class="activity-head">
          <span class="nm">${a.icon} ${esc(a.name)}</span>
          <span class="score-label" style="color:${color};font-weight:700">${a.label}</span>
        </div>
        <div class="activity-score">
          <div class="bar"><i style="width:${a.score}%;background:${color}"></i></div>
          <b>${a.score}</b>
        </div>
        <div class="reasons">${esc(a.reasons.join(" · "))}</div>
      </div>`;
    }).join("");
  }

  function renderInsights(data) {
    if (!data.insights || !data.insights.length) { $("insights").innerHTML = `<p class="muted">No insights available.</p>`; return; }
    $("insights").innerHTML = data.insights.map((i) => `
      <div class="insight">
        <span class="ic">${i.icon}</span>
        <div>
          <small style="color:${i.color}">${esc(i.level)}</small>
          <strong>${esc(i.title)}</strong>
          <p>${esc(i.message)}</p>
        </div>
      </div>`).join("");
  }

  function renderAlerts(data) {
    const box = $("alerts");
    const alerts = data.alerts || [];
    if (!alerts.length) { box.hidden = true; box.innerHTML = ""; return; }
    box.innerHTML = alerts.map((a) => `
      <div class="alert" style="--alert-color:${a.color}">
        <span class="a-icon">${a.icon}</span>
        <div>
          <small>${esc(a.level)}</small>
          <strong>${esc(a.title)}</strong>
          <span>${esc(a.message)}</span>
        </div>
      </div>`).join("");
    box.hidden = false;
  }

  // ------------------------------------------------------------------
  // "Why this forecast?" modal
  // ------------------------------------------------------------------
  function openWhy() {
    const data = state.current;
    if (!data || !data.score) return;
    const comps = data.score.components.map((f) => `
      <div class="factor">
        <div class="f-info">
          <div class="f-label">${esc(f.label)} <span class="f-weight">(weight ${Math.round(f.weight * 100)}%)</span></div>
          <div class="f-note">${esc(f.note)}</div>
        </div>
        <div class="f-score" style="color:${scoreColor(f.score)}">${f.score}<small>/100</small></div>
      </div>`).join("");
    const lines = (data.why || []).map((l) => esc(l)).join("<br>");
    $("why-content").innerHTML = `
      <div class="why-lines">${lines}</div>
      <div style="margin-top:14px">${comps}</div>`;
    $("why-modal").hidden = false;
  }
  function closeWhy() { $("why-modal").hidden = true; }

  // ------------------------------------------------------------------
  // Favorites & history
  // ------------------------------------------------------------------
  async function toggleFavorite() {
    const data = state.current;
    if (!data) return;
    const loc = data.location;
    if (data.meta.is_favorite) {
      await api("/api/favorites", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ latitude: loc.latitude, longitude: loc.longitude }),
      });
    } else {
      await api("/api/favorites", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(loc),
      });
    }
    loadWeather(state.query);
  }

  async function loadFavorites() {
    try {
      const data = await api("/api/favorites");
      const list = data.favorites || [];
      $("favorites").innerHTML = list.length
        ? list.map((f) => `<button class="chip-item" data-lat="${f.latitude}" data-lon="${f.longitude}">⭐ ${esc(f.display_name)}</button>`).join("")
        : `<p class="muted">No favorites yet. Star a location to save it here.</p>`;
      document.querySelectorAll("#favorites .chip-item").forEach((b) => {
        b.addEventListener("click", () => {
          loadWeather(`${b.dataset.lat}, ${b.dataset.lon}`);
          window.scrollTo({ top: 0, behavior: "smooth" });
        });
      });
    } catch { /* non-fatal */ }
  }

  async function loadHistory() {
    try {
      const data = await api("/api/history");
      const list = data.history || [];
      $("history").innerHTML = list.length
        ? list.map((h) => `<button class="chip-item" data-lat="${h.location.latitude}" data-lon="${h.location.longitude}">🕘 ${esc(h.location.display_name)}</button>`).join("")
        : `<p class="muted">Your recent searches will appear here.</p>`;
      document.querySelectorAll("#history .chip-item").forEach((b) => {
        b.addEventListener("click", () => {
          loadWeather(`${b.dataset.lat}, ${b.dataset.lon}`);
          window.scrollTo({ top: 0, behavior: "smooth" });
        });
      });
    } catch { /* non-fatal */ }
  }

  // ------------------------------------------------------------------
  // Bootstrap
  // ------------------------------------------------------------------
  function init() {
    applyTheme(currentTheme());

    $("theme-toggle").addEventListener("click", () => {
      applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
      if (state.current && window.WeatherCharts) window.WeatherCharts.render(state.current.hourly, state.units);
    });

    document.querySelectorAll("#unit-toggle button").forEach((b) =>
      b.addEventListener("click", () => setUnits(b.dataset.units)));
    setUnits(state.units); // sync button highlight without re-fetch

    $("search-form").addEventListener("submit", (e) => {
      e.preventDefault();
      const q = $("search-input").value.trim();
      if (q) loadWeather(q);
    });
    $("retry-btn").addEventListener("click", () => {
      if (state.query) loadWeather(state.query);
    });
    $("refresh-btn").addEventListener("click", () => {
      if (state.query) loadWeather(state.query);
    });
    $("favorite-btn").addEventListener("click", toggleFavorite);
    $("why-btn").addEventListener("click", openWhy);
    $("why-close").addEventListener("click", closeWhy);
    $("why-modal").addEventListener("click", (e) => { if (e.target === $("why-modal")) closeWhy(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeWhy(); });

    setDemoBadge(!!(window.WEATHERVISION && window.WEATHERVISION.demo));

    loadFavorites();
    loadHistory();

    // Deep link: /?q=London  → load immediately.
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
