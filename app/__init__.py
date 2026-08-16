"""WeatherVision application package.

Modules are organised into clear layers:

    api/        - external data sources (Open-Meteo, geocoding, demo mock)
    database/   - SQLite persistence
    models/     - domain objects (dataclasses)
    services/   - business logic (weather, cache, favorites, history,
                  settings, intelligence engine, alert engine)
    ui/         - PySide6 widgets and application windows
    utils/      - unit conversion, validation and formatting helpers
"""

__version__ = "2.0.0"
