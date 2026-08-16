"""Typed exceptions raised by the weather API client."""


class WeatherAPIError(Exception):
    """Base class for all API errors."""


class NetworkError(WeatherAPIError):
    """No connectivity, timeout, DNS failure, or transport-level error."""


class CityNotFoundError(WeatherAPIError):
    """Geocoding returned no matching locations."""


class RateLimitError(WeatherAPIError):
    """HTTP 429 - the provider asked us to slow down."""


class ServerError(WeatherAPIError):
    """HTTP 5xx or unexpected status code."""


class InvalidResponseError(WeatherAPIError):
    """The response body was not usable JSON or missed required fields."""
