"""Weather Intelligence Engine.

This is the 'explainable AI' heart of WeatherVision. Instead of inventing
random statements it derives every conclusion from the actual weather values
through transparent, documented rules:

* ``comfort_score`` -- a 0-100 Weather Comfort Score from six weighted factors.
* ``activity_scores`` -- per-activity suitability for 8 common activities.
* ``insights`` -- rule-based, human-readable weather intelligence.
* ``why`` -- the reasoning behind the score (powering the 'Why this forecast?'
  button), generated from the same values and rules.

Scoring formulas
================
Every factor maps a measurement to a 0-100 sub-score through piecewise-linear
anchors: ``100`` inside the ideal band, ``70`` at the warning bounds, ``40`` at
the extreme bounds and ``0`` beyond the extremes.

Comfort score weights (sums to 1.0):
    temperature 0.30   humidity  0.20   wind  0.15
    rain        0.15   visibility 0.10   uv    0.10
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.weather_models import WeatherData
from app.utils.helpers import RAIN_CODES, SNOW_CODES, THUNDERSTORM_CODES

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass
class ScoreComponent:
    label: str
    score: int          # 0-100
    weight: float       # 0..1
    value: str          # human readable measurement
    note: str           # why this score (used by the "Why?" feature)

    @property
    def weighted(self) -> float:
        return self.score * self.weight


@dataclass
class ScoreResult:
    total: int
    grade: str
    grade_label: str
    components: list[ScoreComponent] = field(default_factory=list)


@dataclass
class Insight:
    icon: str
    title: str
    message: str
    level: str = "INFO"  # INFO | LOW | MODERATE | HIGH | CRITICAL


@dataclass
class ActivityResult:
    name: str
    icon: str
    score: int
    label: str
    reasons: list[str]


GRADE_BANDS = [
    (81, "Excellent", "Excellent"),
    (61, "Good", "Good"),
    (41, "Moderate", "Moderate"),
    (21, "Poor", "Poor"),
    (0, "Very Poor", "Very Poor"),
]


# ---------------------------------------------------------------------------
# Factor scoring helpers
# ---------------------------------------------------------------------------
def _lerp(value: float, a: float, b: float, score_a: float, score_b: float) -> float:
    if b == a:
        return score_a
    ratio = (value - a) / (b - a)
    return score_a + (score_b - score_a) * max(0.0, min(1.0, ratio))


def _range_score(
    value: float,
    ideal_lo: float,
    ideal_hi: float,
    warn_lo: float,
    warn_hi: float,
    extreme_lo: float,
    extreme_hi: float,
) -> float:
    """Piecewise-linear score from four anchor bands (see module docstring)."""
    if ideal_lo <= value <= ideal_hi:
        return 100.0
    if value < extreme_lo or value > extreme_hi:
        return 0.0
    if warn_lo <= value < ideal_lo:
        return _lerp(value, warn_lo, ideal_lo, 70.0, 100.0)
    if ideal_hi < value <= warn_hi:
        return _lerp(value, ideal_hi, warn_hi, 100.0, 70.0)
    if extreme_lo <= value < warn_lo:
        return _lerp(value, extreme_lo, warn_lo, 40.0, 70.0)
    return _lerp(value, warn_hi, extreme_hi, 70.0, 40.0)


def _rain_score(probability: int) -> float:
    return max(0.0, 100.0 - probability)


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------
class IntelligenceEngine:
    """Translates raw weather values into scores, insights and explanations."""

    # Comfort factors ---------------------------------------------------
    COMFORT_FACTORS = (
        ("temperature", "Temperature", 0.30),
        ("humidity", "Humidity", 0.20),
        ("wind", "Wind", 0.15),
        ("rain", "Rain probability", 0.15),
        ("visibility", "Visibility", 0.10),
        ("uv", "UV index", 0.10),
    )

    # Activities --------------------------------------------------------
    ACTIVITY_SPECS: dict[str, dict[str, Any]] = {
        "Walking": {
            "icon": "🚶",
            "temp": (12, 28),
            "humidity": (30, 75),
            "wind_max": 35,
            "rain_max": 50,
            "uv_max": 7,
            "visibility_min": 5,
        },
        "Running": {
            "icon": "🏃",
            "temp": (10, 25),
            "humidity": (30, 65),
            "wind_max": 38,
            "rain_max": 40,
            "uv_max": 6,
            "visibility_min": 5,
        },
        "Cycling": {
            "icon": "🚴",
            "temp": (12, 30),
            "humidity": (30, 70),
            "wind_max": 42,
            "rain_max": 45,
            "uv_max": 7,
            "visibility_min": 8,
        },
        "Outdoor Photography": {
            "icon": "📷",
            "temp": (0, 35),
            "humidity": (25, 85),
            "wind_max": 48,
            "rain_max": 30,
            "uv_max": 10,
            "visibility_min": 10,
        },
        "Picnic": {
            "icon": "🧺",
            "temp": (18, 30),
            "humidity": (30, 65),
            "wind_max": 25,
            "rain_max": 25,
            "uv_max": 7,
            "visibility_min": 8,
        },
        "Travel": {
            "icon": "✈️",
            "temp": (5, 35),
            "humidity": (20, 80),
            "wind_max": 55,
            "rain_max": 60,
            "uv_max": 10,
            "visibility_min": 6,
        },
        "Outdoor Study": {
            "icon": "📚",
            "temp": (15, 32),
            "humidity": (30, 70),
            "wind_max": 32,
            "rain_max": 35,
            "uv_max": 8,
            "visibility_min": 5,
        },
        "Sports": {
            "icon": "⚽",
            "temp": (12, 28),
            "humidity": (35, 70),
            "wind_max": 35,
            "rain_max": 40,
            "uv_max": 7,
            "visibility_min": 8,
        },
    }
    ACTIVITY_WEIGHTS = {
        "temperature": 0.35,
        "rain": 0.25,
        "wind": 0.15,
        "humidity": 0.10,
        "uv": 0.10,
        "visibility": 0.05,
    }

    # ------------------------------------------------------------------
    # Comfort score
    # ------------------------------------------------------------------
    def comfort_score(self, weather: WeatherData) -> ScoreResult:
        cur = weather.current
        components: list[ScoreComponent] = []

        temp_score = _range_score(cur.temperature, 18, 24, 10, 30, 0, 40)
        components.append(ScoreComponent(
            "Temperature", round(temp_score), 0.30,
            f"{cur.temperature:.0f}°C",
            self._temperature_note(cur.temperature, temp_score),
        ))

        hum_score = _range_score(cur.humidity, 40, 60, 25, 75, 10, 90)
        components.append(ScoreComponent(
            "Humidity", round(hum_score), 0.20,
            f"{cur.humidity}%",
            self._humidity_note(cur.humidity, hum_score),
        ))

        wind_score = _range_score(cur.wind_speed, 0, 25, 45, 70, 90, 110)
        components.append(ScoreComponent(
            "Wind", round(wind_score), 0.15,
            f"{cur.wind_speed:.0f} km/h",
            self._wind_note(cur.wind_speed, wind_score),
        ))

        rain_value = _rain_score(cur.precipitation_probability)
        components.append(ScoreComponent(
            "Rain probability", round(rain_value), 0.15,
            f"{cur.precipitation_probability}%",
            self._rain_note(cur.precipitation_probability, rain_value),
        ))

        vis_km = cur.visibility_m / 1000.0
        vis_score = _range_score(vis_km, 10, 40, 5, 6, 1, 2)
        components.append(ScoreComponent(
            "Visibility", round(vis_score), 0.10,
            f"{vis_km:.1f} km",
            self._visibility_note(vis_km, vis_score),
        ))

        uv_score = self._uv_score(cur.uv_index, cur.is_day)
        components.append(ScoreComponent(
            "UV index", round(uv_score), 0.10,
            self._uv_value_text(cur.uv_index, cur.is_day),
            self._uv_note(cur.uv_index, cur.is_day, uv_score),
        ))

        total = round(sum(c.weighted for c in components))
        total = max(0, min(100, total))
        grade, label = self._grade(total)
        return ScoreResult(total=total, grade=grade, grade_label=label, components=components)

    @staticmethod
    def _grade(score: int) -> tuple[str, str]:
        for bound, grade, label in GRADE_BANDS:
            if score >= bound:
                return grade, label
        return "Very Poor", "Very Poor"

    # ------------------------------------------------------------------
    # Note builders (used by score + "Why?" feature)
    # ------------------------------------------------------------------
    @staticmethod
    def _temperature_note(value: float, score: float) -> str:
        if 18 <= value <= 24:
            return "Within the ideal 18-24°C range - no penalty."
        if score >= 70:
            return f"{value:.0f}°C is slightly outside the ideal 18-24°C band."
        if score >= 40:
            return f"{value:.0f}°C is uncomfortable for most people."
        return f"{value:.0f}°C is extreme - a major comfort penalty."

    @staticmethod
    def _humidity_note(value: int, score: float) -> str:
        if 40 <= value <= 60:
            return "Humidity is comfortable (40-60%)."
        if score >= 70:
            return f"{value}% humidity is a little outside the comfortable band."
        if score >= 40:
            return f"{value}% humidity feels muggy or dry - reduces comfort."
        return f"{value}% humidity is extreme - serious comfort impact."

    @staticmethod
    def _wind_note(value: float, score: float) -> str:
        if value <= 25:
            return "Wind is light - no penalty."
        if score >= 70:
            return f"{value:.0f} km/h wind is noticeable but acceptable."
        if score >= 40:
            return f"{value:.0f} km/h wind makes outdoor activity harder."
        return f"{value:.0f} km/h wind is strong and disruptive."

    @staticmethod
    def _rain_note(value: int, score: float) -> str:
        if value <= 15:
            return "Very low chance of rain."
        if value <= 45:
            return f"{value}% rain probability - minor uncertainty."
        if value <= 70:
            return f"{value}% rain probability - moderate chance of rain."
        return f"{value}% rain probability - rain is likely."

    @staticmethod
    def _visibility_note(value: float, score: float) -> str:
        if value >= 10:
            return "Visibility is excellent (10+ km)."
        if score >= 70:
            return f"{value:.1f} km visibility is acceptable."
        if score >= 40:
            return f"{value:.1f} km visibility limits long-distance views."
        return f"{value:.1f} km visibility is very poor."

    @staticmethod
    def _uv_score(uv: float | None, is_day: bool) -> float:
        if uv is None:
            return 100.0
        if not is_day:
            return 100.0
        if uv <= 2:
            return 100.0
        if uv <= 5:
            return 80.0
        if uv <= 7:
            return 60.0
        if uv <= 10:
            return 40.0
        return 20.0

    @staticmethod
    def _uv_value_text(uv: float | None, is_day: bool) -> str:
        if uv is None:
            return "n/a"
        return f"{uv:.0f}" if not is_day else f"{uv:.1f}"

    @staticmethod
    def _uv_note(uv: float | None, is_day: bool, score: float) -> str:
        if uv is None:
            return "UV data unavailable - no penalty applied."
        if not is_day:
            return "Night time - UV risk is negligible."
        if score == 100:
            return f"UV index {uv:.1f} is low - sun is safe."
        if score >= 60:
            return f"UV index {uv:.1f} is moderate - light sun protection advised."
        if score >= 40:
            return f"UV index {uv:.1f} is high - sun protection required."
        return f"UV index {uv:.1f} is very high - avoid prolonged exposure."

    # ------------------------------------------------------------------
    # "Why this forecast?" explanation
    # ------------------------------------------------------------------
    def why(self, weather: WeatherData) -> list[str]:
        """Human-readable reasoning behind the comfort score."""
        result = self.comfort_score(weather)
        lines = [
            f"Weather Comfort Score = {result.total}/100 ({result.grade}).",
            "The score is computed from six weather factors, each contributing "
            "a weighted penalty:",
        ]
        for comp in result.components:
            lines.append(
                f"• {comp.label} ({comp.value}): {comp.note} "
                f"[contribution {round(comp.weighted)}/{round(comp.weight * 100)}]"
            )
        if result.total >= 61:
            lines.append("Overall the conditions are pleasant for most outdoor activities.")
        elif result.total >= 41:
            lines.append("Conditions are mixed - plan activities around the weakest factors above.")
        else:
            lines.append("Conditions are poor for general outdoor activity. See the activity planner.")
        return lines

    # ------------------------------------------------------------------
    # Activity planner
    # ------------------------------------------------------------------
    def activity_scores(self, weather: WeatherData) -> list[ActivityResult]:
        cur = weather.current
        vis_km = cur.visibility_m / 1000.0
        results: list[ActivityResult] = []

        for name, spec in self.ACTIVITY_SPECS.items():
            factors: dict[str, float] = {}

            temp_lo, temp_hi = spec["temp"]
            factors["temperature"] = _range_score(
                cur.temperature, temp_lo, temp_hi, temp_lo - 8, temp_hi + 8,
                temp_lo - 16, temp_hi + 16,
            )
            factors["rain"] = _range_score(
                cur.precipitation_probability, 0, spec["rain_max"],
                spec["rain_max"], spec["rain_max"] + 30, spec["rain_max"] + 40,
                spec["rain_max"] + 70,
            )
            factors["wind"] = _range_score(
                cur.wind_speed, 0, spec["wind_max"],
                spec["wind_max"], spec["wind_max"] + 25,
                spec["wind_max"] + 40, spec["wind_max"] + 60,
            )
            hum_lo, hum_hi = spec["humidity"]
            factors["humidity"] = _range_score(
                cur.humidity, hum_lo, hum_hi, hum_lo - 15, hum_hi + 15,
                hum_lo - 30, hum_hi + 30,
            )
            uv_score = self._uv_score(cur.uv_index, cur.is_day)
            factors["uv"] = min(
                uv_score,
                _range_score(
                    cur.uv_index if cur.uv_index is not None else 0,
                    0, spec["uv_max"], spec["uv_max"], spec["uv_max"] + 3,
                    spec["uv_max"] + 6, spec["uv_max"] + 9,
                ),
            )
            factors["visibility"] = _range_score(
                vis_km, spec["visibility_min"], 40,
                spec["visibility_min"] - 2, 6, spec["visibility_min"] - 4, 2,
            )

            total = round(
                sum(factors[k] * self.ACTIVITY_WEIGHTS[k] for k in self.ACTIVITY_WEIGHTS)
            )
            total = max(0, min(100, total))

            label = self._activity_label(total)
            reasons = self._activity_reasons(name, factors, cur)
            results.append(ActivityResult(name=name, icon=spec["icon"], score=total, label=label, reasons=reasons))

        # Best first.
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    @staticmethod
    def _activity_label(score: int) -> str:
        if score >= 80:
            return "Great"
        if score >= 60:
            return "Good"
        if score >= 40:
            return "Fair"
        if score >= 20:
            return "Poor"
        return "Very poor"

    @staticmethod
    def _activity_reasons(
        name: str, factors: dict[str, float], cur: Any
    ) -> list[str]:
        """Explain the two biggest deductions for an activity."""
        penalties = [
            (label, score)
            for label, score in factors.items()
            if score < 100
        ]
        penalties.sort(key=lambda item: item[1])
        reasons = []
        for label, score in penalties[:2]:
            if label == "temperature":
                reasons.append(f"Temperature {cur.temperature:.0f}°C is not ideal for {name.lower()}.")
            elif label == "rain":
                reasons.append(f"{cur.precipitation_probability}% rain chance affects {name.lower()}.")
            elif label == "wind":
                reasons.append(f"Wind of {cur.wind_speed:.0f} km/h is a factor.")
            elif label == "uv":
                reasons.append("UV exposure needs consideration.")
            elif label == "visibility":
                reasons.append("Visibility is limited.")
            elif label == "humidity":
                reasons.append("Humidity affects comfort.")
        return reasons or ["All weather factors are favourable."]

    # ------------------------------------------------------------------
    # Insights
    # ------------------------------------------------------------------
    def insights(self, weather: WeatherData) -> list[Insight]:
        cur = weather.current
        vis_km = cur.visibility_m / 1000.0
        score = self.comfort_score(weather).total
        out: list[Insight] = []

        # Heat / cold
        if cur.temperature >= 35:
            out.append(Insight("🌡️", "Extreme heat",
                               f"{cur.temperature:.0f}°C is very hot. Stay hydrated, seek shade and limit exertion.",
                               "HIGH"))
        elif cur.temperature >= 30:
            out.append(Insight("🌡️", "Hot conditions",
                               f"At {cur.temperature:.0f}°C it is hot. Plan outdoor time for cooler hours.",
                               "MODERATE"))
        elif cur.temperature <= -5:
            out.append(Insight("🥶", "Bitter cold",
                               f"{cur.temperature:.0f}°C - dress in layers and keep skin covered.",
                               "HIGH"))
        elif cur.temperature <= 5:
            out.append(Insight("🥶", "Cold conditions",
                               f"Only {cur.temperature:.0f}°C - warm clothing recommended.",
                               "MODERATE"))

        # Humidity making it feel hotter
        if cur.feels_like - cur.temperature >= 3:
            out.append(Insight("💧", "Humidity makes it feel hotter",
                               f"It feels like {cur.feels_like:.0f}°C due to {cur.humidity}% humidity.",
                               "MODERATE"))

        # Rain
        if cur.condition_code in THUNDERSTORM_CODES:
            out.append(Insight("⛈️", "Thunderstorm",
                               "Thunderstorm conditions detected. Avoid open areas and stay indoors.",
                               "CRITICAL"))
        elif cur.precipitation_probability >= 80 or (
            cur.condition_code in RAIN_CODES and cur.precipitation > 1.5
        ):
            out.append(Insight("🌧️", "Rain alert",
                               f"Rain is very likely ({cur.precipitation_probability}%). Carry an umbrella.",
                               "HIGH"))
        elif cur.precipitation_probability >= 55:
            out.append(Insight("☔", "Possible rain",
                               f"Rain chance is {cur.precipitation_probability}% - consider an umbrella.",
                               "MODERATE"))
        elif cur.precipitation_probability >= 35:
            out.append(Insight("🌦️", "Slight rain chance",
                               f"A {cur.precipitation_probability}% chance of light rain exists.",
                               "LOW"))

        if cur.condition_code in SNOW_CODES:
            out.append(Insight("❄️", "Snow conditions",
                               "Snow is falling or forecast. Expect slippery surfaces.",
                               "MODERATE"))

        # Wind
        if cur.wind_speed >= 50:
            out.append(Insight("🌬️", "Strong wind",
                               f"Wind gusts may reach {cur.wind_gusts:.0f} km/h. Secure loose items.",
                               "HIGH"))
        elif cur.wind_speed >= 32:
            out.append(Insight("🌬️", "Breezy",
                               f"{cur.wind_speed:.0f} km/h wind - noticeable during outdoor activity.",
                               "LOW"))

        # UV
        if cur.uv_index is not None and cur.is_day:
            if cur.uv_index >= 11:
                out.append(Insight("☀️", "Extreme UV",
                                   f"UV index {cur.uv_index:.1f} - avoid the sun between 11:00-15:00.",
                                   "HIGH"))
            elif cur.uv_index >= 8:
                out.append(Insight("☀️", "High UV",
                                   f"UV index {cur.uv_index:.1f} - use SPF 30+ and sunglasses.",
                                   "MODERATE"))
            elif cur.uv_index >= 6:
                out.append(Insight("☀️", "Moderate UV",
                                   f"UV index {cur.uv_index:.1f} - light sun protection advised.",
                                   "LOW"))

        # Visibility
        if vis_km < 2:
            out.append(Insight("🌫️", "Very poor visibility",
                               f"Visibility is only {vis_km:.1f} km - drive with extreme care.",
                               "HIGH"))
        elif vis_km < 5:
            out.append(Insight("🌫️", "Reduced visibility",
                               f"Visibility is {vis_km:.1f} km - take care on the roads.",
                               "MODERATE"))

        # Overall outdoor comfort
        if score <= 40:
            out.append(Insight("🚫", "Poor outdoor conditions",
                               "The overall comfort score is low. Prefer indoor activities today.",
                               "MODERATE"))

        # Clothing insight (always present, data-driven)
        out.append(self._clothing_insight(weather))

        # Travel insight
        if vis_km < 5 or cur.precipitation_probability >= 55 or cur.wind_speed >= 50:
            out.append(Insight("🧳", "Travel consideration",
                               "Visibility, precipitation or wind may affect long-distance travel.",
                               "LOW"))

        return out[:8]

    @staticmethod
    def _clothing_insight(weather: WeatherData) -> Insight:
        t = weather.current.temperature
        rain = weather.current.precipitation_probability
        if t >= 28:
            msg = "Light clothing is suitable. Use sun protection when outdoors."
        elif t >= 18:
            msg = "Light-to-medium clothing is comfortable."
        elif t >= 10:
            msg = "Medium clothing recommended; a light jacket may help."
        elif t >= 2:
            msg = "Warm clothing recommended."
        else:
            msg = "Heavy winter clothing is strongly recommended."
        if rain >= 55:
            msg += " Rain protection (umbrella/waterproof) would be useful."
        return Insight("👕", "Clothing insight", msg, "INFO")
