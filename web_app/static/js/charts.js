/* WeatherVision — Chart.js wrappers (v2): a single theme-aware chart whose
 * metric is controlled by the tabbed UI in app.js. Units follow the payload.
 */
"use strict";

const WeatherCharts = (() => {
  let chart = null;

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

  function destroy() {
    if (chart) { chart.destroy(); chart = null; }
  }

  function baseOptions(labels, text, border) {
    const font = (size = 10) => ({ family: "'Segoe UI', system-ui, sans-serif", size });
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: cssVar("--tooltip-bg"),
          titleColor: cssVar("--text"),
          bodyColor: cssVar("--text-soft"),
          borderColor: border,
          borderWidth: 1,
          cornerRadius: 8,
          displayColors: false,
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: text, font: font(10), maxTicksLimit: 8, maxRotation: 0 },
        },
        y: {
          grid: { color: border, tickColor: border },
          ticks: { color: text, font: font(10) },
        },
      },
    };
  }

  function render(hourly, units, tab) {
    destroy();
    if (!hourly || !hourly.length) return;

    const labels = hourly.map((h) => h.time);
    const text = cssVar("--text-soft");
    const border = cssVar("--border");
    const accent = cssVar("--accent");
    const tempColor = "#f59e0b";
    const rainColor = "rgba(56, 189, 248, 0.85)";
    const windColor = "#22c55e";
    const tabName = tab || "temp";
    const tempSuffix = units && units.temp === "F" ? "°F" : "°C";
    const windSuffix = units && units.wind === "mph" ? " mph" : " km/h";

    let type = "line";
    let datasets = [];
    let yTicks = null;

    if (tabName === "temp") {
      datasets = [{
        label: "Temperature",
        data: hourly.map((h) => h.temperature),
        borderColor: tempColor,
        backgroundColor: (ctx) => gradient(ctx, "rgba(245,158,11,0.30)", "rgba(245,158,11,0.02)"),
        borderWidth: 2,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointBackgroundColor: tempColor,
        fill: true,
      }];
      yTicks = (v) => `${v}${tempSuffix}`;
    } else if (tabName === "rain") {
      type = "bar";
      datasets = [{
        label: "Rain probability",
        data: hourly.map((h) => h.precip_prob),
        backgroundColor: (ctx) => gradient(ctx, rainColor, "rgba(56,189,248,0.15)"),
        borderRadius: 4,
      }];
      yTicks = (v) => `${v}%`;
    } else {
      datasets = [{
        label: "Wind speed",
        data: hourly.map((h) => h.wind),
        borderColor: windColor,
        backgroundColor: (ctx) => gradient(ctx, "rgba(34,197,94,0.25)", "rgba(34,197,94,0.02)"),
        borderWidth: 2,
        tension: 0.35,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointBackgroundColor: windColor,
        fill: true,
      }];
      yTicks = (v) => `${v}${windSuffix}`;
    }

    const options = baseOptions(labels, text, border);
    if (yTicks) options.scales.y.ticks.callback = yTicks;
    if (tabName === "rain") options.scales.y.suggestedMax = 100;

    chart = new Chart(document.getElementById("chart-main"), {
      type,
      data: { labels, datasets },
      options,
    });

    document.documentElement.setAttribute("data-charts-ready", "true");
  }

  return { render };
})();
window.WeatherCharts = WeatherCharts;
