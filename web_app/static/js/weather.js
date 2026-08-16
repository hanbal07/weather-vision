/* WeatherVision — static-site data layer (v2).
 *
 * Pure client-side (GitHub Pages): weather data comes directly from
 * Open-Meteo (CORS-enabled, no API key). Favorites and search history live
 * in localStorage instead of SQLite.
 *
 * Correctness rules enforced here:
 *  1. Never invent measurements. If the provider omits a value we render
 *     "Not available" — we never substitute 0, 1013 hPa or "Clear sky".
 *  2. Open-Meteo "current"/"hourly"/"daily"/"sunrise" strings are already in
 *     the location's LOCAL wall-clock timezone. We treat them as literal
 *     wall-clock strings and never run them through an IANA timezone
 *     conversion (that is exactly the bug that shifted every label by the UTC
 *     offset). The only genuinely timezone-aware value is the location's
 *     current wall-clock time ("local time now").
 *  3. "Now" comparisons (current-hour rain probability, hourly window) are
 *     done in the location's local time using utc_offset_seconds.
 *  4. The comfort score only uses measurements that actually exist; weights
 *     are renormalized over the available factors and the payload reports how
 *     many of the six factors were used.
 *
 * Public API:
 *   WV.weather(query, units)            -> Promise<payload>  (+ payload._raw)
 *   WV.serializePayload(raw, units)     -> payload           (no network)
 *   WV.suggest(query)                   -> Promise<[suggestion]>
 *   WV.favorites() / WV.toggleFavorite(loc) / WV.history() / WV.clearHistory()
 *   WV.lastPayload()                    -> serialized payload or null
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
  const CACHE_TTL_MS = 10 * 60 * 1000;      // reuse raw data for 10 minutes
  const APP_VERSION = "2.0.0";

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
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "visibility",
    "uv_index", "dew_point_2m",
  ].join(",");
  const HOURLY_FIELDS = [
    "temperature_2m", "apparent_temperature", "precipitation_probability",
    "precipitation", "weather_code", "wind_speed_10m", "wind_direction_10m",
    "is_day", "visibility",
  ].join(",");
  const DAILY_FIELDS = [
    "weather_code", "temperature_2m_max", "temperature_2m_min",
    "apparent_temperature_max", "precipitation_probability_max",
    "precipitation_sum", "uv_index_max", "sunrise", "sunset",
    "wind_speed_10m_max",
  ].join(",");

  const COORDINATES_RE = /^\s*(-?\d{1,3}(?:\.\d+)?)\s*[,;]\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;
  const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  const NOT_AVAILABLE = "Not available";

  // --------------------------------------------------------------------
  // Null-safe value helpers — the heart of "never invent data".
  // --------------------------------------------------------------------
  /** Return a finite Number, or null when missing / not numeric. */
  function num(v) {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  /** Return a rounded integer, or null when missing. */
  function numInt(v) {
    const n = num(v);
    return n === null ? null : Math.round(n);
  }
  function hasNum(v) { return num(v) !== null; }

  /** Human display string for a numeric value, "Not available" when null. */
  function disp(v, format) {
    return (v === null || v === undefined) ? NOT_AVAILABLE : format(v);
  }

  // Python's round() uses round-half-to-even; keep parity with the backend.
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

  // --------------------------------------------------------------------
  // Local wall-clock handling (see rules 2 & 3 in the header).
  // --------------------------------------------------------------------
  /** "YYYY-MM-DDTHH:00" (UTC string form) for the current LOCAL hour. */
  function localNowHour(utcOffsetSeconds) {
    const offset = numInt(utcOffsetSeconds) || 0;
    return new Date(Date.now() + offset * 1000).toISOString().slice(0, 13) + ":00";
  }
  /** Epoch (ms) of the current local hour in the "wall-clock-as-UTC" frame. */
  function localNowHourMs(utcOffsetSeconds) {
    const offset = numInt(utcOffsetSeconds) || 0;
    return Math.floor((Date.now() + offset * 1000) / 3600000) * 3600000;
  }
  /** Extract "HH:MM" from an Open-Meteo local wall-clock string ("2026-08-16T06:10"). */
  function clockOf(isoLocal) {
    const s = String(isoLocal || "");
    if (s.length < 16) return s;
    return s.slice(11, 16);
  }
  /** Parse a "YYYY-MM-DD" calendar date into {weekday, day, month} parts. */
  function dateParts(dateStr) {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dateStr || ""));
    if (!m) return null;
    const year = +m[1], month = +m[2], day = +m[3];
    const dow = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
    return { weekday: WEEKDAYS[dow], day, month: MONTHS[month - 1], iso: String(dateStr) };
  }

  /** Current wall-clock time in the location's real timezone. */
  function localTimeNow(tz) {
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
  const formatPressure = (hpa, u) => {
    const v = convertPressure(hpa, u);
    return u === "inHg" ? `${v.toFixed(2)} inHg` : `${Math.round(v)} hPa`;
  };
  const convertVisibility = (metres, u) => {
    const km = metres / 1000;
    return u === "mph" ? km * 0.621371 : km;
  };
  const formatVisibility = (metres, u) =>
    `${convertVisibility(metres, u).toFixed(1)} ${u === "mph" ? "mi" : "km"}`;
  const formatDistance = (metres, u) => {
    if (metres >= 1000) return formatVisibility(metres, u);
    return `${Math.round(convertVisibility(metres, u) * (u === "mph" ? 1000 : 1))} ${u === "mph" ? "m" : "m"}`;
  };
  const WIND_DIRECTIONS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  const windDirection = (degrees) => {
    const d = num(degrees);
    if (d === null) return NOT_AVAILABLE;
    return WIND_DIRECTIONS[Math.floor(((d % 360 + 360) % 360 + 11.25) / 22.5) % 16];
  };
  function aqiCategory(aqi) {
    const v = num(aqi);
    if (v === null) return "Unavailable";
    if (v <= 50) return "Good";
    if (v <= 100) return "Moderate";
    if (v <= 150) return "Sensitive";
    if (v <= 200) return "Unhealthy";
    if (v <= 300) return "Very Unhealthy";
    return "Hazardous";
  }
  function aqiColor(aqi) {
    const v = num(aqi);
    if (v === null) return "#64748b";
    if (v <= 50) return "#22c55e";
    if (v <= 100) return "#eab308";
    if (v <= 150) return "#f97316";
    if (v <= 200) return "#ef4444";
    if (v <= 300) return "#a855f7";
    return "#7f1d1d";
  }

  // --------------------------------------------------------------------
  // WMO condition
  // --------------------------------------------------------------------
  function conditionFromCode(code, isDay) {
    const c = numInt(code);
    if (c === null) return { text: NOT_AVAILABLE, icon: "🌡️" };
    const entry = WMO_CODES[c] || ["Unknown", "🌡️", "🌡️"];
    return { text: entry[0], icon: isDay ? entry[1] : entry[2] };
  }

  // --------------------------------------------------------------------
  // Parsing (mirrors app/models/weather_models.py + serializers.py)
  // --------------------------------------------------------------------
  function parseForecast(payload, location, airPayload) {
    const cur = payload.current || {};
    const utcOffset = numInt(payload.utc_offset_seconds);

    // is_day is 1 (day) / 0 (night) / null (unknown). Default to day for the
    // icon choice only when the provider truly omitted it.
    const isDay = numInt(cur.is_day) === null ? true : Boolean(numInt(cur.is_day));
    const code = numInt(cur.weather_code);
    const cond = conditionFromCode(code, isDay);

    const temperature = num(cur.temperature_2m);
    const feelsLike = num(cur.apparent_temperature);
    const humidity = numInt(cur.relative_humidity_2m);
    const windSpeed = num(cur.wind_speed_10m);
    const windGusts = num(cur.wind_gusts_10m);
    const pressure = num(cur.pressure_msl);
    const visibilityM = num(cur.visibility);
    const cloudCover = numInt(cur.cloud_cover);
    const uvIndex = num(cur.uv_index);
    const precipitation = num(cur.precipitation);
    const dewPoint = num(cur.dew_point_2m);

    const { probability: precipProb, hour: precipHour } =
      currentPrecipitationProbability(payload, utcOffset);

    const sunrise = firstDaily(payload.daily, "sunrise");
    const sunset = firstDaily(payload.daily, "sunset");

    const current = {
      temperature,
      feels_like: feelsLike === null ? temperature : feelsLike,
      condition_code: code,
      condition_text: cond.text,
      icon: cond.icon,
      humidity,
      wind_speed: windSpeed,
      wind_direction: numInt(cur.wind_direction_10m),
      wind_gusts: windGusts,
      pressure,
      visibility_m: visibilityM,
      cloud_cover: cloudCover,
      uv_index: uvIndex,
      is_day: isDay,
      precipitation,
      precipitation_probability: precipProb,
      precipitation_period_label: precipHour ? `over the next hour (from ${clockOf(precipHour)})` : "",
      dew_point: dewPoint,
      sunrise,
      sunset,
    };

    return {
      location,
      current,
      hourly: parseHourly(payload, utcOffset),
      daily: parseDaily(payload),
      air_quality: parseAirQuality(airPayload),
      fetched_at: new Date().toISOString(),
      source: "live",
      utc_offset_seconds: utcOffset,
    };
  }

  /** Rain probability for the CURRENT local hour (Open-Meteo only exposes it
   *  inside the hourly arrays; the current block has none). */
  function currentPrecipitationProbability(payload, utcOffset) {
    const hourly = payload.hourly || {};
    const times = hourly.time || [];
    const probs = hourly.precipitation_probability || [];
    if (!times.length || times.length !== probs.length) {
      return { probability: null, hour: null };
    }
    const localNow = localNowHour(utcOffset);
    let firstFuture = null;
    for (let i = 0; i < times.length; i++) {
      const t = String(times[i]);
      if (t.slice(0, 13) === localNow.slice(0, 13)) {
        const p = numInt(probs[i]);
        return { probability: p, hour: t };
      }
      if (t >= localNow && firstFuture === null) firstFuture = i;
    }
    // Hour boundary rolled over mid-request: use the next upcoming hour.
    if (firstFuture !== null) return { probability: numInt(probs[firstFuture]), hour: String(times[firstFuture]) };
    // Nothing in the window (should not happen with forecast_days>=1).
    return { probability: numInt(probs[0]), hour: String(times[0]) };
  }

  function parseHourly(payload, utcOffset) {
    const hourly = payload.hourly || {};
    const times = hourly.time || [];
    if (!times.length) return [];

    const start = localNowHourMs(utcOffset);
    const result = [];
    for (let i = 0; i < times.length; i++) {
      const raw = String(times[i]);
      // Raw times are local wall-clock strings; represent them as-if-UTC so
      // the same "wall clock hour" is comparable with localNowHourMs().
      const epoch = Date.parse(raw + (raw.includes("Z") || /[+-]\d{2}:?\d{2}$/.test(raw) ? "" : "Z"));
      if (Number.isFinite(epoch) && epoch < start) continue;

      const hCode = numInt((hourly.weather_code || [])[i]);
      const hDay = numInt((hourly.is_day || [])[i]) === null ? true : Boolean(numInt((hourly.is_day || [])[i]));
      const hCond = conditionFromCode(hCode, hDay);
      result.push({
        time: raw,
        temperature: num((hourly.temperature_2m || [])[i]),
        feels_like: num((hourly.apparent_temperature || [])[i]),
        precipitation_probability: numInt((hourly.precipitation_probability || [])[i]),
        precipitation: num((hourly.precipitation || [])[i]),
        condition_code: hCode,
        condition_text: hCond.text,
        icon: hCond.icon,
        wind_speed: num((hourly.wind_speed_10m || [])[i]),
        wind_direction: numInt((hourly.wind_direction_10m || [])[i]),
        visibility_m: num((hourly.visibility || [])[i]),
        is_day: hDay,
      });
      if (result.length >= HOURLY_LIMIT) break;
    }
    if (result.length) result[0].is_now = true;
    return result;
  }

  function parseDaily(payload) {
    const daily = payload.daily || {};
    const dates = daily.time || [];
    const result = [];
    for (let i = 0; i < dates.length; i++) {
      const dCode = numInt((daily.weather_code || [])[i]);
      const dCond = conditionFromCode(dCode, true);
      result.push({
        date: String(dates[i]),
        temp_max: num((daily.temperature_2m_max || [])[i]),
        temp_min: num((daily.temperature_2m_min || [])[i]),
        feels_like_max: num((daily.apparent_temperature_max || [])[i]),
        condition_code: dCode,
        condition_text: dCond.text,
        icon: dCond.icon,
        precipitation_probability: numInt((daily.precipitation_probability_max || [])[i]),
        precipitation_sum: num((daily.precipitation_sum || [])[i]),
        uv_index_max: num((daily.uv_index_max || [])[i]),
        wind_max: num((daily.wind_speed_10m_max || [])[i]),
        sunrise: at(daily, "sunrise", i),
        sunset: at(daily, "sunset", i),
      });
    }
    return result;
  }

  function parseAirQuality(airPayload) {
    const cur = (airPayload && airPayload.current) || {};
    const aqi = num(cur.us_aqi);
    if (aqi === null) return null;
    return {
      aqi,
      pm2_5: num(cur.pm2_5),
      pm10: num(cur.pm10),
    };
  }

  const firstDaily = (daily, key) => {
    const v = daily && daily[key];
    if (Array.isArray(v) && v.length) return String(v[0]);
    if (typeof v === "string") return v;
    return "";
  };
  const at = (daily, key, i) => {
    const v = daily && daily[key];
    if (Array.isArray(v) && v[i] !== undefined && v[i] !== null) return String(v[i]);
    return "";
  };

  // --------------------------------------------------------------------
  // Human summary (rule-based, derived only from available data)
  // --------------------------------------------------------------------
  function summarySentence(c) {
    const parts = [];
    if (c.condition_text && c.condition_text !== NOT_AVAILABLE) {
      parts.push(c.condition_text);
    } else if (hasNum(c.temperature)) {
      parts.push("Conditions are currently mixed");
    }
    if (hasNum(c.temperature)) {
      parts.push(`${Math.round(c.temperature)}°`);
    }
    if (hasNum(c.feels_like) && hasNum(c.temperature) && Math.abs(c.feels_like - c.temperature) >= 2) {
      parts.push(`feels like ${Math.round(c.feels_like)}°`);
    }
    let sentence = parts.length ? parts.join(" and ").replace(/ and feels/, ", feels") : "Weather data is not available right now.";
    const extras = [];
    if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 55) {
      extras.push(`rain is likely (${c.precipitation_probability}%)`);
    } else if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 35) {
      extras.push(`a ${c.precipitation_probability}% chance of rain`);
    }
    if (hasNum(c.uv_index) && c.is_day && c.uv_index >= 8) extras.push(`UV index ${c.uv_index.toFixed(1)} — sun protection needed`);
    if (hasNum(c.wind_speed) && c.wind_speed >= 45) extras.push(`wind near ${Math.round(c.wind_speed)} km/h`);
    if (extras.length) {
      sentence += extras.length === 1 ? ` — ${extras[0]}.` : ` — ${extras.join("; ")}.`;
    } else {
      sentence += ".";
    }
    return sentence;
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

  /** UV sub-score; null when UV data is unavailable (factor is then excluded). */
  function uvScore(uv, isDay) {
    const v = num(uv);
    if (v === null) return null;
    if (!isDay) return 100;
    if (v <= 2) return 100;
    if (v <= 5) return 80;
    if (v <= 7) return 60;
    if (v <= 10) return 40;
    return 20;
  }

  const COMFORT_WEIGHTS = {
    temperature: 0.30, humidity: 0.20, wind: 0.15,
    rain: 0.15, visibility: 0.10, uv: 0.10,
  };

  function comfortScore(c) {
    const visKm = hasNum(c.visibility_m) ? c.visibility_m / 1000 : null;

    const factors = [
      {
        key: "temperature", label: "Temperature",
        score: hasNum(c.temperature) ? pyround(rangeScore(c.temperature, 18, 24, 10, 30, 0, 40)) : null,
        value: hasNum(c.temperature) ? `${c.temperature.toFixed(0)}°C` : null,
      },
      {
        key: "humidity", label: "Humidity",
        score: hasNum(c.humidity) ? pyround(rangeScore(c.humidity, 40, 60, 25, 75, 10, 90)) : null,
        value: hasNum(c.humidity) ? `${c.humidity}%` : null,
      },
      {
        key: "wind", label: "Wind",
        score: hasNum(c.wind_speed) ? pyround(rangeScore(c.wind_speed, 0, 25, 45, 70, 90, 110)) : null,
        value: hasNum(c.wind_speed) ? `${c.wind_speed.toFixed(0)} km/h` : null,
      },
      {
        key: "rain", label: "Rain probability",
        score: hasNum(c.precipitation_probability) ? pyround(rainScore(c.precipitation_probability)) : null,
        value: hasNum(c.precipitation_probability) ? `${c.precipitation_probability}%` : null,
      },
      {
        key: "visibility", label: "Visibility",
        score: visKm !== null ? pyround(rangeScore(visKm, 10, 40, 5, 6, 1, 2)) : null,
        value: visKm !== null ? `${visKm.toFixed(1)} km` : null,
      },
      {
        key: "uv", label: "UV index",
        score: uvScore(c.uv_index, c.is_day) === null ? null : Math.round(uvScore(c.uv_index, c.is_day)),
        value: uvValueText(c.uv_index, c.is_day),
      },
    ];

    const available = factors.filter((f) => f.score !== null);
    const weightSum = available.reduce((s, f) => s + COMFORT_WEIGHTS[f.key], 0);

    const components = available.map((f) => {
      const weight = weightSum > 0 ? COMFORT_WEIGHTS[f.key] / weightSum : 0;
      return {
        key: f.key,
        label: f.label,
        score: f.score,
        weight: pyround(weight * 1000) / 1000,
        value: f.value,
        note: factorNote(f.key, c),
      };
    });

    let total = null;
    if (components.length) {
      total = pyround(components.reduce((s, cpt) => s + cpt.score * cpt.weight, 0));
      total = Math.max(0, Math.min(100, total));
    }
    return {
      total,
      grade: total === null ? NOT_AVAILABLE : gradeOf(total),
      grade_label: total === null ? NOT_AVAILABLE : gradeOf(total),
      factor_count: 6,
      available_factors: available.length,
      note: available.length === 6
        ? "Based on all six measurements."
        : `Based on ${available.length} of 6 available measurements — the rest are not provided by the data source.`,
      components,
    };
  }

  function factorNote(key, c) {
    const v = (x) => hasNum(x) ? x : null;
    if (key === "temperature") return temperatureNote(v(c.temperature));
    if (key === "humidity") return humidityNote(v(c.humidity));
    if (key === "wind") return windNote(v(c.wind_speed));
    if (key === "rain") return rainNote(v(c.precipitation_probability));
    if (key === "visibility") return visibilityNote(v(c.visibility_m) !== null ? c.visibility_m / 1000 : null);
    if (key === "uv") return uvNote(c.uv_index, c.is_day);
    return "";
  }
  function temperatureNote(value) {
    if (value <= 18) return `${value.toFixed(0)}°C is cooler than the ideal 18-24°C band.`;
    if (value <= 24) return `Within the ideal 18-24°C range.`;
    if (value <= 30) return `${value.toFixed(0)}°C is a little above the ideal 18-24°C band.`;
    if (value <= 40) return `${value.toFixed(0)}°C is uncomfortably warm for most people.`;
    return `${value.toFixed(0)}°C is extreme heat.`;
  }
  function humidityNote(value) {
    if (value <= 40) return `${value}% humidity is on the dry side.`;
    if (value <= 60) return `Humidity is comfortable (40-60%).`;
    if (value <= 75) return `${value}% humidity feels a little muggy.`;
    if (value <= 90) return `${value}% humidity feels muggy and sticky.`;
    return `${value}% humidity is very high and oppressive.`;
  }
  function windNote(value) {
    if (value <= 25) return `Wind is light (${value.toFixed(0)} km/h).`;
    if (value <= 45) return `${value.toFixed(0)} km/h wind is noticeable but fine.`;
    if (value <= 70) return `${value.toFixed(0)} km/h wind makes outdoor activity harder.`;
    if (value <= 90) return `${value.toFixed(0)} km/h wind is strong.`;
    return `${value.toFixed(0)} km/h wind is dangerously strong.`;
  }
  function rainNote(value) {
    if (value <= 15) return `Very low chance of rain (${value}%).`;
    if (value <= 45) return `${value}% rain probability — minor uncertainty.`;
    if (value <= 70) return `${value}% rain probability — moderate chance of rain.`;
    return `${value}% rain probability — rain is likely.`;
  }
  function visibilityNote(value) {
    if (value >= 10) return `Visibility is excellent (${value.toFixed(1)} km).`;
    if (value >= 5) return `${value.toFixed(1)} km visibility is acceptable.`;
    if (value >= 2) return `${value.toFixed(1)} km visibility limits long-distance views.`;
    return `${value.toFixed(1)} km visibility is very poor.`;
  }
  function uvValueText(uv, isDay) {
    const v = num(uv);
    if (v === null) return null;
    return (isDay ? v.toFixed(1) : v.toFixed(0));
  }
  function uvNote(uv, isDay) {
    const v = num(uv);
    if (v === null) return null;
    if (!isDay) return "Night time — UV risk is negligible.";
    if (v <= 2) return `UV index ${v.toFixed(1)} is low — sun is safe.`;
    if (v <= 5) return `UV index ${v.toFixed(1)} is moderate — light sun protection advised.`;
    if (v <= 7) return `UV index ${v.toFixed(1)} is high — sun protection required.`;
    if (v <= 10) return `UV index ${v.toFixed(1)} is very high — use SPF 30+, a hat and sunglasses.`;
    return `UV index ${v.toFixed(1)} is extreme — avoid prolonged exposure.`;
  }

  // --------------------------------------------------------------------
  // "Why this forecast?" — structured, plain-language explanation
  // --------------------------------------------------------------------
  function whyLines(c, score) {
    const lines = [];
    if (score.total === null) {
      lines.push({
        title: "Score unavailable",
        body: "None of the six weather measurements are currently provided by the data source, so no comfort score could be computed.",
      });
      return lines;
    }
    lines.push({
      title: `${score.total}/100 — ${score.grade}`,
      body: score.available_factors === 6
        ? "The Weather Comfort Score weighs six measurements of the current conditions."
        : `The Weather Comfort Score weighs the ${score.available_factors} of six measurements that are currently available.`,
    });
    for (const cpt of score.components) {
      lines.push({
        title: `${cpt.label} — ${cpt.value}`,
        body: `${cpt.note} Contribution ${pyround(cpt.score * cpt.weight)}/${pyround(cpt.weight * 100)} of the score.`,
      });
    }
    if (score.total >= 61) {
      lines.push({ title: "Bottom line", body: "Overall the conditions are pleasant for most outdoor activities." });
    } else if (score.total >= 41) {
      lines.push({ title: "Bottom line", body: "Conditions are mixed — plan around the weakest factors listed above." });
    } else {
      lines.push({ title: "Bottom line", body: "Conditions are poor for general outdoor activity. See the activity planner." });
    }
    return lines;
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

  function activityFactor(spec, c) {
    const [tl, th] = spec.temp;
    const factors = {
      temperature: hasNum(c.temperature)
        ? rangeScore(c.temperature, tl, th, tl - 8, th + 8, tl - 16, th + 16) : null,
      rain: hasNum(c.precipitation_probability)
        ? rangeScore(c.precipitation_probability, 0, spec.rain_max, spec.rain_max, spec.rain_max + 30, spec.rain_max + 40, spec.rain_max + 70) : null,
      wind: hasNum(c.wind_speed)
        ? rangeScore(c.wind_speed, 0, spec.wind_max, spec.wind_max, spec.wind_max + 25, spec.wind_max + 40, spec.wind_max + 60) : null,
    };
    const [hl, hh] = spec.humidity;
    factors.humidity = hasNum(c.humidity)
      ? rangeScore(c.humidity, hl, hh, hl - 15, hh + 15, hl - 30, hh + 30) : null;
    const uv = uvScore(c.uv_index, c.is_day);
    factors.uv = uv === null ? null : Math.min(uv,
      rangeScore(c.uv_index, 0, spec.uv_max, spec.uv_max, spec.uv_max + 3, spec.uv_max + 6, spec.uv_max + 9));
    const visKm = hasNum(c.visibility_m) ? c.visibility_m / 1000 : null;
    factors.visibility = visKm === null ? null
      : rangeScore(visKm, spec.visibility_min, 40, spec.visibility_min - 2, 6, spec.visibility_min - 4, 2);
    return factors;
  }

  function activityScores(c) {
    const results = [];
    for (const [name, spec] of Object.entries(ACTIVITY_SPECS)) {
      const factors = activityFactor(spec, c);
      const available = Object.keys(ACTIVITY_WEIGHTS).filter((k) => factors[k] !== null);
      const weightSum = available.reduce((s, k) => s + ACTIVITY_WEIGHTS[k], 0);
      let total = pyround(available.reduce((s, k) =>
        s + factors[k] * (ACTIVITY_WEIGHTS[k] / weightSum), 0));
      total = Math.max(0, Math.min(100, total));
      results.push({ name, icon: spec.icon, score: total, label: activityLabel(total), reasons: activityReasons(name, factors, c) });
    }
    results.sort((a, b) => b.score - a.score);
    return results;
  }

  function activityReasons(name, factors, c) {
    const penalties = Object.entries(factors)
      .filter(([, score]) => score !== null && score < 100)
      .sort((a, b) => a[1] - b[1]);
    const reasons = [];
    for (const [label] of penalties.slice(0, 2)) {
      if (label === "temperature") reasons.push(`Temperature ${Math.round(c.temperature)}°C is not ideal for ${name.toLowerCase()}.`);
      else if (label === "rain") reasons.push(`${c.precipitation_probability}% rain chance affects ${name.toLowerCase()}.`);
      else if (label === "wind") reasons.push(`Wind of ${Math.round(c.wind_speed)} km/h is a factor.`);
      else if (label === "uv") reasons.push("UV exposure needs consideration.");
      else if (label === "visibility") reasons.push("Visibility is limited.");
      else if (label === "humidity") reasons.push("Humidity affects comfort.");
    }
    return reasons.length ? reasons : ["All relevant weather factors are favourable."];
  }

  function activityVerdict(best) {
    if (best === null) return { icon: "🛰️", text: "No data", detail: "No activity guidance yet — weather data is unavailable." };
    if (best.score >= 80) return { icon: "👍", text: "Great for today", detail: `${best.name} and similar outdoor plans are well-suited to the current conditions.` };
    if (best.score >= 60) return { icon: "🙂", text: "Good for today", detail: `Outdoor plans like ${best.name.toLowerCase()} should be fine in the current conditions.` };
    if (best.score >= 40) return { icon: "😐", text: "Mixed today", detail: `Conditions are workable, but ${best.name.toLowerCase()} needs some planning around the weather.` };
    if (best.score >= 20) return { icon: "🌧️", text: "Poor for today", detail: `Current conditions are not ideal for ${best.name.toLowerCase()} or similar outdoor plans.` };
    return { icon: "🚫", text: "Not recommended", detail: "Current conditions are very poor for outdoor activity." };
  }

  // --------------------------------------------------------------------
  // "What matters today" — short, prioritized insights (max 4)
  // --------------------------------------------------------------------
  const SEVERITY_RANK = { INFO: 0, LOW: 1, MODERATE: 2, HIGH: 3, CRITICAL: 4 };

  function insights(c) {
    const visKm = hasNum(c.visibility_m) ? c.visibility_m / 1000 : null;
    const out = [];

    if (hasNum(c.temperature)) {
      if (c.temperature >= 35) out.push(ins("🌡️", "Extreme heat", `${Math.round(c.temperature)}°C is very hot — stay hydrated, seek shade and limit exertion.`, "HIGH"));
      else if (c.temperature >= 30) out.push(ins("🌡️", "Hot conditions", `At ${Math.round(c.temperature)}°C it is hot — plan outdoor time for cooler hours.`, "MODERATE"));
      else if (c.temperature <= -5) out.push(ins("🥶", "Bitter cold", `${Math.round(c.temperature)}°C — dress in layers and keep skin covered.`, "HIGH"));
      else if (c.temperature <= 5) out.push(ins("🥶", "Cold conditions", `Only ${Math.round(c.temperature)}°C — warm clothing recommended.`, "MODERATE"));
    }

    if (hasNum(c.feels_like) && hasNum(c.temperature) && c.feels_like - c.temperature >= 3) {
      out.push(ins("💧", "Feels hotter than it is", `It feels like ${Math.round(c.feels_like)}°C — ${c.humidity}% humidity makes it muggy.`, "MODERATE"));
    }

    if (hasNum(c.condition_code)) {
      if (THUNDERSTORM_CODES.has(c.condition_code)) {
        out.push(ins("⛈️", "Thunderstorm", "Thunderstorm conditions detected. Avoid open areas and stay indoors.", "CRITICAL"));
      } else if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 80) {
        out.push(ins("🌧️", "Rain is very likely", `Rain chance is ${c.precipitation_probability}% — carry an umbrella.`, "HIGH"));
      } else if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 55) {
        out.push(ins("☔", "Possible rain", `Rain chance is ${c.precipitation_probability}% — consider an umbrella.`, "MODERATE"));
      } else if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 35) {
        out.push(ins("🌦️", "Slight rain chance", `A ${c.precipitation_probability}% chance of rain exists today.`, "LOW"));
      }
    }
    if (hasNum(c.condition_code) && SNOW_CODES.has(c.condition_code)) {
      out.push(ins("❄️", "Snow conditions", "Snow is falling or forecast — expect slippery surfaces.", "MODERATE"));
    }

    if (hasNum(c.wind_speed)) {
      if (c.wind_speed >= 50) out.push(ins("🌬️", "Strong wind", hasNum(c.wind_gusts)
        ? `Wind near ${Math.round(c.wind_speed)} km/h, gusts to ${Math.round(c.wind_gusts)} km/h — secure loose items.`
        : `Wind near ${Math.round(c.wind_speed)} km/h — secure loose items.`, "HIGH"));
      else if (c.wind_speed >= 32) out.push(ins("🌬️", "Breezy", `${Math.round(c.wind_speed)} km/h wind — noticeable during outdoor activity.`, "LOW"));
    }

    if (hasNum(c.uv_index) && c.is_day) {
      if (c.uv_index >= 11) out.push(ins("☀️", "Extreme UV", `UV index ${c.uv_index.toFixed(1)} — avoid the sun between 11:00-15:00.`, "HIGH"));
      else if (c.uv_index >= 8) out.push(ins("☀️", "High UV", `UV index ${c.uv_index.toFixed(1)} — use SPF 30+, a hat and sunglasses.`, "MODERATE"));
      else if (c.uv_index >= 6) out.push(ins("☀️", "Moderate UV", `UV index ${c.uv_index.toFixed(1)} — light sun protection advised.`, "LOW"));
    }

    if (visKm !== null) {
      if (visKm < 2) out.push(ins("🌫️", "Very poor visibility", `Visibility is only ${visKm.toFixed(1)} km — drive with extreme care.`, "HIGH"));
      else if (visKm < 5) out.push(ins("🌫️", "Reduced visibility", `Visibility is ${visKm.toFixed(1)} km — take care on the roads.`, "MODERATE"));
    }

    if (hasNum(c.temperature)) {
      out.push(clothingInsight(c));
    }

    out.sort((a, b) => SEVERITY_RANK[b.level] - SEVERITY_RANK[a.level]);
    return out.slice(0, 4);
  }

  const ins = (icon, title, message, level) => ({ icon, title, message, level });

  function clothingInsight(c) {
    const t = c.temperature;
    let msg;
    if (t >= 28) msg = "Light clothing is suitable — use sun protection outdoors.";
    else if (t >= 18) msg = "Light-to-medium clothing is comfortable.";
    else if (t >= 10) msg = "Medium clothing recommended; a light jacket may help.";
    else if (t >= 2) msg = "Warm clothing recommended.";
    else msg = "Heavy winter clothing is strongly recommended.";
    if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 55) {
      msg += " Rain protection would be useful.";
    }
    return ins("👕", "Clothing", msg, "INFO");
  }

  // --------------------------------------------------------------------
  // Alerts (mirror app/services/alert_engine.py) — meaningful warnings only
  // --------------------------------------------------------------------
  function evaluateAlerts(c, daily, scoreTotal) {
    const visKm = hasNum(c.visibility_m) ? c.visibility_m / 1000 : null;
    const alerts = [];

    if (hasNum(c.condition_code) && RAIN_CODES.has(c.condition_code) && hasNum(c.precipitation) && c.precipitation >= 2.5) {
      alerts.push(alert("HIGH", "🌧️", "Heavy rain", `Rainfall rate is ${c.precipitation.toFixed(1)} mm/h — seek shelter and take care on the roads.`));
    } else if (hasNum(c.precipitation_probability) && c.precipitation_probability >= 85) {
      alerts.push(alert("MODERATE", "🌧️", "High rain probability", `There is a ${c.precipitation_probability}% chance of rain over the next hour.`));
    }

    if (hasNum(c.condition_code) && THUNDERSTORM_CODES.has(c.condition_code)) {
      alerts.push(alert("CRITICAL", "⛈️", "Thunderstorm", "Thunderstorm conditions are present. Avoid open areas, tall objects and water."));
    }

    if (hasNum(c.temperature)) {
      if (c.temperature >= 35) alerts.push(alert("HIGH", "🌡️", "Extreme heat", `Temperature reached ${Math.round(c.temperature)}°C — stay hydrated and limit exposure.`));
      else if (c.temperature <= -5) alerts.push(alert("HIGH", "🥶", "Extreme cold", `Temperature is ${Math.round(c.temperature)}°C — dress warmly and limit exposure.`));
    }

    if (hasNum(c.uv_index) && c.is_day && c.uv_index >= 8) {
      alerts.push(alert(c.uv_index >= 10 ? "HIGH" : "MODERATE", "☀️", "High UV index", `UV index is ${c.uv_index.toFixed(1)} — use sunscreen, sunglasses and a hat.`));
    }

    if (hasNum(c.wind_speed) && c.wind_speed >= 45) {
      const gusts = hasNum(c.wind_gusts) ? ` (gusts to ${Math.round(c.wind_gusts)} km/h)` : "";
      alerts.push(alert(c.wind_speed >= 60 ? "HIGH" : "MODERATE", "🌬️", "Strong wind", `Wind speed is ${Math.round(c.wind_speed)} km/h${gusts}.`));
    }

    if (visKm !== null) {
      if (visKm < 2) alerts.push(alert("HIGH", "🌫️", "Very poor visibility", `Visibility is only ${visKm.toFixed(1)} km — travel with extreme caution.`));
      else if (visKm < 5) alerts.push(alert("MODERATE", "🌫️", "Reduced visibility", `Visibility is ${visKm.toFixed(1)} km — allow extra distance on the road.`));
    }

    if (scoreTotal !== null) {
      if (scoreTotal <= 25) alerts.push(alert("HIGH", "🚫", "Very poor outdoor conditions", `The Weather Comfort Score is ${scoreTotal}/100 — outdoor activity is discouraged.`));
      else if (scoreTotal <= 40) alerts.push(alert("MODERATE", "⚠️", "Poor outdoor conditions", `The Weather Comfort Score is ${scoreTotal}/100 — plan indoor alternatives.`));
    }

    if (daily.length >= 2) {
      const tomorrow = daily[1];
      if (hasNum(tomorrow.precipitation_probability) && tomorrow.precipitation_probability >= 75) {
        alerts.push(alert("LOW", "🗓️", "Rain expected tomorrow",
          `There is a ${tomorrow.precipitation_probability}% chance of rain tomorrow (${dateParts(tomorrow.date) ? dateParts(tomorrow.date).weekday : tomorrow.date}).`));
      }
    }

    alerts.sort((a, b) => SEVERITY_RANK[b.level] - SEVERITY_RANK[a.level]);
    return alerts;
  }

  const alert = (level, icon, title, message) => ({ level, icon, title, message });

  // --------------------------------------------------------------------
  // Serialization (mirror web_app/serializers.py)
  // --------------------------------------------------------------------
  function serializePayload(raw, unitSet, isFavorite) {
    const c = raw.current;
    const loc = raw.location;
    const [tempUnit, windUnit, pressureUnit] = unitSet;
    const tz = loc.timezone || "UTC";

    const pct = (v) => disp(v, (x) => `${x}%`);
    const mm = (v) => disp(v, (x) => `${x.toFixed(1)} mm`);

    const current = {
      temperature: c.temperature === null ? null : pyround(c.temperature, 1),
      temperature_display: disp(c.temperature, (x) => formatTemp(x, tempUnit)),
      feels_like: c.feels_like === null ? null : pyround(c.feels_like, 1),
      feels_like_display: disp(c.feels_like, (x) => formatTemp(x, tempUnit)),
      condition: c.condition_text,
      icon: c.icon,
      humidity: c.humidity,
      humidity_display: pct(c.humidity),
      pressure: c.pressure,
      pressure_display: disp(c.pressure, (x) => formatPressure(x, pressureUnit)),
      wind: c.wind_speed,
      wind_display: disp(c.wind_speed, (x) => formatWind(x, windUnit)),
      wind_direction: windDirection(c.wind_direction),
      wind_gusts: c.wind_gusts,
      wind_gusts_display: disp(c.wind_gusts, (x) => formatWind(x, windUnit)),
      visibility: c.visibility_m,
      visibility_display: disp(c.visibility_m, (x) => formatVisibility(x, windUnit)),
      visibility_km: c.visibility_m === null ? null : pyround(c.visibility_m / 1000, 1),
      uv: c.uv_index,
      uv_display: c.uv_index === null ? NOT_AVAILABLE : (c.is_day ? c.uv_index.toFixed(1) : c.uv_index.toFixed(0)),
      precipitation: c.precipitation,
      precipitation_display: mm(c.precipitation),
      precipitation_probability: c.precipitation_probability,
      precipitation_probability_display: disp(c.precipitation_probability, (x) => `${x}%`),
      precipitation_period_label: c.precipitation_period_label || "",
      cloud_cover: c.cloud_cover,
      cloud_cover_display: pct(c.cloud_cover),
      dew_point: c.dew_point,
      dew_point_display: disp(c.dew_point, (x) => formatTemp(x, tempUnit)),
      sunrise: clockOf(c.sunrise),
      sunset: clockOf(c.sunset),
      is_day: c.is_day,
    };

    const hourly = raw.hourly.map((h) => ({
      time: clockOf(h.time),
      iso: h.time,
      icon: h.icon,
      condition: h.condition_text,
      is_now: Boolean(h.is_now),
      temperature: h.temperature === null ? null : pyround(h.temperature, 1),
      temperature_display: disp(h.temperature, (x) => formatTemp(x, tempUnit)),
      feels_like: h.feels_like === null ? null : pyround(h.feels_like, 1),
      feels_like_display: disp(h.feels_like, (x) => formatTemp(x, tempUnit)),
      precip_prob: h.precipitation_probability,
      precipitation: h.precipitation,
      precipitation_display: mm(h.precipitation),
      wind: h.wind_speed,
      wind_display: disp(h.wind_speed, (x) => formatWind(x, windUnit)),
      wind_direction: windDirection(h.wind_direction),
      visibility: h.visibility_m,
      visibility_display: disp(h.visibility_m, (x) => formatVisibility(x, windUnit)),
      is_day: h.is_day,
    }));

    const daily = raw.daily.map((d) => {
      const dp = dateParts(d.date) || { weekday: "—", day: "—", month: "—", iso: d.date };
      return {
        day: dp.weekday,
        date: `${dp.month} ${dp.day}`,
        iso: dp.iso,
        icon: d.icon,
        condition: d.condition_text,
        high: d.temp_max === null ? null : pyround(d.temp_max, 1),
        low: d.temp_min === null ? null : pyround(d.temp_min, 1),
        high_display: disp(d.temp_max, (x) => formatTemp(x, tempUnit)),
        low_display: disp(d.temp_min, (x) => formatTemp(x, tempUnit)),
        feels_like_max: d.feels_like_max === null ? null : pyround(d.feels_like_max, 1),
        feels_like_max_display: disp(d.feels_like_max, (x) => formatTemp(x, tempUnit)),
        precip_prob: d.precipitation_probability,
        precipitation_sum: d.precipitation_sum,
        precipitation_sum_display: disp(d.precipitation_sum, (x) => `${x.toFixed(1)} mm`),
        uv: d.uv_index_max,
        uv_display: d.uv_index_max === null ? NOT_AVAILABLE : d.uv_index_max.toFixed(1),
        wind_max: d.wind_max,
        wind_max_display: disp(d.wind_max, (x) => formatWind(x, windUnit)),
        sunrise: clockOf(d.sunrise),
        sunset: clockOf(d.sunset),
      };
    });

    const airQuality = raw.air_quality
      ? {
          aqi: raw.air_quality.aqi,
          label: aqiCategory(raw.air_quality.aqi),
          color: aqiColor(raw.air_quality.aqi),
          pm25: raw.air_quality.pm2_5,
          pm25_display: raw.air_quality.pm2_5 === null ? NOT_AVAILABLE : `${raw.air_quality.pm2_5.toFixed(1)} µg/m³`,
          pm10: raw.air_quality.pm10,
          pm10_display: raw.air_quality.pm10 === null ? NOT_AVAILABLE : `${raw.air_quality.pm10.toFixed(1)} µg/m³`,
          note: "US AQI — Open-Meteo Air Quality API",
        }
      : null;

    const score = comfortScore(c);
    const activities = activityScores(c);
    const scoreTotal = score.total;
    const alerts = evaluateAlerts(c, raw.daily, scoreTotal);

    return {
      meta: {
        app: "WeatherVision",
        version: APP_VERSION,
        source: raw.source,
        demo: raw.source === "demo",
        fetched_at: raw.fetched_at,
        is_favorite: isFavorite,
        data_note: "Latest available observations and model data",
        attribution: "Open-Meteo",
      },
      location: {
        name: loc.name, country: loc.country, country_code: loc.country_code,
        admin1: loc.admin1, latitude: loc.latitude, longitude: loc.longitude,
        timezone: loc.timezone, population: loc.population,
        display_name: loc.display_name,
        local_time: localTimeNow(tz),
        utc_offset_seconds: raw.utc_offset_seconds,
      },
      units: { temp: tempUnit, wind: windUnit, pressure: pressureUnit },
      current,
      hourly,
      daily,
      air_quality: airQuality,
      summary: summarySentence(c),
      score: {
        total: score.total,
        grade: score.grade,
        grade_label: score.grade,
        color: score.total === null ? "#64748b" : (GRADE_COLORS[score.grade] || "#64748b"),
        factor_count: score.factor_count,
        available_factors: score.available_factors,
        note: score.note,
        components: score.components.map((cpt) => ({
          key: cpt.key, label: cpt.label, score: cpt.score,
          weight: cpt.weight, value: cpt.value, note: cpt.note,
        })),
      },
      why: whyLines(c, score),
      insights: insights(c).map((i) => ({
        icon: i.icon, title: i.title, message: i.message, level: i.level,
        color: LEVEL_COLORS[i.level] || "#64748b",
      })),
      activity: {
        verdict: activityVerdict(activities.length ? activities[0] : null),
        items: activities.map((a) => ({
          name: a.name, icon: a.icon, score: a.score, label: a.label, reasons: a.reasons,
        })),
      },
      activities: activities.map((a) => ({
        name: a.name, icon: a.icon, score: a.score, label: a.label, reasons: a.reasons,
      })),
      alerts: alerts.map((a) => ({
        level: a.level, icon: a.icon, title: a.title, message: a.message,
        color: LEVEL_COLORS[a.level] || "#64748b",
      })),
    };
  }

  // --------------------------------------------------------------------
  // Geocoding & suggestions
  // --------------------------------------------------------------------
  function detectCoordinates(text) {
    const match = COORDINATES_RE.exec(text);
    if (!match) return null;
    const lat = parseFloat(match[1]);
    const lon = parseFloat(match[2]);
    if (lat < -90 || lat > 90 || lon < -180 || lon > 180) return null;
    return [lat, lon];
  }

  function mapGeocodeResult(r, coords) {
    if (coords) {
      return {
        name: `${coords[0].toFixed(2)}, ${coords[1].toFixed(2)}`,
        country: "Coordinates",
        country_code: "",
        admin1: "",
        latitude: coords[0],
        longitude: coords[1],
        timezone: "UTC",
        population: null,
      };
    }
    return {
      name: r.name || "Unknown",
      country: r.country || "",
      country_code: r.country_code || "",
      admin1: r.admin1 || "",
      latitude: Number(r.latitude) || 0,
      longitude: Number(r.longitude) || 0,
      timezone: r.timezone || "UTC",
      population: r.population === undefined ? null : Number(r.population),
    };
  }

  async function geocode(query, count = 8) {
    const coords = detectCoordinates(query);
    if (coords) return [mapGeocodeResult(null, coords)];
    const url = `${GEOCODING_URL}?name=${encodeURIComponent(query)}&count=${count}&language=en&format=json`;
    const data = await fetchJSON(url);
    const results = data && data.results;
    if (!results || !results.length) return [];
    return results.slice(0, count).map((r) => mapGeocodeResult(r, null));
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
  // Flask API layer (web_app variant).
  //
  // The server performs geocoding, forecasting and SQLite favorites/history;
  // this layer preserves the exact same payload contract and public API as the
  // static GitHub-Pages build, so app.js / charts.js are shared verbatim.
  // --------------------------------------------------------------------
  const API_WEATHER = "/api/weather";
  const API_SEARCH = "/api/search";
  const API_FAVORITES = "/api/favorites";
  const API_HISTORY = "/api/history";

  const keyOf = (loc) => `${loc.latitude},${loc.longitude}`;

  async function fetchAPI(url, options) {
    let res;
    try {
      res = await fetch(url, options);
    } catch (_e) {
      throw new Error("Cannot reach the weather server. Please check your internet connection and try again.");
    }
    let data = {};
    try { data = await res.json(); } catch (_e) { /* fallthrough */ }
    if (!res.ok) {
      throw new Error((data && data.error) || "The weather service returned unexpected data. Please try again.");
    }
    return data;
  }

  // Rebuild the "raw metric snapshot" shape consumed by serializePayload() so
  // client-side unit switches work exactly like on the static site.
  function rawFromPayload(p) {
    const cur = p.current || {};
    const loc = p.location || {};
    const arr = (v) => Array.isArray(v) ? v : [];
    return {
      location: {
        name: loc.name, country: loc.country, country_code: loc.country_code,
        admin1: loc.admin1, latitude: loc.latitude, longitude: loc.longitude,
        timezone: loc.timezone, population: loc.population,
        display_name: loc.display_name,
        utc_offset_seconds: loc.utc_offset_seconds,
      },
      current: {
        temperature: cur.temperature,
        feels_like: cur.feels_like,
        condition_code: null,
        condition_text: cur.condition,
        icon: cur.icon,
        humidity: cur.humidity,
        wind_speed: cur.wind,
        wind_direction: cur.wind_direction_deg,
        wind_gusts: cur.wind_gusts,
        pressure: cur.pressure,
        visibility_m: cur.visibility,
        cloud_cover: cur.cloud_cover,
        uv_index: cur.uv,
        is_day: cur.is_day,
        precipitation: cur.precipitation,
        precipitation_probability: cur.precipitation_probability,
        precipitation_period_label: cur.precipitation_period_label || "",
        dew_point: cur.dew_point,
        sunrise: cur.sunrise || "",
        sunset: cur.sunset || "",
      },
      hourly: arr(p.hourly).map((h) => ({
        time: h.iso || "",
        temperature: h.temperature,
        feels_like: h.feels_like,
        precipitation_probability: h.precip_prob,
        precipitation: h.precipitation,
        condition_text: h.condition,
        icon: h.icon,
        wind_speed: h.wind,
        wind_direction: h.wind_direction_deg,
        visibility_m: h.visibility,
        is_day: h.is_day,
        is_now: Boolean(h.is_now),
      })),
      daily: arr(p.daily).map((d) => ({
        date: d.iso || "",
        temp_max: d.high,
        temp_min: d.low,
        feels_like_max: d.feels_like_max,
        condition_text: d.condition,
        icon: d.icon,
        precipitation_probability: d.precip_prob,
        precipitation_sum: d.precipitation_sum,
        uv_index_max: d.uv,
        wind_max: d.wind_max,
        sunrise: d.sunrise || "",
        sunset: d.sunset || "",
      })),
      air_quality: p.air_quality
        ? { aqi: p.air_quality.aqi, pm2_5: p.air_quality.pm25, pm10: p.air_quality.pm10 }
        : null,
      fetched_at: (p.meta && p.meta.fetched_at) || new Date().toISOString(),
      source: (p.meta && p.meta.source) || "live",
      utc_offset_seconds: loc.utc_offset_seconds,
    };
  }

  // --------------------------------------------------------------------
  // Favorites / history (server-backed, mirrored locally for instant UI)
  // --------------------------------------------------------------------
  let favCache = [];
  let histCache = [];

  function favorites() { return favCache; }
  function isFavorite(loc) { return favCache.some((f) => keyOf(f) === keyOf(loc)); }
  function history() { return histCache; }

  async function refreshFavorites() {
    try {
      const data = await fetchAPI(API_FAVORITES);
      favCache = (data && data.favorites) || [];
    } catch (_e) { favCache = []; }
  }
  async function refreshHistory() {
    try {
      const data = await fetchAPI(API_HISTORY);
      histCache = (data && data.history) || [];
    } catch (_e) { histCache = []; }
  }

  function toggleFavorite(loc) {
    const existing = favCache.findIndex((f) => keyOf(f) === keyOf(loc));
    if (existing >= 0) {
      favCache.splice(existing, 1);
      fetch(API_FAVORITES, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ latitude: loc.latitude, longitude: loc.longitude }),
      }).catch(() => {});
      return { removed: true };
    }
    favCache.unshift({
      name: loc.name || "Unknown", country: loc.country || "", country_code: loc.country_code || "",
      admin1: loc.admin1 || "", latitude: loc.latitude, longitude: loc.longitude,
      timezone: loc.timezone || "UTC",
      display_name: loc.display_name || loc.name || "Unknown location",
    });
    fetch(API_FAVORITES, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(favCache[0]),
    }).catch(() => {});
    return { added: true };
  }

  function recordHistory(loc) {
    histCache = histCache.filter((e) => keyOf(e.location) !== keyOf(loc));
    histCache.unshift({ location: loc, searched_at: new Date().toISOString() });
    histCache = histCache.slice(0, HISTORY_LIMIT);
  }

  function clearHistory() {
    histCache = [];
    fetch(API_HISTORY, { method: "DELETE" }).catch(() => {});
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

    const data = await fetchAPI(`${API_WEATHER}?q=${encodeURIComponent(q)}&units=metric`);
    const raw = rawFromPayload(data);
    const payload = serializePayload(raw, unitSet, Boolean(data.meta && data.meta.is_favorite));
    payload._raw = raw;
    recordHistory(raw.location);
    return payload;
  }

  function serializePayloadPublic(raw, units) {
    const unitSet = UNITS[units] || UNITS.metric;
    const payload = serializePayload(raw, unitSet, isFavorite(raw.location));
    payload._raw = raw;
    return payload;
  }

  async function suggest(query) {
    const q = String(query || "").trim();
    if (!q) return [];
    const data = await fetchAPI(`${API_SEARCH}?q=${encodeURIComponent(q)}`);
    return (data && data.locations) || [];
  }

  function lastPayload() {
    try {
      const entry = JSON.parse(localStorage.getItem("wv-last-payload") || "null");
      return entry || null;
    } catch (_e) {
      return null;
    }
  }
  function saveLastPayload(payload) {
    try {
      localStorage.setItem("wv-last-payload", JSON.stringify({
        ...payload, _raw: undefined,
      }));
    } catch (_e) { /* ignore */ }
  }

  // Preload server-side favorites/history for the initial render.
  refreshFavorites();
  refreshHistory();

  return {
    weather,
    serializePayload: serializePayloadPublic,
    suggest,
    favorites,
    toggleFavorite,
    history,
    clearHistory,
    lastPayload,
    saveLastPayload,
  };
})();

window.WV = WV;
