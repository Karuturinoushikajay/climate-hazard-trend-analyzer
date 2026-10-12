"""Turn a region and a year window into a stored heatwave analysis.

The first request for a location fetches daily maxima, writes them to the
document store, and writes the finished analysis too. A later request for a
completed historical window reads that analysis back instead of recomputing it.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from app.data.regions import FEATURED_BY_ID, sample_points
from app.db.store import DocumentStore
from app.errors import APIError, OpenMeteoError
from app.models.schemas import AnalyzeRequest
from app.sanitize import clean_name
from app.services import open_meteo
from app.services.heatwave import (
    DailyTemp,
    HeatwaveEvent,
    YearStat,
    annual_statistics,
    detect_heatwaves,
    interpret_temperature,
    regional_daily_mean,
    threshold_from_baseline,
)
from app.services.insights import build_insight
from app.services.trends import ROLLING_WINDOW, period_change, rolling_mean, trend_block

logger = logging.getLogger(__name__)

ASSUMPTIONS = [
    "Daily maximum temperature is Open-Meteo's archive variable temperature_2m_max, in degrees Celsius. For these years that archive is ERA5 reanalysis at 2 m, not a single weather station.",
    "The percentile is computed from every valid baseline day, not a separate threshold for each calendar day. It acts as a local hot-season extreme. Unusually warm winter days are not called heatwaves.",
    "The threshold is fixed from the baseline and then applied to the analysis window. It is not recomputed from the years being scored, so a warmer climate can produce more exceedances.",
    "A day counts only when the temperature is strictly above the threshold. Missing values, non-numeric values, and readings below −80°C or above 55°C break a consecutive run.",
    "A city is one point snapped to 0.01 degree (about 1 km). A state or box uses the unweighted mean of up to four interior points. A day is missing if fewer than half of those points have a valid temperature.",
    "An event is counted in the year it starts. Heatwave days are counted in the year they occur. A spell that crosses 1 January can therefore add days to a year with no new event.",
    "Years with less than 80% of days present are left out of totals and trend tests. A missing summer is not treated as a year with no heatwave.",
    "The percent change compares mean annual heatwave days in the first and last 10 complete years, or the two halves of the series when fewer than 20 complete years are available.",
    "Mann–Kendall p-values use a normal approximation with a tie correction. Significance means a two-sided p-value below 0.05. On series shorter than 20 years that approximation is rough.",
    "Boxes that cross the antimeridian are not supported, and a box edge cannot exceed 15 degrees.",
]

_KEY_LOCKS: dict[str, threading.Lock] = {}
_KEY_GUARD = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _KEY_GUARD:
        if key not in _KEY_LOCKS:
            _KEY_LOCKS[key] = threading.Lock()
        return _KEY_LOCKS[key]


@dataclass(frozen=True)
class ResolvedRegion:
    region_id: str
    name: str
    mode: str
    latitude: float
    longitude: float
    bbox: tuple[float, float, float, float] | None


def resolve_region(body: AnalyzeRequest) -> ResolvedRegion:
    featured = None
    if body.region_id and not body.region_id.startswith("om-") and body.region_id != "custom":
        featured = FEATURED_BY_ID.get(body.region_id)
        if featured is None:
            raise APIError(400, "That region id is not in the catalog. Search for a city or draw a box.")
    if featured is not None:
        bbox = None
        if featured["bbox"] is not None:
            box = featured["bbox"]
            bbox = (box["west"], box["south"], box["east"], box["north"])
        return ResolvedRegion(
            region_id=featured["id"],
            name=featured["name"],
            mode="region" if featured["kind"] == "region" else "city",
            latitude=float(featured["latitude"]),
            longitude=float(featured["longitude"]),
            bbox=bbox,
        )
    if body.mode == "bbox":
        if body.bbox is None:
            raise APIError(400, "A bounding box is required")
        box = body.bbox
        return ResolvedRegion(
            region_id=body.region_id or "custom",
            name=clean_name(body.name, "Custom box"),
            mode="bbox",
            latitude=(box.south + box.north) / 2,
            longitude=(box.west + box.east) / 2,
            bbox=(box.west, box.south, box.east, box.north),
        )
    if body.latitude is None or body.longitude is None:
        raise APIError(400, "Latitude and longitude are required")
    return ResolvedRegion(
        region_id=body.region_id or "custom",
        name=clean_name(body.name, "Selected location"),
        mode="city",
        latitude=body.latitude,
        longitude=body.longitude,
        bbox=None,
    )


def _end_of_year(year: int, today: date) -> date:
    if year < today.year:
        return date(year, 12, 31)
    yesterday = today - timedelta(days=1)
    if yesterday < date(year, 1, 1):
        raise APIError(400, "The current year does not have a complete archive day yet. Choose last year.")
    return yesterday


def _missing_dates(raw: dict, start: date, end: date, today: date, updated_at: datetime | None) -> list[date]:
    stale = updated_at is None or (datetime.now(timezone.utc) - updated_at) > timedelta(hours=12)
    missing: list[date] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        provisional = (today - cursor).days <= 14
        if key not in raw or (raw.get(key) is None and provisional and stale):
            missing.append(cursor)
        cursor += timedelta(days=1)
    return missing


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def load_point_series(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    store: DocumentStore,
    fetcher,
    today: date,
) -> tuple[list[DailyTemp], bool]:
    key = f"{latitude:.2f},{longitude:.2f}"
    with _lock_for(key):
        existing = store.get_document("weather", key) or {}
        raw = dict(existing.get("days") or {})
        updated_at = _parse_time(existing.get("updated_at"))
        missing = _missing_dates(raw, start, end, today, updated_at)
        fetched = False
        if missing:
            try:
                observed = fetcher(latitude, longitude, missing[0], missing[-1])
            except OpenMeteoError as exc:
                raise APIError(502, f"Weather archive request failed: {exc}") from exc
            for observed_day, value in observed:
                raw[observed_day.isoformat()] = value
            cursor = missing[0]
            while cursor <= missing[-1]:
                raw.setdefault(cursor.isoformat(), None)
                cursor += timedelta(days=1)
            store.put_document(
                "weather",
                key,
                {
                    "latitude": latitude,
                    "longitude": longitude,
                    "days": raw,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                },
            )
            fetched = True
        series = [
            interpret_temperature(day, raw.get(day.isoformat()))
            for day in open_meteo.iter_dates(start, end)
        ]
        return series, fetched


def _analysis_key(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _plain_number(value: float | None, digits: int = 2) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def _event_payload(event: HeatwaveEvent) -> dict:
    return {
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "duration": event.duration,
        "mean_tmax": round(event.mean_tmax, 2),
        "max_tmax": round(event.max_tmax, 2),
        "peak_date": event.peak_date.isoformat(),
    }


def _fitted(block: dict | None, year: int) -> float | None:
    if not block or not block.get("linear"):
        return None
    linear = block["linear"]
    return linear["intercept"] + linear["slope_per_year"] * year


def _serialize_year(row: YearStat, columns: dict[str, list[float | None]], index: int) -> dict:
    usable = row.usable

    def series(name: str) -> float | None:
        value = columns[name][index]
        return None if value is None else round(float(value), 2)

    return {
        "year": row.year,
        "usable": usable,
        "valid_days": row.valid_days,
        "expected_days": row.expected_days,
        "completeness": round(row.completeness, 4),
        "events": row.events if usable else None,
        "heatwave_days": row.heatwave_days if usable else None,
        "max_duration": row.max_duration if usable else None,
        "mean_heatwave_tmax": _plain_number(row.mean_heatwave_tmax) if usable else None,
        "mean_excess": _plain_number(row.mean_excess) if usable else None,
        "annual_max": _plain_number(row.annual_max) if usable else None,
        "rolling_events": series("rolling_events"),
        "rolling_heatwave_days": series("rolling_heatwave_days"),
        "rolling_annual_max": series("rolling_annual_max"),
        "regression_events": series("regression_events"),
        "regression_heatwave_days": series("regression_heatwave_days"),
        "regression_annual_max": series("regression_annual_max"),
    }


def _round_block(block: dict | None) -> dict | None:
    if block is None:
        return None
    linear = block.get("linear")
    mk = block.get("mann_kendall")
    rounded_linear = None
    if linear:
        rounded_linear = {
            "slope_per_year": round(linear["slope_per_year"], 4),
            "slope_per_decade": round(linear["slope_per_decade"], 4),
            "intercept": round(linear["intercept"], 4),
            "r_squared": round(linear["r_squared"], 4),
            "p_value": linear["p_value"],
        }
    rounded_mk = None
    if mk:
        rounded_mk = {
            **mk,
            "z": round(mk["z"], 4),
            "variance": round(mk["variance"], 4),
            "sen_slope_per_year": round(mk["sen_slope_per_year"], 4),
            "sen_slope_per_decade": round(mk["sen_slope_per_decade"], 4),
        }
    return {"linear": rounded_linear, "mann_kendall": rounded_mk}


def run_analysis(
    body: AnalyzeRequest,
    store: DocumentStore,
    fetcher=None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    fetch = fetcher or open_meteo.fetch_daily_tmax
    region = resolve_region(body)
    try:
        points = sample_points(region.latitude, region.longitude, region.bbox)
    except ValueError as exc:
        raise APIError(400, str(exc)) from exc

    analysis_start = date(body.start_year, 1, 1)
    analysis_end = _end_of_year(body.end_year, today)
    baseline_start = date(body.baseline_start_year, 1, 1)
    baseline_end = _end_of_year(body.baseline_end_year, today)
    fetch_start = min(analysis_start, baseline_start)
    fetch_end = max(analysis_end, baseline_end)

    key_payload = {
        "hazard": "heatwave",
        "points": points,
        "analysis_start": analysis_start.isoformat(),
        "analysis_end": analysis_end.isoformat(),
        "baseline_start": baseline_start.isoformat(),
        "baseline_end": baseline_end.isoformat(),
        "percentile": body.percentile,
        "min_duration": body.min_duration,
        "name": region.name,
        "mode": region.mode,
    }
    cache_key = _analysis_key(key_payload)
    use_cache = analysis_end.year < today.year
    if use_cache:
        cached = store.get_document("analyses", cache_key)
        if cached and isinstance(cached.get("result"), dict):
            result = dict(cached["result"])
            cache = dict(result.get("cache") or {})
            cache["analysis"] = "hit"
            result["cache"] = cache
            result["cached"] = True
            return result

    fetched_flags: list[bool] = []
    series: list[list[DailyTemp]] = []
    workers = min(4, len(points))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(load_point_series, lat, lon, fetch_start, fetch_end, store, fetch, today)
            for lat, lon in points
        ]
        for future in futures:
            point_series, fetched = future.result()
            series.append(point_series)
            fetched_flags.append(fetched)

    regional = regional_daily_mean(series)
    try:
        threshold, baseline_days = threshold_from_baseline(
            regional,
            body.baseline_start_year,
            body.baseline_end_year,
            body.percentile,
        )
    except ValueError as exc:
        raise APIError(422, str(exc)) from exc

    window_days = [item for item in regional if analysis_start <= item.day <= analysis_end]
    events = detect_heatwaves(window_days, threshold, body.min_duration)
    stats = annual_statistics(window_days, events, analysis_start, analysis_end, threshold)
    usable_years = {row.year for row in stats if row.usable}
    kept_events = [event for event in events if event.year in usable_years]
    if not any(row.usable for row in stats):
        raise APIError(422, "None of the selected years have enough valid temperature days to analyze.")

    days_block = trend_block(stats, "heatwave_days")
    events_block = trend_block(stats, "events")
    max_block = trend_block(stats, "annual_max")
    change = period_change(stats, "heatwave_days")
    days_mk = (days_block or {}).get("mann_kendall")
    events_mk = (events_block or {}).get("mann_kendall")
    days_linear = (days_block or {}).get("linear")
    insight = build_insight(
        region_name=region.name,
        change=change,
        days_mk=days_mk,
        events_mk=events_mk,
        days_linear=days_linear,
        threshold_c=threshold,
        percentile=body.percentile,
        min_duration=body.min_duration,
        baseline_start=body.baseline_start_year,
        baseline_end=body.baseline_end_year,
        baseline_days=baseline_days,
        usable_years=len(usable_years),
    )

    usable_rows = [row for row in stats if row.usable]
    columns = {
        "rolling_events": rolling_mean([row.events if row.usable else None for row in stats], ROLLING_WINDOW),
        "rolling_heatwave_days": rolling_mean(
            [row.heatwave_days if row.usable else None for row in stats],
            ROLLING_WINDOW,
        ),
        "rolling_annual_max": rolling_mean([row.annual_max if row.usable else None for row in stats], ROLLING_WINDOW),
        "regression_events": [_fitted(events_block, row.year) for row in stats],
        "regression_heatwave_days": [_fitted(days_block, row.year) for row in stats],
        "regression_annual_max": [_fitted(max_block, row.year) for row in stats],
    }
    annual = [_serialize_year(row, columns, index) for index, row in enumerate(stats)]
    event_payloads = [_event_payload(event) for event in sorted(kept_events, key=lambda item: (-item.duration, item.start))]
    hottest = None
    for item in window_days:
        if item.tmax is None:
            continue
        if item.day.year not in usable_years:
            continue
        if hottest is None or item.tmax > hottest[1]:
            hottest = (item.day, item.tmax)
    total_events = len(kept_events)
    total_days = sum(row.heatwave_days for row in usable_rows)
    longest = max(kept_events, key=lambda item: (item.duration, item.max_tmax), default=None)
    if fetched_flags and all(fetched_flags):
        weather_state = "miss"
    elif any(fetched_flags):
        weather_state = "mixed"
    else:
        weather_state = "hit"
    expected = sum(row.expected_days for row in stats)
    valid = sum(row.valid_days for row in stats)
    rejected = sum(row.rejected_days for row in stats)
    bbox_payload = None
    if region.bbox is not None:
        west, south, east, north = region.bbox
        bbox_payload = {"west": west, "south": south, "east": east, "north": north}
    result = {
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "hazard": {
            "id": "heatwave",
            "name": "Heatwave",
            "definition": (
                f"{body.min_duration} or more consecutive days with maximum temperature strictly above "
                f"the {body.percentile:g}th percentile of daily maxima in "
                f"{body.baseline_start_year}–{body.baseline_end_year}."
            ),
        },
        "region": {
            "id": region.region_id,
            "name": region.name,
            "mode": region.mode,
            "latitude": region.latitude,
            "longitude": region.longitude,
            "bbox": bbox_payload,
            "sample_points": [{"latitude": lat, "longitude": lon} for lat, lon in points],
        },
        "period": {
            "start_year": body.start_year,
            "end_year": body.end_year,
            "start_date": analysis_start.isoformat(),
            "end_date": analysis_end.isoformat(),
            "baseline_start_year": body.baseline_start_year,
            "baseline_end_year": body.baseline_end_year,
            "baseline_overlaps_analysis": not (
                body.baseline_end_year < body.start_year or body.baseline_start_year > body.end_year
            ),
        },
        "threshold": {
            "percentile": body.percentile,
            "celsius": round(threshold, 2),
            "min_duration_days": body.min_duration,
            "baseline_valid_days": baseline_days,
            "comparison": "strictly above",
        },
        "data_quality": {
            "days_expected": expected,
            "days_valid": valid,
            "missing_days": max(expected - valid, 0),
            "rejected_days": rejected,
            "completeness": round(valid / expected, 4) if expected else 0.0,
            "usable_years": len(usable_years),
            "low_data_years": [row.year for row in stats if not row.usable],
            "source": "Open-Meteo historical archive (ERA5), daily temperature_2m_max",
            "units": "celsius",
        },
        "cache": {"analysis": "miss", "weather": weather_state, "points": len(points)},
        "summary": {
            "total_events": total_events,
            "total_heatwave_days": total_days,
            "longest_event": _event_payload(longest) if longest else None,
            "mean_event_duration": round(total_days / total_events, 2) if total_events else None,
            "mean_annual_events": round(total_events / len(usable_rows), 2) if usable_rows else 0,
            "mean_annual_heatwave_days": round(total_days / len(usable_rows), 2) if usable_rows else 0,
            "hottest_day": None
            if hottest is None
            else {"date": hottest[0].isoformat(), "tmax": round(hottest[1], 2)},
        },
        "change": None if change.get("kind") == "insufficient" else change,
        "insight": insight,
        "trends": {
            "heatwave_days": _round_block(days_block),
            "events": _round_block(events_block),
            "annual_max": _round_block(max_block),
            "rolling_window_years": ROLLING_WINDOW,
        },
        "annual": annual,
        "events": event_payloads,
        "assumptions": ASSUMPTIONS,
    }
    if use_cache:
        store.put_document(
            "analyses",
            cache_key,
            {"created_at": result["generated_at"], "request": key_payload, "result": result},
        )
    logger.info(
        "Analysis %s %s–%s threshold %.2f°C events %s weather %s",
        region.name,
        body.start_year,
        body.end_year,
        threshold,
        total_events,
        weather_state,
    )
    return result
