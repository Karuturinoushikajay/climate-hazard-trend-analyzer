"""Heatwave threshold and event rules."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.services.heatwave import (
    MIN_BASELINE_DAYS,
    DailyTemp,
    annual_statistics,
    detect_heatwaves,
    interpret_temperature,
    regional_daily_mean,
    threshold_from_baseline,
)
from app.services.trends import mann_kendall, period_change


def _day(year: int, month: int, day: int, tmax: float | None) -> DailyTemp:
    return DailyTemp(date(year, month, day), tmax)


def test_percentile_ignores_missing_and_implausible_values():
    # 10°C through 49°C, each value repeated. 80°C is outside the plausible range.
    values = [10 + (index % 40) for index in range(2000)]
    start = date(1961, 1, 1)
    days = [interpret_temperature(start + timedelta(days=index), value) for index, value in enumerate(values)]
    days.append(interpret_temperature(date(1970, 1, 1), 80))
    days.append(interpret_temperature(date(1970, 1, 2), None))
    threshold, count = threshold_from_baseline(days, 1961, 1990, 95)
    assert count == 2000
    assert threshold == pytest.approx(47.05)
    assert days[-2].rejected is True
    assert days[-2].tmax is None


def test_baseline_requires_about_five_years():
    days = [DailyTemp(date(1961, 1, 1) + timedelta(days=index), 30.0) for index in range(MIN_BASELINE_DAYS - 1)]
    with pytest.raises(ValueError, match="valid days"):
        threshold_from_baseline(days, 1961, 1990, 95)


def test_three_consecutive_days_form_one_event_and_two_do_not():
    too_short = [
        _day(2000, 7, 1, 30),
        _day(2000, 7, 2, 40),
        _day(2000, 7, 3, 41),
        _day(2000, 7, 4, 30),
    ]
    assert detect_heatwaves(too_short, 35, 3) == []
    long_enough = [
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, 41),
        _day(2000, 7, 3, 42),
    ]
    events = detect_heatwaves(long_enough, 35, 3)
    assert len(events) == 1
    assert events[0].duration == 3
    assert events[0].start == date(2000, 7, 1)
    assert events[0].end == date(2000, 7, 3)
    assert events[0].max_tmax == 42
    assert events[0].peak_date == date(2000, 7, 3)
    assert events[0].mean_tmax == pytest.approx(41)


def test_threshold_must_be_strictly_exceeded():
    days = [_day(2000, 7, day, 35) for day in range(1, 6)]
    assert detect_heatwaves(days, 35, 3) == []


def test_missing_day_or_calendar_gap_breaks_a_run():
    missing = [
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, None),
        _day(2000, 7, 3, 40),
        _day(2000, 7, 4, 40),
    ]
    gap = [
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, 40),
        _day(2000, 7, 4, 40),
    ]
    assert detect_heatwaves(missing, 35, 3) == []
    assert detect_heatwaves(gap, 35, 3) == []


def test_unsorted_days_and_duplicate_dates():
    unsorted = [
        _day(2000, 7, 3, 40),
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, 42),
    ]
    events = detect_heatwaves(unsorted, 35, 3)
    assert len(events) == 1
    assert events[0].peak_date == date(2000, 7, 2)
    duplicate = [
        _day(2000, 7, 1, 30),
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, 40),
        _day(2000, 7, 3, 40),
    ]
    assert detect_heatwaves(duplicate, 35, 3) == []


def test_implausible_temperature_breaks_the_run():
    days = [
        interpret_temperature(date(2000, 7, 1), 40),
        interpret_temperature(date(2000, 7, 2), 40),
        interpret_temperature(date(2000, 7, 3), 99),
        interpret_temperature(date(2000, 7, 4), 40),
        interpret_temperature(date(2000, 7, 5), 40),
    ]
    assert days[2].rejected is True
    assert detect_heatwaves(days, 35, 3) == []


def test_event_crossing_new_year_is_counted_in_the_start_year():
    days = [
        _day(2000, 12, 30, 40),
        _day(2000, 12, 31, 41),
        _day(2001, 1, 1, 39),
    ]
    events = detect_heatwaves(days, 35, 3)
    assert len(events) == 1
    assert events[0].year == 2000
    stats = annual_statistics(
        days,
        events,
        date(2000, 1, 1),
        date(2001, 12, 31),
        35,
        min_completeness=0,
    )
    by_year = {row.year: row for row in stats}
    assert by_year[2000].events == 1
    assert by_year[2000].heatwave_days == 2
    assert by_year[2001].events == 0
    assert by_year[2001].heatwave_days == 1


def test_multiple_events_in_one_year():
    days = [
        _day(2000, 7, 1, 40),
        _day(2000, 7, 2, 40),
        _day(2000, 7, 3, 40),
        _day(2000, 7, 4, 20),
        _day(2000, 7, 10, 41),
        _day(2000, 7, 11, 42),
        _day(2000, 7, 12, 43),
        _day(2000, 7, 13, 44),
    ]
    events = detect_heatwaves(days, 35, 3)
    assert [event.duration for event in events] == [3, 4]


def test_regional_mean_needs_half_the_points():
    day = date(2000, 7, 1)
    merged = regional_daily_mean(
        [
            [DailyTemp(day, 40), DailyTemp(date(2000, 7, 2), 30)],
            [DailyTemp(day, 42), DailyTemp(date(2000, 7, 2), None)],
        ]
    )
    assert merged[0].tmax == pytest.approx(41)
    assert merged[1].tmax == pytest.approx(30)
    sparse = regional_daily_mean(
        [
            [DailyTemp(day, 40)],
            [DailyTemp(day, None)],
            [DailyTemp(day, None)],
        ]
    )
    assert sparse[0].tmax is None


def _seasonal(start_year: int, end_year: int, warming_per_year: float) -> list[DailyTemp]:
    cursor = date(start_year, 1, 1)
    last = date(end_year, 12, 31)
    days: list[DailyTemp] = []
    while cursor <= last:
        doy = cursor.timetuple().tm_yday
        seasonal = 24 + 11 * math.cos((doy - 200) * 2 * math.pi / 365.25)
        warming = max(0, cursor.year - 1990) * warming_per_year
        days.append(DailyTemp(cursor, seasonal + warming))
        cursor += timedelta(days=1)
    return days


def _scored(days: list[DailyTemp], threshold: float):
    window = [item for item in days if 1990 <= item.day.year <= 2020]
    events = detect_heatwaves(window, threshold, 3)
    stats = annual_statistics(window, events, date(1990, 1, 1), date(2020, 12, 31), threshold)
    return stats


def test_fixed_baseline_shows_warming_that_an_in_sample_threshold_mutes():
    warm = _seasonal(1961, 2020, 0.12)
    fixed, _count = threshold_from_baseline(warm, 1961, 1990, 95)
    fixed_stats = _scored(warm, fixed)
    fixed_change = period_change(fixed_stats)
    usable = [row for row in fixed_stats if row.usable]
    mk = mann_kendall([row.year for row in usable], [float(row.heatwave_days) for row in usable])
    assert fixed_change["kind"] == "percent"
    assert fixed_change["percent"] > 30
    assert mk is not None
    assert mk["significant"] is True
    assert mk["direction"] == "increasing"

    analysis = [item for item in warm if 1990 <= item.day.year <= 2020]
    in_sample, _count = threshold_from_baseline(analysis, 1990, 2020, 95)
    in_sample_change = period_change(_scored(warm, in_sample))
    # Later hot years pull an in-sample percentile up, so the early decade can
    # fall entirely below it. The fixed baseline still scores those years.
    assert in_sample > fixed
    assert in_sample_change["kind"] == "from_zero"
    assert in_sample_change["early_mean"] == 0


def test_flat_climate_does_not_invent_a_large_increase():
    flat = _seasonal(1961, 2020, 0)
    threshold, _count = threshold_from_baseline(flat, 1961, 1990, 95)
    change = period_change(_scored(flat, threshold))
    assert change["kind"] == "percent"
    assert abs(change["percent"]) < 15
