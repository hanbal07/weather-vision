# 🌤️ WeatherVision — Real-Time Weather Intelligence System

> A modern, explainable weather intelligence platform — available as a **responsive web application** and a **desktop GUI (PySide6)**.

**WeatherVision does not merely answer *"What is the weather?"* — it answers *"What does this weather mean for me?"* and *"Why did the application reach this conclusion?"***

Traditional weather apps mostly display raw numbers. WeatherVision converts raw weather data into a **Weather Comfort Score (0–100)**, **activity recommendations**, **severity-based alerts** and human-readable **insights** — every conclusion derived from real measured values through transparent, documented rules.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Active-brightgreen)]()
[![Tests](https://img.shields.io/badge/Tests-58%20passing-brightgreen)]()

> Note: the **Tests** badge reflects the suite included in this repository (run `pytest` locally to reproduce). Deployment status is shown in the **Live Demo** section.

---

## 🚀 Live Demo

**[➡️ Open the live application](https://hanbal07.github.io/weather-vision/)**

> **Status:** Live and verified — served from GitHub Pages (`gh-pages` branch, zero-cost, no billing info required). The static build in [`site/`](site) replicates the full WeatherVision experience entirely in the browser: it calls **Open-Meteo directly** (CORS-enabled, no API key) and stores favorites/history in `localStorage`. The Flask web app in `web_app/` remains the backend version for local deployment (see [Deployment](#deployment)).

---

## ✨ Features

| Area | Details |
|---|---|
| **Real-time weather** | Current conditions + hourly + **7-day forecast** + air quality + UV + sunrise/sunset + visibility |
| **Location system** | Search by city / country / region or **coordinates** (e.g. `31.55, 74.34`); favorites ⭐; recent-search history |
| **Weather Intelligence** | Rule-based insights: heat, rain, wind, UV, visibility, clothing and travel guidance |
| **Weather Comfort Score** | 0–100 score from six weighted factors with a **"Why this forecast?"** explainability dialog |
| **Activity Planner** | Suitability scores for Walking, Running, Cycling, Photography, Picnic, Travel, Study, Sports — with reasons |
| **Weather Alerts** | Threshold-based warnings with severity INFO → CRITICAL (never fabricated) |
| **Charts** | Interactive temperature / precipitation / wind charts (Chart.js, theme-aware) |
| **Unit conversion** | °C/°F, km/h/mph, hPa/inHg — applied across the whole UI, including charts |
| **Dark / light themes** | Persistent theme toggle (localStorage) |
| **Offline cache** | SQLite cache + clear "Offline Mode — showing data from X ago" banner |
| **Demo Mode** | Realistic mock data labelled **DEMO DATA — NOT REAL-TIME**, no internet needed |
| **Responsive UI** | Desktop, tablet and mobile layouts |
| **Production ready** | Flask + Gunicorn, `/health` endpoint, environment-based config, no debug mode, no hard-coded secrets |

---

## 🖼️ Screenshots

> Insert real screenshots after deployment (e.g. `docs/dashboard-dark.png`, `docs/dashboard-light.png`, `docs/mobile.png`).

| Desktop — dark | Desktop — light | Mobile |
|---|---|---|
| _(insert screenshot)_ | _(insert screenshot)_ | _(insert screenshot)_ |

---

## 🧰 Technology Stack

### Web application (deployed)
- **Python 3.11**
- **Flask 3.1** — web framework
- **Gunicorn** — production WSGI server (1 worker + threads; SQLite is safe)
- **requests** — HTTP client for the weather API
- **Chart.js 4** — charts (vendored locally, no CDN dependency)
- **SQLite** (stdlib) — favorites, history, offline cache
- **python-dotenv** — environment configuration
- **tzdata** — timezone database (required on Windows and slim Linux containers)

### Desktop application (original GUI, in the same repository)
- **PySide6 (Qt)** with **custom QPainter charts** (no chart library)

### Weather data
- **Open-Meteo** — free, keyless forecast + geocoding + air-quality APIs

---

## 🏗️ Architecture

```
┌────────────────────┐      ┌──────────────────────────────────────────────┐
│  Browser frontend  │ HTTP │  Flask web layer (wsgi.py → web_app/)        │
│  HTML + CSS + JS   │─────▶│  routes · serializers · templates · static   │
└────────────────────┘      └──────────────┬───────────────────────────────┘
                                           │ reuses 100% of the core
                    ┌──────────────────────▼───────────────────────────────┐
                    │  WeatherVision core (framework-agnostic)             │
                    │  app/api · app/models · app/services · app/database  │
                    │  app/utils                                           │
                    │                                                      │
                    │  • WeatherService   orchestrates fetch → validate →  │
                    │                     cache → history                  │
                    │  • IntelligenceEngine  scores, activities, insights, │
                    │                     "Why?"                           │
                    │  • AlertEngine      threshold-based alerts           │
                    └──────────────────────┬───────────────────────────────┘
                                           │
                          ┌────────────────┴────────────────┐
                          │  Open-Meteo API (external)      │
                          │  SQLite (favorites/history/cache)│
                          └─────────────────────────────────┘
```

**Layering rule:** `app/api`, `app/models`, `app/database`, `app/services`, `app/utils` are GUI-free. The desktop UI lives in `app/ui/` (PySide6) and is **never imported** by the web app — both presentation layers share the same core, so the weather intelligence is identical everywhere.

```
weather-vision/
├── wsgi.py                  Flask entry point (gunicorn wsgi:app)
├── web_app/                 web presentation layer
│   ├── __init__.py          app factory + JSON API routes
│   ├── serializers.py       domain models → JSON (unit-aware)
│   ├── templates/           index.html, error.html
│   └── static/              css/ · js/ · vendor/ (Chart.js) · favicon.svg
├── app/                     core logic (shared by web + desktop)
│   ├── config.py            paths, API endpoints, constants
│   ├── api/                 Open-Meteo client, geocoding, mock data, errors
│   ├── models/              WeatherData, Location, … (validated dataclasses)
│   ├── database/            thread-safe SQLite manager
│   ├── services/            weather orchestration, intelligence, alerts, …
│   ├── ui/                  PySide6 desktop GUI (original application)
│   └── utils/               units, validators, helpers
├── tests/                   58 tests (fully offline)
├── main.py                  desktop GUI entry point
├── requirements.txt         web production dependencies
├── Procfile                 gunicorn start command
├── runtime.txt              Python version (Render)
├── nixpacks.toml            Python version + start command (Railway/Nixpacks)
├── render.yaml              Render blueprint
├── .env.example             documented environment variables
└── .gitignore
```

---

## 🌦️ Weather API

WeatherVision uses **[Open-Meteo](https://open-meteo.com/)** — a free, open weather API that requires **no API key**:

- **Forecast:** `https://api.open-meteo.com/v1/forecast` (current + hourly + daily)
- **Geocoding:** `https://geocoding-api.open-meteo.com/v1/search`
- **Air quality:** `https://air-quality-api.open-meteo.com/v1/air-quality`

The project still supports `WEATHER_API_KEY` so it can be extended to a keyed provider (e.g. OpenWeatherMap) without code changes — the key is only ever read from environment/`.env`, never committed.

---

## 📦 Installation (local development)

```bash
# 1. Clone the repository
git clone https://github.com/YOUR_USERNAME/weather-vision.git
cd weather-vision

# 2. Create a virtual environment
python -m venv .venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # macOS / Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) create your environment file
copy .env.example .env        # Windows
cp .env.example .env          # macOS / Linux
```

## 🔑 Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `WEATHER_API_KEY` | Optional key for a keyed weather provider | *(empty — Open-Meteo needs none)* |
| `APP_THEME` | Initial desktop theme (`dark`/`light`) | `dark` |
| `DEMO_MODE` | `1` = use realistic mock data, no internet | `0` |
| `PORT` | Port the web server binds to (set by hosting platform) | `8000` |
| `DATABASE_PATH` | SQLite path (e.g. `/data/weathervision.db`) | `./data/weathervision.db` |
| `FLASK_DEBUG` | `1` enables Flask debug mode (**never in production**) | `0` |

Never put real secrets in committed files. Locally use `.env` (git-ignored); on the hosting platform use its environment variable / secret store.

## ▶️ How to run

### Web application (localhost)

```bash
flask --app wsgi run
# or
python wsgi.py
```

Open http://localhost:8000 (or the port printed by Flask).

### Desktop GUI (original PySide6 application)

```bash
pip install PySide6-Essentials
python main.py
```

### Demo mode (no internet)

```bash
set DEMO_MODE=1            # Windows
export DEMO_MODE=1         # macOS / Linux
flask --app wsgi run
```

---

## 🧪 Testing

```bash
python -m pytest tests -q
```

**58 tests**, all offline (mocks / demo mode / stubbed geocoder):

- Units & conversions (`test_units.py`)
- Weather Comfort Score math (`test_intelligence_engine.py`)
- Alert thresholds (`test_alert_engine.py`)
- Weather service: parsing, caching, offline fallback, demo mode (`test_weather_service.py`)
- Settings, favorites, history persistence (`test_settings_and_favorites.py`)
- Web layer: pages, `/health`, JSON API, units, favorites, error handling (`test_web.py`)

---

## ☁️ Deployment

The presentation layer is a **web application** (PySide6 cannot run on a cloud host). Two deployment paths are provided:

### 1) GitHub Pages — the live demo (zero-cost, no billing)

The **static site** in [`site/`](site) is already deployed to the `gh-pages` branch and is live at **[https://hanbal07.github.io/weather-vision/](https://hanbal07.github.io/weather-vision/)**. It needs no server:

- `site/js/weather.js` is a client-side port of the Flask backend — it calls **Open-Meteo directly** (geocoding, forecast, air-quality; CORS-enabled, no API key) and reproduces the same scoring, activities, insights, alerts and unit conversion in the browser.
- Favorites and search history use `localStorage` instead of SQLite.
- To redeploy: commit changes under `site/`, push to `gh-pages`:
  ```bash
  git checkout gh-pages        # or build a scratch branch from site/
  # copy site/* to the branch root, commit, push
  ```
  GitHub Pages then re-serves automatically.

### 2) Flask backend (Render / Railway)

| Platform | Config files | Why |
|---|---|---|
| **Render** | `render.yaml`, `runtime.txt` | Free web service, GitHub auto-deploy, HTTPS, `/health` checks, environment variables, logs, blueprints |
| **Railway** | `nixpacks.toml`, `Procfile` | Python auto-detection, `$PORT`, GitHub deploys, volumes for persistent disk |

> Note: Render now requires a card on file even for free web services; the static GitHub Pages route above is the no-billing alternative.

#### Steps (Render)

1. Push this repository to GitHub.
2. In Render → **New → Web Service → Connect GitHub repository**.
3. Render detects `render.yaml` → fill in the service name.
4. Add any environment variables you need (e.g. `DEMO_MODE`).
5. Deploy. Render runs `pip install -r requirements.txt` then `gunicorn wsgi:app --bind 0.0.0.0:$PORT …`.
6. Open the generated `https://<service>.onrender.com` URL and verify `/health`.

#### Steps (Railway)

1. Push this repository to GitHub.
2. In Railway → **New Project → Deploy from GitHub repo**.
3. Railway's Nixpacks reads `nixpacks.toml`, installs requirements and runs the `Procfile` start command.
4. The `PORT` variable is injected automatically.
5. Open the generated `https://<project>.up.railway.app` URL and verify `/health`.

### Production configuration notes

- Debug mode is off; errors return friendly JSON/HTML pages.
- Gunicorn runs **1 worker with 4 threads** — SQLite (single connection + RLock) is safe with this model.
- API timeouts are enforced (15 s) with a small retry policy for transient 5xx responses.

### Database persistence (important)

Favorites, search history and the offline cache live in **SQLite** (`DATABASE_PATH`, default `./data/weathervision.db`).

- **Render free tier / Railway default:** the filesystem is **ephemeral** — the database resets on each redeploy. This is acceptable for a demo.
- **To persist:** attach a **volume** and set `DATABASE_PATH` to a path on it, e.g. `/data/weathervision.db` on Railway, or use Render's **Persistent Disk**. The database schema is created automatically on first start.

---

## 🧠 Weather Intelligence algorithm

**Weather Comfort Score (0–100).** Six factors, each mapped to a 0–100 sub-score by piecewise-linear anchors — `100` inside the ideal band, `70` at warning bounds, `40` at extreme bounds, `0` beyond extremes:

| Factor | Weight | Ideal band | Warning | Extreme |
|---|---|---|---|---|
| Temperature | 0.30 | 18–24 °C | 10 / 30 °C | 0 / 40 °C |
| Humidity | 0.20 | 40–60 % | 25 / 75 % | 10 / 90 % |
| Wind | 0.15 | 0–25 km/h | 45 / 70 | 90 / 110 |
| Rain probability | 0.15 | 0 % | — | 100 % (score = 100 − probability) |
| Visibility | 0.10 | ≥ 10 km | 5–6 km | 1–2 km |
| UV index | 0.10 | ≤ 2 | 3–5 → 80 | ≥ 11 → 20 |

**Score = round(Σ weight × sub-score)** → grades: `0–20 Very Poor · 21–40 Poor · 41–60 Moderate · 61–80 Good · 81–100 Excellent`.

**"Why this forecast?"** shows the total, each factor's measured value, its rule-based note and its weighted contribution — the entire reasoning chain.

**Alerts** are generated only when data crosses documented thresholds (heavy rain ≥ 2.5 mm/h, ≥ 35 °C, UV ≥ 8, wind ≥ 45 km/h, visibility < 5 km, thunderstorms, low comfort, tomorrow's rain), each with a severity level.

**Activity Planner** scores eight activities using activity-specific ideal ranges and weights (temperature 0.35, rain 0.25, wind 0.15, humidity 0.10, UV 0.10, visibility 0.05); the two largest deductions are shown as reasons on each card.

---

## 📄 Project structure

See [Architecture](#architecture) for the annotated tree.

---

## ⚠️ Known limitations

- **Ephemeral SQLite** on free-tier hosting — favorites/history reset on redeploy unless a persistent volume is attached.
- Open-Meteo provides **no historical** weather; long-range (10+ day) forecasts are not available.
- The intelligence engine's explanatory text uses the metric system even when the UI shows imperial units (same behaviour as the desktop app).
- Charts require JavaScript; the page still works without it for current conditions and forecast cards.
- Free hosting plans may be rate-limited by the platform (not by Open-Meteo).

---

## 🗓️ Future improvements

1. Persistent database via PostgreSQL (or mounted volume) for durable favorites/history.
2. Multi-location dashboard grid with saved layout.
3. Push notifications / web-push weather alerts.
4. Historical weather comparisons (this week vs. last year).
5. Radar / satellite map view.
6. PDF report export for the Activity Planner.
7. Provider abstraction for OpenWeatherMap / WeatherAPI.com.
8. i18n (multiple languages) and additional unit locales.
9. PWA installability + offline-first service worker using the SQLite cache.
10. Automated end-to-end browser tests (Playwright) run in CI.

---

© 2026 WeatherVision Project — academic project. Weather data by [Open-Meteo](https://open-meteo.com/).
