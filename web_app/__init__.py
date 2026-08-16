"""WeatherVision web application (Flask).

Reuses the entire WeatherVision core (API layer, models, services, engines)
and exposes it through a JSON API + a responsive browser frontend. The PySide6
desktop GUI is intentionally NOT imported here; the web layer is the deployed
presentation tier.

Start (local):   flask --app wsgi run
Start (prod):    gunicorn wsgi:app --workers 1 --threads 4 --timeout 30
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

from app.api.errors import (
    CityNotFoundError,
    InvalidResponseError,
    NetworkError,
    RateLimitError,
    WeatherAPIError,
)
from app.config import APP_NAME, APP_SUBTITLE, DB_PATH, SETTINGS_PATH, VERSION
from app.database.database import DatabaseManager
from app.services.alert_engine import AlertEngine
from app.services.cache_service import WeatherCache
from app.services.favorites_service import FavoritesService
from app.services.history_service import HistoryService
from app.services.intelligence_engine import IntelligenceEngine
from app.services.settings_manager import SettingsManager
from app.services.weather_service import WeatherService

_UNITS = {
    "metric": ("C", "kmh", "hpa"),
    "imperial": ("F", "mph", "inHg"),
}

logger = logging.getLogger("weathervision.web")


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config.update(
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=64 * 1024,  # API bodies are tiny
    )

    # --- Services (single instances shared by all threads) ---------------
    db_path = Path(os.getenv("DATABASE_PATH", str(DB_PATH)))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path = Path(os.getenv("SETTINGS_PATH", str(SETTINGS_PATH)))
    db = DatabaseManager(db_path)
    settings = SettingsManager(settings_path)

    demo_from_env = os.getenv("DEMO_MODE") == "1" or os.getenv("WEATHERVISION_DEMO") == "1"
    if demo_from_env:
        settings.set("demo_mode", True)

    # Core services --------------------------------------------------------
    from app.api.geocoding import Geocoder
    from app.api.weather_api import WeatherAPI

    api = WeatherAPI()
    geocoder = Geocoder(api)
    cache = WeatherCache(db)
    favorites = FavoritesService(db)
    history = HistoryService(db)
    intelligence = IntelligenceEngine()
    alerts = AlertEngine()
    service = WeatherService(
        api=api,
        geocoder=geocoder,
        cache=cache,
        history=history,
        settings=settings,
    )

    # --- Page routes ------------------------------------------------------
    @app.route("/")
    def index() -> str:
        return render_template(
            "index.html",
            app_name=APP_NAME,
            app_subtitle=APP_SUBTITLE,
            version=VERSION,
            demo=service.is_demo_mode(),
        )

    @app.route("/health")
    def health() -> dict[str, Any]:
        return {
            "status": "healthy",
            "application": APP_NAME,
            "version": VERSION,
        }

    # --- API routes -------------------------------------------------------
    @app.route("/api/search")
    def api_search() -> dict[str, Any]:
        query = (request.args.get("q") or "").strip()
        if not query:
            return _error("Provide a search query (?q=London).", 400)
        try:
            locations = service.search(query)
        except WeatherAPIError as exc:
            return _api_error(exc)
        return jsonify({"locations": [loc.to_dict() for loc in locations]})

    @app.route("/api/weather")
    def api_weather() -> dict[str, Any]:
        query = (request.args.get("q") or "").strip()
        if not query:
            return _error("Provide a location (?q=London).", 400)
        units = _resolve_units()
        try:
            location, weather = service.fetch_for_query(query)
        except WeatherAPIError as exc:
            return _api_error(exc)

        is_favorite = favorites.contains(location)
        score = intelligence.comfort_score(weather)
        return jsonify(_serialize(weather, units, is_favorite, score))

    @app.route("/api/favorites", methods=["GET", "POST", "DELETE"])
    def api_favorites() -> Any:
        if request.method == "GET":
            return jsonify({
                "favorites": [_location_json(loc) for loc in favorites.list()]
            })
        if request.method == "POST":
            body = request.get_json(silent=True) or {}
            try:
                latitude = float(body["latitude"])
                longitude = float(body["longitude"])
            except (KeyError, TypeError, ValueError):
                return _error("latitude and longitude are required numbers.", 400)
            from app.models.weather_models import Location

            loc = Location(
                name=str(body.get("name") or "Unknown"),
                country=str(body.get("country") or ""),
                country_code=str(body.get("country_code") or ""),
                admin1=str(body.get("admin1") or ""),
                latitude=latitude,
                longitude=longitude,
                timezone=str(body.get("timezone") or "UTC") or "UTC",
            )
            added = favorites.add(loc)
            return jsonify({"added": added, "favorite": _location_json(loc)})
        if request.method == "DELETE":
            body = request.get_json(silent=True) or {}
            try:
                latitude = float(body["latitude"])
                longitude = float(body["longitude"])
            except (KeyError, TypeError, ValueError):
                return _error("latitude and longitude are required numbers.", 400)
            removed = favorites.remove_by_key(latitude, longitude)
            return jsonify({"removed": removed})
        return _error("Method not allowed", 405)

    @app.route("/api/history")
    def api_history() -> Any:
        if request.method == "GET":
            entries = [
                {
                    "location": _location_json(loc),
                    "searched_at": when.isoformat(),
                }
                for loc, when in history.list()
            ]
            return jsonify({"history": entries})
        return _error("Method not allowed", 405)

    @app.route("/api/history", methods=["DELETE"])
    def api_history_clear() -> dict[str, Any]:
        history.clear()
        return jsonify({"cleared": True})

    # --- Error handling ----------------------------------------------------
    @app.errorhandler(404)
    def not_found(_e: Any) -> Any:
        if request.path.startswith("/api/"):
            return _error("Endpoint not found.", 404)
        return render_template(
            "error.html", title="Page not found",
            message="The page you are looking for does not exist.",
        ), 404

    @app.errorhandler(500)
    def internal_error(_e: Any) -> Any:
        logger.exception("Internal server error")
        if request.path.startswith("/api/"):
            return _error("Internal server error.", 500)
        return render_template(
            "error.html", title="Something went wrong",
            message="An unexpected error occurred. Please try again.",
        ), 500

    # --- Request helpers ---------------------------------------------------
    def _resolve_units() -> tuple[str, str, str]:
        requested = request.args.get("units", "metric").strip().lower()
        return _UNITS.get(requested, _UNITS["metric"])

    def _serialize(
        weather: Any,
        units: tuple[str, str, str],
        is_favorite: bool,
        score: Any,
    ) -> dict[str, Any]:
        from web_app.serializers import serialize_weather

        return serialize_weather(
            weather,
            temp_unit=units[0],
            wind_unit=units[1],
            pressure_unit=units[2],
            is_favorite=is_favorite,
            score=score,
            why_lines=intelligence.why(weather),
            activities=intelligence.activity_scores(weather),
            insights=intelligence.insights(weather),
            alerts=alerts.evaluate(weather, score.total),
        )

    def _api_error(exc: WeatherAPIError) -> tuple[dict[str, Any], int]:
        message, status = _error_for(exc)
        return _error(message, status)

    def _error(message: str, status: int) -> tuple[dict[str, Any], int]:
        return jsonify({"error": message}), status

    # Store for shutdown + tests
    app.extensions["db"] = db
    app.extensions["service"] = service
    app.extensions["favorites"] = favorites
    app.extensions["history"] = history
    return app


def _error_for(exc: WeatherAPIError) -> tuple[str, int]:
    """Map typed API errors to (user-friendly message, HTTP status)."""
    if isinstance(exc, CityNotFoundError):
        return (
            "We couldn't find that location. Check the spelling or try a "
            "nearby city name.",
            404,
        )
    if isinstance(exc, RateLimitError):
        return ("Too many requests. Please wait a moment and try again.", 429)
    if isinstance(exc, NetworkError):
        return (
            "Cannot reach the weather server. Please check your internet "
            "connection and try again.",
            502,
        )
    if isinstance(exc, InvalidResponseError):
        return ("The weather service returned unexpected data. Please try again.", 502)
    return ("Something went wrong while fetching weather data.", 502)


def _location_json(loc: Any) -> dict[str, Any]:
    return {
        **loc.to_dict(),
        "display_name": loc.display_name,
        "short_name": loc.short_name,
    }
