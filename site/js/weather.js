/* WeatherVision — static-site data layer.
 *
 * Faithful client-side port of the Flask backend so the same UI works on a
 * static host (GitHub Pages) with no server. Weather data comes directly from
 * Open-Meteo (CORS-enabled, no API key). Favorites and search history are
 * stored in localStorage instead of the SQLite database.
 *
 * Public API:  window.WV.weather(query, units) -> Promise<payload>
 *              window.WV.favorites()  window.WV.toggleFavorite(loc)
 *              window.WV.history()
 *
 * The returned payload matches the shape produced by web_app/serializers.py
 * exactly, so the rendering code is unchanged.
 */
"use strict";

const WV = (() => {
  // --------------------------------------------------------------------
  // Constants (mirror app/utils/helpers.py + app/config.py)
  // --------------------------------------------------------------------
  const FORECAST_URL = "https://api.open-meteo.com/v1/forecast";
  const GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search";
  const AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality";
  const FORECAST_DAYS = 7;
  const HOURLY_LIMIT = 24;
  const HISTORY_LIMIT = 20;

  const WMO_CODES = {
    0: ["Clear sky", "☀️", "🌙"],
    1: ["Mainly clear", "🌤️", "🌙"],
    2: ["Partly cloudy", "⛅", "☁️"],
    3: ["Overcast", "☁️", "☁️"],
    45: ["Fog", "🌫️", "🌫️"],
    48: ["Rime fog", "🌫️", "🌫️"],
    51: ["Light drizzle", "🌦️", "🌧️"],
    53: ["Drizzle", "🌦️", "🌧️"],
    55: ["Dense drizzle", "🌧️", "🌧️"],
    56: ["Freezing drizzle", "🌧️", "🌧️"],
    57: ["Freezing drizzle", "🌧️", "🌧️"],
    61: ["Light rain", "🌦️", "🌧️"],
    63: ["Rain", "🌧️", "🌧️"],
    65: ["Heavy rain", "🌧️", "🌧️"],
    66: ["Freezing rain", "🌧️", "🌧️"],
    67: ["Freezing rain", "🌧️", "🌧️"],
    71: ["Light snow", "🌨️", "🌨️"],
    73: ["Snow", "❄️", "❄️"],
    75: ["Heavy snow", "❄️", "❄️"],
    77: ["Snow grains", "❄️", "❄️"],
    80: ["Light showers", "🌦️", "🌧️"],
    81: ["Rain showers", "🌧️", "🌧️"],
    82: ["Violent showers", "⛈️", "⛈️"],
    85: ["Snow showers", "🌨️", "🌨️"],
    86: ["Snow showers", "❄️", "❄️"],
    95: ["Thunderstorm", "⛈️", "⛈️"],
    96: ["Thunderstorm + hail", "⛈️", "⛈️"],
    99: ["Thunderstorm + hail", "⛈️", "⛈️"],
  };
  const THUNDERSTORM_CODES = new Set([95, 96, 99]);
  const RAIN_CODES = new Set([51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82]);
  const SNOW_CODES = new Set([71, 73, 75, 77, 85, 86]);

  const GRADE_COLORS = {
    Excellent: "#22c55e", Good: "#84cc16", Moderate: "#f59e0b",
    Poor: "#f97316", "Very Poor": "#ef4444",
  };
  const LEVEL_COLORS = {
    INFO: "#64748b", LOW: "#38bdf8", MODERATE: "#f59e0b",
    HIGH: "#f97316", CRITICAL: "#ef4444",
  };

  const CURRENT_FIELDS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature", "is_day",
    "precipitation", "weather_code", "cloud_cover", "pressure_msl",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "visibility", "uv_index",
  ].join(",");
  const HOURLY_FIELDS = [
    "temperature_2m", "precipitation_probability", "precipitation", "weather_code",
    "wind_speed_10m", "wind_direction_10m", "is_day", "visibility",
  ].join(",");
  const DAILY_FIELDS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "precipitation_probability_max", "precipitation_sum",
    "uv_index_max", "sunrise", "sunset",
  ].join(",");

  const COORDINATES_RE = /^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

  // --------------------------------------------------------------------
  // Small helpers
  // --------------------------------------------------------------------
  const fval = (v, d) => (v === null || v === undefined || Number.isNaN(Number(v)) ? d : Number(v));
  const ival = (v, d) => (v === null || v === undefined || Number.isNaN(Number(v)) ? d : Math.trunc(Number(v)));

  // Python's round() uses round-half-to-even; match it for exact parity.
  function pyround(value, ndigits = 0) {
    const m = Math.pow(10, ndigits);
    const x = value * m;
    const f = Math.floor(x);
    const diff = x - f;
    let r;
    if (diff < 0.5) r = f;
    else if (diff > 0.5) r = f + 1;
    else r = (Math.abs(f) % 2 === 0) ? f : f + 1;
    return r / m;
  }

  // Parse an Open-Meteo ISO string (naive, wall-clock in the location timezone)
  // into a Date by treating it as UTC; formatting then applies the real tz.
  function toDate(isoLike) {
    if (!isoLike) return null;
    const s = (String(isoLike).includes("Z") || /\+\d{2}:\d{2}$/.test(String(isoLike)))
      ? String(isoLike) : String(isoLike) + "Z";
    const d = new Date(s);
    return Number.isNaN(d.getTime()) ? null : d;
  }

  function fmtInTz(value, tz, options) {
    const d = toDate(value);
    if (!d) return "—";
    try {
      return new Intl.DateTimeFormat("en-US", { timeZone: tz, ...options }).format(d);
    } catch (_e) {
      return "—";
    }
  }

  const clock = (value, tz) => fmtInTz(value, tz, { hour: "2-digit", minute: "2-digit", hour12: false });
  const dayLabel = (value, tz) => fmtInTz(value, tz, { weekday: "short" });
  const dateLabel = (value, tz) => fmtInTz(value, tz, { month: "short", day: "numeric" });

  function localTime(tz) {
    try {
      return new Intl.DateTimeFormat("en-GB", {
        timeZone: tz, hour: "2-digit", minute: "2-digit", hour12: false,
      }).format(new Date());
    } catch (_e) {
      return new Date().toTimeString().slice(0, 5);
    }
  }

  // --------------------------------------------------------------------
  // Units (mirror app/utils/units.py)
  // --------------------------------------------------------------------
  const convertTemp = (c, u) => (u === "F" ? c * 9 / 5 + 32 : c);
  const formatTemp = (c, u) => `${Math.round(convertTemp(c, u))}°${u}`;
  const convertWind = (kmh, u) => (u === "mph" ? kmh * 0.621371 : kmh);
  const formatWind = (kmh, u) => `${Math.round(convertWind(kmh, u))} ${u}`;
  const convertPressure = (hpa, u) => (u === "inHg" ? hpa * 0.0295299830714 : hpa);
  function formatPressure(hpa, u) {
    const v = convertPressure(hpa, u);
    return u === "inHg" ? `${v.toFixed(2)} inHg` : `${Math.round(v)} hPa`;
  }
  function formatVisibility(metres, u) {
    const km = metres / 1000;
    const v = u === "mph" ? km * 0.621371 : km;
    return `${v.toFixed(1)} ${u === "mph" ? "mi" : "km"}`;
  }
  const WIND_DIRECTIONS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  function windDirection(degrees) {
    if (degrees === null || degrees === undefined) return "—";
    const idx = Math.floor((((degrees % 360) + 11.25) / 22.5)) % 16;
    return WIND_DIRECTIONS[idx];
  }
  function aqiCategory(aqi) {
    if (aqi === null || aqi === undefined) return "Unavailable";
    if (aqi <= 50) return "Good";
    if (aqi <= 100) return "Moderate";
    if (aqi <= 150) return "Sensitive";
    if (aqi <= 200) return "Unhealthy";
    if (aqi <= 300) return "Very Unhealthy";
    return "Hazardous";
  }

  // --------------------------------------------------------------------
  // WMO condition
  // --------------------------------------------------------------------
  function conditionFromCode(code, isDay) {
    if (code === null || code === undefined) return { text: "Unknown", icon: "🌡️" };
    const entry = WMO_CODES[code] || ["Unknown", "🌡️", "🌡️"];
    return { text: entry[0], icon: isDay ? entry[1] : entry[2] };
  }

  // --------------------------------------------------------------------
  // Parsing (mirror app/models/weather_models.py + serializers.py)
  // --------------------------------------------------------------------
  function parseForecast(payload, location, airPayload) {
    const cur = payload.current || {};
    const hourly = payload.hourly || {};
    const daily = payload.daily || {};

    const isDay = Boolean(ival(cur.is_day, 1));
    const code = ival(cur.weather_code, 0);
    const cond = conditionFromCode(code, isDay);

    const times = hourly.time || [];
    const probs = hourly.precipitation_probability || [];
    const h13 = new Date().toISOString().slice(0, 13);
    let precipProb = 0;
    if (times.length && times.length === probs.length) {
      for (let i = 0; i < times.length; i++) {
        const t = String(times[i]);
        if (t.startsWith(h13) || t >= h13) { precipProb = ival(probs[i], 0); break; }
      }
      if (!precipProb && probs.length) precipProb = ival(probs[0], 0);
    }

    const sunrise = firstDaily(daily, "sunrise");
    const sunset = firstDaily(daily, "sunset");

    const current = {
      temperature: fval(cur.temperature_2m, 0),
      feels_like: fval(cur.apparent_temperature, fval(cur.temperature_2m, 0)),
      condition_code: code,
      condition_text: cond.text,
      icon: cond.icon,
      humidity: ival(cur.relative_humidity_2m, 0),
      wind_speed: fval(cur.wind_speed_10m, 0),
      wind_direction: ival(cur.wind_direction_10m, 0),
      wind_gusts: fval(cur.wind_gusts_10m, 0),
      pressure: fval(cur.pressure_msl, 1013),
      visibility_m: fval(cur.visibility, 10000),
      cloud_cover: ival(cur.cloud_cover, 0),
      uv_index: cur.uv_index === undefined || cur.uv_index === null ? null : fval(cur.uv_index, 0),
      is_day: isDay,
      precipitation: fval(cur.precipitation, 0),
      precipitation_probability: precipProb,
      sunrise,
      sunset,
    };

    const nowUtcMs = Math.floor(Date.now() / 3600000) * 3600000;
    const hourlyList = [];
    for (let i = 0; i < times.length; i++) {
      const raw = String(times[i]);
      const d = toDate(raw);
      if (d && d.getTime() < nowUtcMs) continue;
      const hCode = ival((hourly.weather_code || [])[i], 0);
      const hDay = Boolean(ival((hourly.is_day || [])[i], 1));
      const hCond = conditionFromCode(hCode, hDay);
      hourlyList.push({
        time: raw,
        temperature: fval((hourly.temperature_2m || [])[i], 0),
        precipitation_probability: ival((hourly.precipitation_probability || [])[i], 0),
        precipitation: fval((hourly.precipitation || [])[i], 0),
        condition_code: hCode,
        condition_text: hCond.text,
        icon: hCond.icon,
        wind_speed: fval((hourly.wind_speed_10m || [])[i], 0),
        is_day: hDay,
      });
      if (hourlyList.length >= HOURLY_LIMIT) break;
    }

    const dailyList = [];
    const dates = daily.time || [];
    for (let i = 0; i < dates.length; i++) {
      const dCode = ival((daily.weather_code || [])[i], 0);
      const dCond = conditionFromCode(dCode, true);
      dailyList.push({
        date: String(dates[i]),
        temp_max: fval((daily.temperature_2m_max || [])[i], 0),
        temp_min: fval((daily.temperature_2m_min || [])[i], 0),
        condition_code: dCode,
        condition_text: dCond.text,
        icon: dCond.icon,
        precipitation_probability: ival((daily.precipitation_probability_max || [])[i], 0),
        precipitation_sum: fval((daily.precipitation_sum || [])[i], 0),
        uv_index_max: fval((daily.uv_index_max || [])[i], 0),
        sunrise: firstAt(daily, "sunrise", i),
        sunset: firstAt(daily, "sunset", i),
      });
    }

    let airQuality = null;
    if (airPayload && airPayload.current && airPayload.current.us_aqi !== undefined && airPayload.current.us_aqi !== null) {
      airQuality = {
        aqi: fval(airPayload.current.us_aqi, 0),
        pm2_5: fval(airPayload.current.pm2_5, 0),
        pm10: fval(airPayload.current.pm10, 0),
      };
    }

    return {
      location,
      current,
      hourly: hourlyList,
      daily: dailyList,
      air_quality: airQuality,
      fetched_at: new Date().toISOString(),
      source: "live",
    };
  }

  const firstDaily = (daily, key) => {
    const v = daily[key];
    if (Array.isArray(v) && v.length) return String(v[0]);
    if (typeof v === "string") return v;
    return "";
  };
  const firstAt = (daily, key, i) => {
    const v = daily[key];
    if (Array.isArray(v) && i < v.length && v[i] !== undefined && v[i] !== null) return String(v[i]);
    return "";
  };

  function serialize(weather, unitSet, isFavorite) {
    const c = weather.current;
    const loc = weather.location;
    const tz = loc.timezone || "UTC";
    const [tempUnit, windUnit, pressureUnit] = unitSet;

    const payload = {
      meta: {
        app: "WeatherVision",
        source: weather.source,
        demo: false,
        fetched_at: weather.fetched_at,
        is_favorite: isFavorite,
      },
      location: {
        ...loc,
        display_name: loc.display_name,
        local_time: localTime(tz),
      },
      units: { temp: tempUnit, wind: windUnit, pressure: pressureUnit },
      current: {
        temperature: pyround(c.temperature, 1),
        temperature_display: formatTemp(c.temperature, tempUnit),
        feels_like: pyround(c.feels_like, 1),
        feels_like_display: formatTemp(c.feels_like, tempUnit),
        condition: c.condition_text,
        icon: c.icon,
        humidity: `${c.humidity}%`,
        pressure: formatPressure(c.pressure, pressureUnit),
        wind: formatWind(c.wind_speed, windUnit),
        wind_direction: windDirection(c.wind_direction),
        wind_gusts: formatWind(c.wind_gusts, windUnit),
        visibility: formatVisibility(c.visibility_m, windUnit),
        uv: c.uv_index === null || c.uv_index === undefined ? "n/a" : c.uv_index.toFixed(1),
        precipitation: `${c.precipitation.toFixed(1)} mm`,
        precipitation_probability: `${c.precipitation_probability}%`,
        cloud_cover: `${c.cloud_cover}%`,
        sunrise: clock(c.sunrise, tz),
        sunset: clock(c.sunset, tz),
        is_day: c.is_day,
      },
      hourly: weather.hourly.map((h) => ({
        time: clock(h.time, tz),
        icon: h.icon,
        condition: h.condition_text,
        temperature: pyround(convertTemp(h.temperature, tempUnit), 1),
        precip_prob: h.precipitation_probability,
        precipitation: pyround(h.precipitation, 1),
        wind: pyround(convertWind(h.wind_speed, windUnit), 1),
        is_day: h.is_day,
      })),
      daily: weather.daily.map((d) => ({
        day: dayLabel(`${d.date}T12:00`, tz),
        date: dateLabel(`${d.date}T12:00`, tz),
        icon: d.icon,
        condition: d.condition_text,
        high: pyround(convertTemp(d.temp_max, tempUnit), 1),
        low: pyround(convertTemp(d.temp_min, tempUnit), 1),
        high_display: formatTemp(d.temp_max, tempUnit),
        low_display: formatTemp(d.temp_min, tempUnit),
        precip_prob: d.precipitation_probability,
        precipitation_sum: pyround(d.precipitation_sum, 1),
        uv: d.uv_index_max,
        sunrise: clock(d.sunrise, tz),
        sunset: clock(d.sunset, tz),
      })),
      air_quality: weather.air_quality
        ? {
            aqi: weather.air_quality.aqi,
            label: aqiCategory(weather.air_quality.aqi),
            pm25: weather.air_quality.pm2_5,
            pm10: weather.air_quality.pm10,
          }
        : null,
    };

    const score = comfortScore(weather);
    payload.score = serializeScore(score);
    payload.why = whyLines(weather, score);
    payload.activities = activityScores(weather).map((a) => ({
      name: a.name, icon: a.icon, score: a.score, label: a.label, reasons: a.reasons,
    }));
    payload.insights = insights(weather).map((i) => ({
      icon: i.icon, title: i.title, message: i.message, level: i.level,
      color: LEVEL_COLORS[i.level] || "#64748b",
    }));
    payload.alerts = evaluateAlerts(weather, score.total).map((a) => ({
      level: a.level, icon: a.icon, title: a.title, message: a.message,
      color: LEVEL_COLORS[a.level] || "#64748b",
    }));
    return payload;
  }

  // --------------------------------------------------------------------
  // Scoring (mirror app/services/intelligence_engine.py)
  // --------------------------------------------------------------------
  function lerp(value, a, b, scoreA, scoreB) {
    if (b === a) return scoreA;
    const ratio = (value - a) / (b - a);
    return scoreA + (scoreB - scoreA) * Math.max(0, Math.min(1, ratio));
  }
  function rangeScore(value, idealLo, idealHi, warnLo, warnHi, extremeLo, extremeHi) {
    if (idealLo <= value && value <= idealHi) return 100;
    if (value < extremeLo || value > extremeHi) return 0;
    if (warnLo <= value && value < idealLo) return lerp(value, warnLo, idealLo, 70, 100);
    if (idealHi < value && value <= warnHi) return lerp(value, idealHi, warnHi, 100, 70);
    if (extremeLo <= value && value < warnLo) return lerp(value, extremeLo, warnLo, 40, 70);
    return lerp(value, warnHi, extremeHi, 70, 40);
  }
  const rainScore = (prob) => Math.max(0, 100 - prob);

  const gradeOf = (score) => {
    const bands = [[81, "Excellent"], [61, "Good"], [41, "Moderate"], [21, "Poor"], [0, "Very Poor"]];
    for (const [bound, grade] of bands) if (score >= bound) return grade;
    return "Very Poor";
  };

  function uvScore(uv, isDay) {
    if (uv === null || uv === undefined) return 100;
    if (!isDay) return 100;
    if (uv <= 2) return 100;
    if (uv <= 5) return 80;
    if (uv <= 7) return 60;
    if (uv <= 10) return 40;
    return 20;
  }

  function comfortScore(weather) {
    const c = weather.current;
    const visKm = c.visibility_m / 1000;
    const components = [
      {
        label: "Temperature",
        score: pyround(rangeScore(c.temperature, 18, 24, 10, 30, 0, 40)),
        weight: 0.30,
        value: `${c.temperature.toFixed(0)}°C`,
        note: temperatureNote(c.temperature, rangeScore(c.temperature, 18, 24, 10, 30, 0, 40)),
      },
      {
        label: "Humidity",
        score: pyround(rangeScore(c.humidity, 40, 60, 25, 75, 10, 90)),
        weight: 0.20,
        value: `${c.humidity}%`,
        note: humidityNote(c.humidity, rangeScore(c.humidity, 40, 60, 25, 75, 10, 90)),
      },
      {
        label: "Wind",
        score: pyround(rangeScore(c.wind_speed, 0, 25, 45, 70, 90, 110)),
        weight: 0.15,
        value: `${c.wind_speed.toFixed(0)} km/h`,
        note: windNote(c.wind_speed, rangeScore(c.wind_speed, 0, 25, 45, 70, 90, 110)),
      },
      {
        label: "Rain probability",
        score: pyround(rainScore(c.precipitation_probability)),
        weight: 0.15,
        value: `${c.precipitation_probability}%`,
        note: rainNote(c.precipitation_probability, rainScore(c.precipitation_probability)),
      },
      {
        label: "Visibility",
        score: pyround(rangeScore(visKm, 10, 40, 5, 6, 1, 2)),
        weight: 0.10,
        value: `${visKm.toFixed(1)} km`,
        note: visibilityNote(visKm, rangeScore(visKm, 10, 40, 5, 6, 1, 2)),
      },
      {
        label: "UV index",
        score: Math.round(uvScore(c.uv_index, c.is_day)),
        weight: 0.10,
        value: uvValueText(c.uv_index, c.is_day),
        note: uvNote(c.uv_index, c.is_day, uvScore(c.uv_index, c.is_day)),
      },
    ];
    let total = pyround(components.reduce((sum, cpt) => sum + cpt.score * cpt.weight, 0));
    total = Math.max(0, Math.min(100, total));
    return { total, grade: gradeOf(total), grade_label: gradeOf(total), components };
  }

  function serializeScore(score) {
    return {
      total: score.total,
      grade: score.grade,
      color: GRADE_COLORS[score.grade] || "#64748b",
      components: score.components.map((cpt) => ({
        label: cpt.label,
        score: cpt.score,
        weight: pyround(cpt.weight * 100) / 100,
        value: cpt.value,
        note: cpt.note,
      })),
    };
  }

  function whyLines(weather, score) {
    const lines = [
      `Weather Comfort Score = ${score.total}/100 (${score.grade}).`,
      "The score is computed from six weather factors, each contributing a weighted penalty:",
    ];
    for (const cpt of score.components) {
      lines.push(
        `• ${cpt.label} (${cpt.value}): ${cpt.note} ` +
        `[contribution ${pyround(cpt.score * cpt.weight)}/${pyround(cpt.weight * 100)}]`
      );
    }
    if (score.total >= 61) lines.push("Overall the conditions are pleasant for most outdoor activities.");
    else if (score.total >= 41) lines.push("Conditions are mixed - plan activities around the weakest factors above.");
    else lines.push("Conditions are poor for general outdoor activity. See the activity planner.");
    return lines;
  }

  function temperatureNote(value, score) {
    if (18 <= value && value <= 24) return "Within the ideal 18-24°C range - no penalty.";
    if (score >= 70) return `${value.toFixed(0)}°C is slightly outside the ideal 18-24°C band.`;
    if (score >= 40) return `${value.toFixed(0)}°C is uncomfortable for most people.`;
    return `${value.toFixed(0)}°C is extreme - a major comfort penalty.`;
  }
  function humidityNote(value, score) {
    if (40 <= value && value <= 60) return "Humidity is comfortable (40-60%).";
    if (score >= 70) return `${value}% humidity is a little outside the comfortable band.`;
    if (score >= 40) return `${value}% humidity feels muggy or dry - reduces comfort.`;
    return `${value}% humidity is extreme - serious comfort impact.`;
  }
  function windNote(value, score) {
    if (value <= 25) return "Wind is light - no penalty.";
    if (score >= 70) return `${value.toFixed(0)} km/h wind is noticeable but acceptable.`;
    if (score >= 40) return `${value.toFixed(0)} km/h wind makes outdoor activity harder.`;
    return `${value.toFixed(0)} km/h wind is strong and disruptive.`;
  }
  function rainNote(value, score) {
    if (value <= 15) return "Very low chance of rain.";
    if (value <= 45) return `${value}% rain probability - minor uncertainty.`;
    if (value <= 70) return `${value}% rain probability - moderate chance of rain.`;
    return `${value}% rain probability - rain is likely.`;
  }
  function visibilityNote(value, score) {
    if (value >= 10) return "Visibility is excellent (10+ km).";
    if (score >= 70) return `${value.toFixed(1)} km visibility is acceptable.`;
    if (score >= 40) return `${value.toFixed(1)} km visibility limits long-distance views.`;
    return `${value.toFixed(1)} km visibility is very poor.`;
  }
  function uvValueText(uv, isDay) {
    if (uv === null || uv === undefined) return "n/a";
    return isDay ? uv.toFixed(1) : uv.toFixed(0);
  }
  function uvNote(uv, isDay, score) {
    if (uv === null || uv === undefined) return "UV data unavailable - no penalty applied.";
    if (!isDay) return "Night time - UV risk is negligible.";
    if (score === 100) return `UV index ${uv.toFixed(1)} is low - sun is safe.`;
    if (score >= 60) return `UV index ${uv.toFixed(1)} is moderate - light sun protection advised.`;
    if (score >= 40) return `UV index ${uv.toFixed(1)} is high - sun protection required.`;
    return `UV index ${uv.toFixed(1)} is very high - avoid prolonged exposure.`;
  }

  // --------------------------------------------------------------------
  // Activities (mirror ACTIVITY_SPECS / ACTIVITY_WEIGHTS)
  // --------------------------------------------------------------------
  const ACTIVITY_SPECS = {
    Walking: { icon: "🚶", temp: [12, 28], humidity: [30, 75], wind_max: 35, rain_max: 50, uv_max: 7, visibility_min: 5 },
    Running: { icon: "🏃", temp: [10, 25], humidity: [30, 65], wind_max: 38, rain_max: 40, uv_max: 6, visibility_min: 5 },
    Cycling: { icon: "🚴", temp: [12, 30], humidity: [30, 70], wind_max: 42, rain_max: 45, uv_max: 7, visibility_min: 8 },
    "Outdoor Photography": { icon: "📷", temp: [0, 35], humidity: [25, 85], wind_max: 48, rain_max: 30, uv_max: 10, visibility_min: 10 },
    Picnic: { icon: "🧺", temp: [18, 30], humidity: [30, 65], wind_max: 25, rain_max: 25, uv_max: 7, visibility_min: 8 },
    Travel: { icon: "✈️", temp: [5, 35], humidity: [20, 80], wind_max: 55, rain_max: 60, uv_max: 10, visibility_min: 6 },
    "Outdoor Study": { icon: "📚", temp: [15, 32], humidity: [30, 70], wind_max: 32, rain_max: 35, uv_max: 8, visibility_min: 5 },
    Sports: { icon: "⚽", temp: [12, 28], humidity: [35, 70], wind_max: 35, rain_max: 40, uv_max: 7, visibility_min: 8 },
  };
  const ACTIVITY_WEIGHTS = { temperature: 0.35, rain: 0.25, wind: 0.15, humidity: 0.10, uv: 0.10, visibility: 0.05 };

  function activityLabel(score) {
    if (score >= 80) return "Great";
    if (score >= 60) return "Good";
    if (score >= 40) return "Fair";
    if (score >= 20) return "Poor";
    return "Very poor";
  }

  function activityScores(weather) {
    const c = weather.current;
    const visKm = c.visibility_m / 1000;
    const results = [];
    for (const [name, spec] of Object.entries(ACTIVITY_SPECS)) {
      const factors = {};
      const [tl, th] = spec.temp;
      factors.temperature = rangeScore(c.temperature, tl, th, tl - 8, th + 8, tl - 16, th + 16);
      factors.rain = rangeScore(c.precipitation_probability, 0, spec.rain_max, spec.rain_max, spec.rain_max + 30, spec.rain_max + 40, spec.rain_max + 70);
      factors.wind = rangeScore(c.wind_speed, 0, spec.wind_max, spec.wind_max, spec.wind_max + 25, spec.wind_max + 40, spec.wind_max + 60);
      const [hl, hh] = spec.humidity;
      factors.humidity = rangeScore(c.humidity, hl, hh, hl - 15, hh + 15, hl - 30, hh + 30);
      factors.uv = Math.min(uvScore(c.uv_index, c.is_day),
        rangeScore(c.uv_index === null || c.uv_index === undefined ? 0 : c.uv_index, 0, spec.uv_max, spec.uv_max, spec.uv_max + 3, spec.uv_max + 6, spec.uv_max + 9));
      factors.visibility = rangeScore(visKm, spec.visibility_min, 40, spec.visibility_min - 2, 6, spec.visibility_min - 4, 2);

      let total = pyround(Object.keys(ACTIVITY_WEIGHTS).reduce((s, k) => s + factors[k] * ACTIVITY_WEIGHTS[k], 0));
      total = Math.max(0, Math.min(100, total));
      results.push({ name, icon: spec.icon, score: total, label: activityLabel(total), reasons: activityReasons(name, factors, c) });
    }
    results.sort((a, b) => b.score - a.score);
    return results;
  }

  function activityReasons(name, factors, c) {
    const penalties = Object.entries(factors)
      .map(([label, score]) => ({ label, score }))
      .filter((f) => f.score < 100)
      .sort((a, b) => a.score - b.score);
    const reasons = [];
    for (const { label } of penalties.slice(0, 2)) {
      if (label === "temperature") reasons.push(`Temperature ${c.temperature.toFixed(0)}°C is not ideal for ${name.toLowerCase()}.`);
      else if (label === "rain") reasons.push(`${c.precipitation_probability}% rain chance affects ${name.toLowerCase()}.`);
      else if (label === "wind") reasons.push(`Wind of ${c.wind_speed.toFixed(0)} km/h is a factor.`);
      else if (label === "uv") reasons.push("UV exposure needs consideration.");
      else if (label === "visibility") reasons.push("Visibility is limited.");
      else if (label === "humidity") reasons.push("Humidity affects comfort.");
    }
    return reasons.length ? reasons : ["All weather factors are favourable."];
  }

  // --------------------------------------------------------------------
  // Insights (mirror IntelligenceEngine.insights)
  // --------------------------------------------------------------------
  function insights(weather) {
    const c = weather.current;
    const visKm = c.visibility_m / 1000;
    const score = comfortScore(weather).total;
    const out = [];

    if (c.temperature >= 35) out.push(ins("🌡️", "Extreme heat", `${c.temperature.toFixed(0)}°C is very hot. Stay hydrated, seek shade and limit exertion.`, "HIGH"));
    else if (c.temperature >= 30) out.push(ins("🌡️", "Hot conditions", `At ${c.temperature.toFixed(0)}°C it is hot. Plan outdoor time for cooler hours.`, "MODERATE"));
    else if (c.temperature <= -5) out.push(ins("🥶", "Bitter cold", `${c.temperature.toFixed(0)}°C - dress in layers and keep skin covered.`, "HIGH"));
    else if (c.temperature <= 5) out.push(ins("🥶", "Cold conditions", `Only ${c.temperature.toFixed(0)}°C - warm clothing recommended.`, "MODERATE"));

    if (c.feels_like - c.temperature >= 3) {
      out.push(ins("💧", "Humidity makes it feel hotter",
        `It feels like ${c.feels_like.toFixed(0)}°C due to ${c.humidity}% humidity.`, "MODERATE"));
    }

    if (THUNDERSTORM_CODES.has(c.condition_code)) {
      out.push(ins("⛈️", "Thunderstorm", "Thunderstorm conditions detected. Avoid open areas and stay indoors.", "CRITICAL"));
    } else if (c.precipitation_probability >= 80 || (RAIN_CODES.has(c.condition_code) && c.precipitation > 1.5)) {
      out.push(ins("🌧️", "Rain alert", `Rain is very likely (${c.precipitation_probability}%). Carry an umbrella.`, "HIGH"));
    } else if (c.precipitation_probability >= 55) {
      out.push(ins("☔", "Possible rain", `Rain chance is ${c.precipitation_probability}% - consider an umbrella.`, "MODERATE"));
    } else if (c.precipitation_probability >= 35) {
      out.push(ins("🌦️", "Slight rain chance", `A ${c.precipitation_probability}% chance of light rain exists.`, "LOW"));
    }

    if (SNOW_CODES.has(c.condition_code)) {
      out.push(ins("❄️", "Snow conditions", "Snow is falling or forecast. Expect slippery surfaces.", "MODERATE"));
    }

    if (c.wind_speed >= 50) out.push(ins("🌬️", "Strong wind", `Wind gusts may reach ${c.wind_gusts.toFixed(0)} km/h. Secure loose items.`, "HIGH"));
    else if (c.wind_speed >= 32) out.push(ins("🌬️", "Breezy", `${c.wind_speed.toFixed(0)} km/h wind - noticeable during outdoor activity.`, "LOW"));

    if (c.uv_index !== null && c.uv_index !== undefined && c.is_day) {
      if (c.uv_index >= 11) out.push(ins("☀️", "Extreme UV", `UV index ${c.uv_index.toFixed(1)} - avoid the sun between 11:00-15:00.`, "HIGH"));
      else if (c.uv_index >= 8) out.push(ins("☀️", "High UV", `UV index ${c.uv_index.toFixed(1)} - use SPF 30+ and sunglasses.`, "MODERATE"));
      else if (c.uv_index >= 6) out.push(ins("☀️", "Moderate UV", `UV index ${c.uv_index.toFixed(1)} - light sun protection advised.`, "LOW"));
    }

    if (visKm < 2) out.push(ins("🌫️", "Very poor visibility", `Visibility is only ${visKm.toFixed(1)} km - drive with extreme care.`, "HIGH"));
    else if (visKm < 5) out.push(ins("🌫️", "Reduced visibility", `Visibility is ${visKm.toFixed(1)} km - take care on the roads.`, "MODERATE"));

    if (score <= 40) out.push(ins("🚫", "Poor outdoor conditions", "The overall comfort score is low. Prefer indoor activities today.", "MODERATE"));

    out.push(clothingInsight(weather));

    if (visKm < 5 || c.precipitation_probability >= 55 || c.wind_speed >= 50) {
      out.push(ins("🧳", "Travel consideration", "Visibility, precipitation or wind may affect long-distance travel.", "LOW"));
    }
    return out.slice(0, 8);
  }

  const ins = (icon, title, message, level) => ({ icon, title, message, level });

  function clothingInsight(weather) {
    const t = weather.current.temperature;
    const rain = weather.current.precipitation_probability;
    let msg;
    if (t >= 28) msg = "Light clothing is suitable. Use sun protection when outdoors.";
    else if (t >= 18) msg = "Light-to-medium clothing is comfortable.";
    else if (t >= 10) msg = "Medium clothing recommended; a light jacket may help.";
    else if (t >= 2) msg = "Warm clothing recommended.";
    else msg = "Heavy winter clothing is strongly recommended.";
    if (rain >= 55) msg += " Rain protection (umbrella/waterproof) would be useful.";
    return ins("👕", "Clothing insight", msg, "INFO");
  }

  // --------------------------------------------------------------------
  // Alerts (mirror app/services/alert_engine.py)
  // --------------------------------------------------------------------
  const SEVERITY_ORDER = { INFO: 0, LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 };

  function evaluateAlerts(weather, comfortScoreTotal) {
    const c = weather.current;
    const visKm = c.visibility_m / 1000;
    const alerts = [];

    if (RAIN_CODES.has(c.condition_code) && c.precipitation >= 2.5) {
      alerts.push(alert("HIGH", "🌧️", "Heavy rain", `Rainfall rate is ${c.precipitation.toFixed(1)} mm/h. Seek shelter and take care on the roads.`));
    } else if (c.precipitation_probability >= 85) {
      alerts.push(alert("MODERATE", "🌧️", "High rain probability", `There is a ${c.precipitation_probability}% chance of rain soon.`));
    }

    if (THUNDERSTORM_CODES.has(c.condition_code)) {
      alerts.push(alert("CRITICAL", "⛈️", "Thunderstorm", "Thunderstorm conditions are present. Avoid open areas, tall objects and water."));
    }

    if (c.temperature >= 35) alerts.push(alert("HIGH", "🌡️", "Extreme heat", `Temperature reached ${c.temperature.toFixed(0)}°C. Stay hydrated and limit exposure.`));
    else if (c.temperature <= -5) alerts.push(alert("HIGH", "🥶", "Extreme cold", `Temperature dropped to ${c.temperature.toFixed(0)}°C. Dress warmly and limit exposure.`));

    if (c.uv_index !== null && c.uv_index !== undefined && c.is_day && c.uv_index >= 8) {
      alerts.push(alert(c.uv_index >= 10 ? "HIGH" : "MODERATE", "☀️", "High UV index", `UV index is ${c.uv_index.toFixed(1)}. Use sunscreen, sunglasses and a hat.`));
    }

    if (c.wind_speed >= 45) {
      alerts.push(alert(c.wind_speed >= 60 ? "HIGH" : "MODERATE", "🌬️", "Strong wind", `Wind speed is ${c.wind_speed.toFixed(0)} km/h (gusts to ${c.wind_gusts.toFixed(0)} km/h).`));
    }

    if (visKm < 2) alerts.push(alert("HIGH", "🌫️", "Very poor visibility", `Visibility is only ${visKm.toFixed(1)} km. Travel with extreme caution.`));
    else if (visKm < 5) alerts.push(alert("MODERATE", "🌫️", "Reduced visibility", `Visibility is ${visKm.toFixed(1)} km. Allow extra distance on the road.`));

    if (comfortScoreTotal <= 25) alerts.push(alert("HIGH", "🚫", "Very poor outdoor conditions", `The Weather Comfort Score is ${comfortScoreTotal}/100. Outdoor activity is discouraged.`));
    else if (comfortScoreTotal <= 40) alerts.push(alert("MODERATE", "⚠️", "Poor outdoor conditions", `The Weather Comfort Score is ${comfortScoreTotal}/100. Plan indoor alternatives.`));

    if (weather.daily.length >= 2) {
      const tomorrow = weather.daily[1];
      if (tomorrow.precipitation_probability >= 75) {
        alerts.push(alert("LOW", "🗓️", "Rain expected tomorrow",
          `There is a ${tomorrow.precipitation_probability}% chance of rain tomorrow (${tomorrow.date}). Plan accordingly.`));
      }
    }

    alerts.sort((a, b) => SEVERITY_ORDER[b.level] - SEVERITY_ORDER[a.level]);
    return alerts;
  }

  const alert = (level, icon, title, message) => ({ level, icon, title, message });

  // --------------------------------------------------------------------
  // Geocoding (mirror app/api/geocoding.py)
  // --------------------------------------------------------------------
  function detectCoordinates(text) {
    const match = COORDINATES_RE.exec(text);
    if (!match) return null;
    const lat = parseFloat(match[1]);
    const lon = parseFloat(match[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return [lat, lon];
  }

  async function geocode(query) {
    const coords = detectCoordinates(query);
    if (coords) {
      return [{
        name: `${coords[0].toFixed(2)}, ${coords[1].toFixed(2)}`,
        country: "Coordinates",
        country_code: "",
        admin1: "",
        latitude: coords[0],
        longitude: coords[1],
        timezone: "UTC",
        population: null,
      }];
    }
    const url = `${GEOCODING_URL}?name=${encodeURIComponent(query)}&count=8&language=en&format=json`;
    const data = await fetchJSON(url);
    const results = data && data.results;
    if (!results || !results.length) return [];
    return results.slice(0, 8).map((r) => ({
      name: r.name || "Unknown",
      country: r.country || "",
      country_code: r.country_code || "",
      admin1: r.admin1 || "",
      latitude: Number(r.latitude) || 0,
      longitude: Number(r.longitude) || 0,
      timezone: r.timezone || "UTC",
      population: r.population === undefined ? null : Number(r.population),
    }));
  }

  async function fetchJSON(url) {
    let res;
    try {
      res = await fetch(url, { headers: { Accept: "application/json" } });
    } catch (_e) {
      throw new Error("Cannot reach the weather server. Please check your internet connection and try again.");
    }
    let data = {};
    try { data = await res.json(); } catch (_e) { /* fallthrough */ }
    if (!res.ok) {
      if (res.status === 404) throw new Error("We couldn't find that location. Check the spelling or try a nearby city name.");
      throw new Error("The weather service returned unexpected data. Please try again.");
    }
    return data;
  }

  // --------------------------------------------------------------------
  // Open-Meteo orchestration
  // --------------------------------------------------------------------
  async function fetchForecast(location) {
    const url = `${FORECAST_URL}?latitude=${location.latitude}&longitude=${location.longitude}` +
      `&timezone=${encodeURIComponent(location.timezone || "UTC")}` +
      `&current=${CURRENT_FIELDS}&hourly=${HOURLY_FIELDS}&daily=${DAILY_FIELDS}` +
      `&forecast_days=${FORECAST_DAYS}`;
    const data = await fetchJSON(url);
    if (!data || !data.current) {
      throw new Error("The weather service returned unexpected data. Please try again.");
    }
    return data;
  }

  async function fetchAirQuality(location) {
    try {
      const url = `${AIR_QUALITY_URL}?latitude=${location.latitude}&longitude=${location.longitude}` +
        `&current=us_aqi,pm2_5,pm10`;
      return await fetchJSON(url);
    } catch (_e) {
      return null;
    }
  }

  // --------------------------------------------------------------------
  // localStorage persistence (mirror SQLite favorites/history services)
  // --------------------------------------------------------------------
  const key = (loc) => `${loc.latitude},${loc.longitude}`;

  function readList(name) {
    try { return JSON.parse(localStorage.getItem(name)) || []; } catch (_e) { return []; }
  }
  function writeList(name, list) {
    try { localStorage.setItem(name, JSON.stringify(list)); } catch (_e) { /* storage full/unavailable */ }
  }

  function favoritesList() { return readList("wv-favorites"); }

  function isFavorite(loc) {
    return favoritesList().some((f) => key(f) === key(loc));
  }

  function toggleFavorite(loc) {
    const list = favoritesList();
    const existing = list.findIndex((f) => key(f) === key(loc));
    if (existing >= 0) {
      list.splice(existing, 1);
      writeList("wv-favorites", list);
      return { removed: true };
    }
    list.unshift({
      name: loc.name || "Unknown",
      country: loc.country || "",
      country_code: loc.country_code || "",
      admin1: loc.admin1 || "",
      latitude: loc.latitude,
      longitude: loc.longitude,
      timezone: loc.timezone || "UTC",
      display_name: loc.display_name || loc.name || "Unknown location",
    });
    writeList("wv-favorites", list);
    return { added: true };
  }

  function historyList() {
    return readList("wv-history").map((e) => ({
      location: e.location,
      searched_at: e.searched_at,
    }));
  }

  function recordHistory(loc) {
    const list = readList("wv-history").filter((e) => key(e.location) !== key(loc));
    list.unshift({ location: loc, searched_at: new Date().toISOString() });
    writeList("wv-history", list.slice(0, HISTORY_LIMIT));
  }

  // --------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------
  const UNITS = {
    metric: ["C", "kmh", "hpa"],
    imperial: ["F", "mph", "inHg"],
  };

  async function weather(query, units) {
    const unitSet = UNITS[units] || UNITS.metric;
    const q = String(query || "").trim();
    if (!q) throw new Error("Please enter a location name");

    const locations = await geocode(q);
    if (!locations.length) {
      throw new Error("We couldn't find that location. Check the spelling or try a nearby city name.");
    }
    const location = locations[0];
    const displayName = [location.name, location.admin1, location.country].filter(Boolean).join(", ") || "Unknown location";

    const payload = await fetchForecast(location);
    const airPayload = await fetchAirQuality(location);

    const w = parseForecast(payload, { ...location, display_name: displayName }, airPayload);
    recordHistory({ ...location, display_name: displayName });
    return serialize(w, unitSet, isFavorite(location));
  }

  return { weather, favorites: favoritesList, toggleFavorite, history: historyList };
})();

window.WV = WV;
