"""Weather alert engine.

Generates warnings ONLY when the actual weather data satisfies documented
thresholds. Severity levels: INFO < LOW < MODERATE < HIGH < CRITICAL.

Warnings never appear out of thin air - every alert is a pure function of the
measured / forecast values, so they are easy to justify during a viva.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.models.weather_models import WeatherData
from app.utils.helpers import RAIN_CODES, THUNDERSTORM_CODES

SEVERITY_ORDER = {"INFO": 0, "LOW": 1, "MODERATE": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass
class WeatherAlert:
    level: str
    icon: str
    title: str
    message: str


class AlertEngine:
    """Evaluates a :class:`WeatherData` snapshot against alert thresholds."""

    # Documented thresholds -------------------------------------------------
    HEAVY_RAIN_MM = 2.5          # mm per hour
    EXTREME_HEAT_C = 35
    EXTREME_COLD_C = -5
    HIGH_UV = 8.0
    STRONG_WIND_KMH = 45
    POOR_VISIBILITY_KM = 5.0
    VERY_POOR_VISIBILITY_KM = 2.0

    def evaluate(self, weather: WeatherData, comfort_score: int) -> list[WeatherAlert]:
        """Return alerts derived from the current conditions and today's forecast."""
        cur = weather.current
        alerts: list[WeatherAlert] = []
        vis_km = cur.visibility_m / 1000.0

        # --- Heavy rain ----------------------------------------------------
        if cur.condition_code in RAIN_CODES and cur.precipitation >= self.HEAVY_RAIN_MM:
            alerts.append(WeatherAlert(
                "HIGH", "🌧️", "Heavy rain",
                f"Rainfall rate is {cur.precipitation:.1f} mm/h. Seek shelter and take care on the roads.",
            ))
        elif cur.precipitation_probability >= 85:
            alerts.append(WeatherAlert(
                "MODERATE", "🌧️", "High rain probability",
                f"There is a {cur.precipitation_probability}% chance of rain soon.",
            ))

        # --- Thunderstorm --------------------------------------------------
        if cur.condition_code in THUNDERSTORM_CODES:
            alerts.append(WeatherAlert(
                "CRITICAL", "⛈️", "Thunderstorm",
                "Thunderstorm conditions are present. Avoid open areas, tall objects and water.",
            ))

        # --- Extreme temperature --------------------------------------------
        if cur.temperature >= self.EXTREME_HEAT_C:
            alerts.append(WeatherAlert(
                "HIGH", "🌡️", "Extreme heat",
                f"Temperature reached {cur.temperature:.0f}°C. Stay hydrated and limit exposure.",
            ))
        elif cur.temperature <= self.EXTREME_COLD_C:
            alerts.append(WeatherAlert(
                "HIGH", "🥶", "Extreme cold",
                f"Temperature dropped to {cur.temperature:.0f}°C. Dress warmly and limit exposure.",
            ))

        # --- High UV ----------------------------------------------------------
        if cur.uv_index is not None and cur.is_day and cur.uv_index >= self.HIGH_UV:
            alerts.append(WeatherAlert(
                "HIGH" if cur.uv_index >= 10 else "MODERATE",
                "☀️", "High UV index",
                f"UV index is {cur.uv_index:.1f}. Use sunscreen, sunglasses and a hat.",
            ))

        # --- Strong wind --------------------------------------------------------
        if cur.wind_speed >= self.STRONG_WIND_KMH:
            alerts.append(WeatherAlert(
                "HIGH" if cur.wind_speed >= 60 else "MODERATE",
                "🌬️", "Strong wind",
                f"Wind speed is {cur.wind_speed:.0f} km/h (gusts to {cur.wind_gusts:.0f} km/h).",
            ))

        # --- Poor visibility ----------------------------------------------------
        if vis_km < self.VERY_POOR_VISIBILITY_KM:
            alerts.append(WeatherAlert(
                "HIGH", "🌫️", "Very poor visibility",
                f"Visibility is only {vis_km:.1f} km. Travel with extreme caution.",
            ))
        elif vis_km < self.POOR_VISIBILITY_KM:
            alerts.append(WeatherAlert(
                "MODERATE", "🌫️", "Reduced visibility",
                f"Visibility is {vis_km:.1f} km. Allow extra distance on the road.",
            ))

        # --- Poor overall comfort ------------------------------------------------
        if comfort_score <= 25:
            alerts.append(WeatherAlert(
                "HIGH", "🚫", "Very poor outdoor conditions",
                f"The Weather Comfort Score is {comfort_score}/100. Outdoor activity is discouraged.",
            ))
        elif comfort_score <= 40:
            alerts.append(WeatherAlert(
                "MODERATE", "⚠️", "Poor outdoor conditions",
                f"The Weather Comfort Score is {comfort_score}/100. Plan indoor alternatives.",
            ))

        # --- Tomorrow's heavy rain (advance notice) -------------------------------
        if len(weather.daily) >= 2:
            tomorrow = weather.daily[1]
            if tomorrow.precipitation_probability >= 75:
                alerts.append(WeatherAlert(
                    "LOW", "🗓️", "Rain expected tomorrow",
                    f"There is a {tomorrow.precipitation_probability}% chance of rain tomorrow "
                    f"({tomorrow.date}). Plan accordingly.",
                ))

        alerts.sort(key=lambda a: SEVERITY_ORDER[a.level], reverse=True)
        return alerts
