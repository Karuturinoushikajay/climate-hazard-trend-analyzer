"""Heatwave detection.

A heatwave is a run of at least `min_duration` consecutive calendar days whose
daily maximum temperature is strictly above a fixed threshold. The threshold is
a percentile of daily maxima over a baseline period, not over the years being
scored. That keeps a warming climate visible: later years can exceed a
historical extreme more often.

Missing days and physically implausible temperatures break a run. They are not
filled in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

TMAX_MIN = -80.0
TMAX_MAX = 55.0
MIN_BASELINE_DAYS = 365 * 5


@dataclass(frozen=True)
class DailyTemp:
    day: date
    tmax: float | None
    rejected: bool = False


@dataclass(frozen=True)
class HeatwaveEvent:
    start: date
    end: date
    duration: int
    mean_tmax: float
    max_tmax: float
    peak_date: date

    @property
    def year(self) -> int:
        return self.start.year


@dataclass(frozen=True)
class YearStat:
    year: int
    usable: bool
    valid_days: int
    expected_days: int
    rejected_days: int
    events: int
    heatwave_days: int
    max_duration: int
    mean_heatwave_tmax: float | None
    mean_excess: float | None
    annual_max: float | None

    @property
    def completeness(self) -> float:
        if self.expected_days <= 0:
            return 0.0
        return self.valid_days / self.expected_days


def clean_tmax(value: object) -> float | None:
    """Return a plausible Celsius maximum, or None when the value cannot be used."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
    else:
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    if number < TMAX_MIN or number > TMAX_MAX:
        return None
    return number


def interpret_temperature(day: date, raw: object) -> DailyTemp:
    """Distinguish a missing observation from one we rejected as implausible."""
    if raw is None:
        return DailyTemp(day, None, False)
    cleaned = clean_tmax(raw)
    if cleaned is None:
        return DailyTemp(day, None, True)
    return DailyTemp(day, cleaned, False)


def prepare_days(days: list[DailyTemp]) -> list[DailyTemp]:
    """Sort by date and keep the first observation when a date is repeated."""
    chosen: dict[date, DailyTemp] = {}
    for item in days:
        if item.day not in chosen:
            chosen[item.day] = item
    return [chosen[key] for key in sorted(chosen)]


def threshold_from_baseline(
    days: list[DailyTemp],
    baseline_start: int,
    baseline_end: int,
    percentile: float,
) -> tuple[float, int]:
    values = [
        item.tmax
        for item in days
        if item.tmax is not None and baseline_start <= item.day.year <= baseline_end
    ]
    if len(values) < MIN_BASELINE_DAYS:
        raise ValueError(
            f"The baseline has {len(values)} valid days; at least {MIN_BASELINE_DAYS} "
            "are required (about five years)."
        )
    threshold = float(np.percentile(np.asarray(values, dtype=float), percentile, method="linear"))
    return threshold, len(values)


def detect_heatwaves(
    days: list[DailyTemp],
    threshold: float,
    min_duration: int = 3,
) -> list[HeatwaveEvent]:
    """Find runs of consecutive hot days.

    A day is hot only when its maximum is strictly above `threshold`. A missing
    day, a rejected day, or a gap in the calendar ends the current run.
    """
    if min_duration < 1:
        raise ValueError("min_duration must be at least 1")
    ordered = prepare_days(days)
    events: list[HeatwaveEvent] = []
    run: list[DailyTemp] = []
    previous: date | None = None

    def flush() -> None:
        nonlocal run
        if len(run) >= min_duration:
            temps = [item.tmax for item in run if item.tmax is not None]
            peak = max(run, key=lambda item: item.tmax if item.tmax is not None else -10_000)
            events.append(
                HeatwaveEvent(
                    start=run[0].day,
                    end=run[-1].day,
                    duration=len(run),
                    mean_tmax=float(sum(temps) / len(temps)),
                    max_tmax=float(peak.tmax if peak.tmax is not None else 0.0),
                    peak_date=peak.day,
                )
            )
        run = []

    for item in ordered:
        if previous is not None and item.day == previous:
            continue
        hot = item.tmax is not None and item.tmax > threshold
        if hot:
            if run and previous is not None and (item.day - previous).days != 1:
                flush()
            run.append(item)
        else:
            flush()
        previous = item.day
    flush()
    return events


def _expected_days(year: int, window_start: date, window_end: date) -> int:
    start = max(date(year, 1, 1), window_start)
    end = min(date(year, 12, 31), window_end)
    if end < start:
        return 0
    return (end - start).days + 1


def annual_statistics(
    days: list[DailyTemp],
    events: list[HeatwaveEvent],
    window_start: date,
    window_end: date,
    threshold: float,
    *,
    min_completeness: float = 0.8,
) -> list[YearStat]:
    """Summarize each analysis year.

    Years with less than 80% of days present are marked unusable. Callers should
    keep them out of trend tests so a missing summer is not stored as a cool year.
    """
    ordered = prepare_days(days)
    by_year: dict[int, list[DailyTemp]] = {}
    for item in ordered:
        if window_start <= item.day <= window_end:
            by_year.setdefault(item.day.year, []).append(item)

    temp_by_date = {item.day: item.tmax for item in ordered}
    heat_days: dict[int, list[float]] = {}
    for event in events:
        cursor = event.start
        while cursor <= event.end:
            if window_start <= cursor <= window_end:
                value = temp_by_date.get(cursor)
                if value is not None:
                    heat_days.setdefault(cursor.year, []).append(value)
            cursor += timedelta(days=1)

    events_by_year: dict[int, list[HeatwaveEvent]] = {}
    for event in events:
        events_by_year.setdefault(event.year, []).append(event)

    stats: list[YearStat] = []
    for year in range(window_start.year, window_end.year + 1):
        observations = by_year.get(year, [])
        valid = [item.tmax for item in observations if item.tmax is not None]
        rejected = sum(1 for item in observations if item.rejected)
        expected = _expected_days(year, window_start, window_end)
        completeness = (len(valid) / expected) if expected else 0.0
        usable = expected > 0 and completeness >= min_completeness
        year_events = events_by_year.get(year, [])
        hot = heat_days.get(year, [])
        mean_hot = float(sum(hot) / len(hot)) if hot else None
        mean_excess = float(sum(value - threshold for value in hot) / len(hot)) if hot else None
        stats.append(
            YearStat(
                year=year,
                usable=usable,
                valid_days=len(valid),
                expected_days=expected,
                rejected_days=rejected,
                events=len(year_events),
                heatwave_days=len(hot),
                max_duration=max((event.duration for event in year_events), default=0),
                mean_heatwave_tmax=mean_hot,
                mean_excess=mean_excess,
                annual_max=max(valid) if valid and usable else (max(valid) if valid else None),
            )
        )
    return stats


def regional_daily_mean(series: list[list[DailyTemp]]) -> list[DailyTemp]:
    """Unweighted mean across sample points.

    A date is missing when fewer than half of the points have a valid temperature.
    Rejected values count as missing for that point. If any point rejected the
    day and the regional mean is still missing, the day is flagged rejected only
    when every available point was rejected rather than absent.
    """
    if not series:
        return []
    if len(series) == 1:
        return prepare_days(series[0])

    buckets: dict[date, list[DailyTemp]] = {}
    for points in series:
        seen: set[date] = set()
        for item in points:
            if item.day in seen:
                continue
            seen.add(item.day)
            buckets.setdefault(item.day, []).append(item)

    point_count = len(series)
    merged: list[DailyTemp] = []
    for day in sorted(buckets):
        observations = buckets[day]
        values = [item.tmax for item in observations if item.tmax is not None]
        if len(values) * 2 >= point_count and values:
            merged.append(DailyTemp(day, float(sum(values) / len(values)), False))
            continue
        rejected_only = bool(observations) and all(item.rejected for item in observations)
        merged.append(DailyTemp(day, None, rejected_only))
    return merged
