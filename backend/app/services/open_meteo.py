"""Client for the Open-Meteo archive and geocoder.

Historical daily maximum temperature comes from the archive API, which serves
ERA5 reanalysis and does not require an API key. Only that host is called.
Requests are retried on rate limits and server errors, then given up so a
failure is visible instead of hanging.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta

import httpx

from app.config import get_settings
from app.errors import OpenMeteoError

logger = logging.getLogger(__name__)

USER_AGENT = "ClimateHazardTrendAnalyzer/1.0 (educational; cache-on-read)"
_CLIENT = httpx.Client(
    timeout=httpx.Timeout(90.0, connect=10.0),
    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    follow_redirects=False,
)


def _get_json(url: str, params: dict) -> dict:
    delays = (0.6, 1.5, 3.0)
    last_error = "The weather service did not respond"
    for attempt, delay in enumerate(delays, start=1):
        try:
            response = _CLIENT.get(url, params=params)
        except httpx.HTTPError as exc:
            last_error = "The weather service could not be reached"
            logger.warning("Open-Meteo request failed (%s/%s): %s", attempt, len(delays), exc.__class__.__name__)
            time.sleep(delay)
            continue
        if response.status_code == 429 or response.status_code >= 500:
            last_error = f"The weather service returned HTTP {response.status_code}"
            logger.warning("Open-Meteo HTTP %s (%s/%s)", response.status_code, attempt, len(delays))
            time.sleep(delay)
            continue
        try:
            payload = response.json()
        except ValueError as exc:
            raise OpenMeteoError("The weather service returned a response that was not JSON") from exc
        if response.status_code >= 400 or (isinstance(payload, dict) and payload.get("error")):
            reason = payload.get("reason") if isinstance(payload, dict) else None
            raise OpenMeteoError(str(reason or f"The weather service returned HTTP {response.status_code}")[:240])
        if not isinstance(payload, dict):
            raise OpenMeteoError("The weather service returned an unexpected payload")
        return payload
    raise OpenMeteoError(last_error)


def fetch_daily_tmax(latitude: float, longitude: float, start: date, end: date) -> list[tuple[date, float | None]]:
    """Return raw daily maxima. None means the archive had no value that day."""
    if end < start:
        raise OpenMeteoError("The requested date range is empty")
    settings = get_settings()
    logger.info("Fetching Open-Meteo daily max %s,%s %s to %s", latitude, longitude, start, end)
    payload = _get_json(
        settings.open_meteo_archive_url,
        {
            "latitude": latitude,
            "longitude": longitude,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "daily": "temperature_2m_max",
            "timezone": "UTC",
            "temperature_unit": "celsius",
        },
    )
    daily = payload.get("daily") or {}
    times = daily.get("time")
    temps = daily.get("temperature_2m_max")
    if not isinstance(times, list) or not isinstance(temps, list) or len(times) != len(temps):
        raise OpenMeteoError("The archive response did not include a daily temperature series")
    series: list[tuple[date, float | None]] = []
    for raw_day, raw_temp in zip(times, temps, strict=True):
        try:
            parsed = date.fromisoformat(str(raw_day))
        except ValueError as exc:
            raise OpenMeteoError("The archive response included a date that could not be read") from exc
        if raw_temp is None:
            series.append((parsed, None))
        elif isinstance(raw_temp, (int, float)) and not isinstance(raw_temp, bool):
            series.append((parsed, float(raw_temp)))
        else:
            series.append((parsed, None))
    if not series:
        raise OpenMeteoError("The archive returned no days for that location and period")
    return series


def geocode_places(query: str) -> list[dict]:
    settings = get_settings()
    payload = _get_json(
        settings.open_meteo_geocode_url,
        {"name": query, "count": 8, "language": "en", "format": "json"},
    )
    results = payload.get("results") or []
    if not isinstance(results, list):
        return []
    places: list[dict] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        try:
            latitude = float(item["latitude"])
            longitude = float(item["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
            continue
        population = item.get("population")
        places.append(
            {
                "id": f"om-{item.get('id')}",
                "name": str(item.get("name") or query)[:120],
                "kind": "city",
                "country": str(item.get("country") or ""),
                "admin": str(item.get("admin1") or ""),
                "latitude": latitude,
                "longitude": longitude,
                "population": int(population) if isinstance(population, int) else None,
                "bbox": None,
            }
        )
    places.sort(key=lambda place: place["population"] or 0, reverse=True)
    return places


def iter_dates(start: date, end: date):
    cursor = start
    while cursor <= end:
        yield cursor
        cursor += timedelta(days=1)
