/* WeatherVision — Chart.js wrappers (theme-aware). */
"use strict";

const WeatherCharts = (() => {
  let tempChart = null;
  let precipChart = null;
  let windChart = null;

  function cssVar(name) {
    return getComputedStyle(document.documentElement)
      .getPropertyValue(name).trim() || "#64748b";
  }

  function gradient(ctx, color1, color2) {
    const { chartArea } = ctx.chart;
    if (!chartArea) return color1;
    const g = ctx.chart.ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    g.addColorStop(0, color1);
    g.addColorStop(1, color2);
    return g;
  }

  function font() {
    return "'Segoe UI', system-ui, sans-serif";
  }

  function destroyAll() {
    [tempChart, precipChart, windChart].forEach((c) => c && c.destroy());
    tempChart = precipChart = windChart = null;
  }

  function render(hourly, units) {
    destroyAll();
    if (!hourly || !hourly.length) return;

    const labels = hourly.map((h) => h.time);
    const text = cssVar("--text-soft");
    const border = cssVar("--border");
    const accent = cssVar("--accent");
    const ok = "#22c55e";
    const warn = "#f59e0b";
    const skye = "rgba(56, 189, 248, 0.85)";

    const gridOpts = {
      color: border,
      font: { family: font(), size: 10 },
      tickColor: border,
    };
    const base = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
    };

    // Temperature ----------------------------------------------------
    tempChart = new Chart(document.getElementById("chart-temp"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Temperature",
          data: hourly.map((h) => h.temperature),
          borderColor: accent,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: accent,
          fill: true,
          backgroundColor: (ctx) => gradient(ctx, "rgba(56,189,248,0.35)", "rgba(56,189,248,0.02)"),
        }],
      },
      options: {
        ...base,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { color: text, font: { family: font(), size: 10 }, maxTicksLimit: 8 } },
          y: { grid: gridOpts, ticks: { color: text, font: { family: font(), size: 10 }, callback: (v) => `${v}°` } },
        },
      },
    });

    // Precipitation ----------------------------------------------------
    precipChart = new Chart(document.getElementById("chart-precip"), {
      type: "bar",
      data: {
        labels,
        datasets: [{
          label: "Rain probability",
          data: hourly.map((h) => h.precip_prob),
          backgroundColor: (ctx) => gradient(ctx, skye, "rgba(56,189,248,0.15)"),
          borderRadius: 4,
        }],
      },
      options: {
        ...base,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { color: text, font: { family: font(), size: 10 }, maxTicksLimit: 8 } },
          y: { grid: gridOpts, ticks: { color: text, font: { family: font(), size: 10 }, callback: (v) => `${v}%`, suggestedMax: 100 } },
        },
      },
    });

    // Wind --------------------------------------------------------------
    windChart = new Chart(document.getElementById("chart-wind"), {
      type: "line",
      data: {
        labels,
        datasets: [{
          label: "Wind speed",
          data: hourly.map((h) => h.wind),
          borderColor: ok,
          borderWidth: 2,
          tension: 0.35,
          pointRadius: 2,
          pointHoverRadius: 5,
          pointBackgroundColor: ok,
        }],
      },
      options: {
        ...base,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false }, ticks: { color: text, font: { family: font(), size: 10 }, maxTicksLimit: 8 } },
          y: { grid: gridOpts, ticks: { color: text, font: { family: font(), size: 10 } } },
        },
      },
    });

    // Keep charts in sync with the theme after re-renders.
    document.documentElement.setAttribute("data-charts-ready", "true");
  }

  return { render };
})();
window.WeatherCharts = WeatherCharts;
