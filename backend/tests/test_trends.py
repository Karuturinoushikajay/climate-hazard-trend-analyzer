"""Rolling means, regression, Mann–Kendall, and the wording of insights."""

from __future__ import annotations

import pytest

from app.services.insights import build_insight
from app.services.trends import linear_trend, mann_kendall, period_change, rolling_mean
from app.services.heatwave import YearStat


def _year(year: int, events: int, days: int, duration: int | None = None) -> YearStat:
    return YearStat(
        year=year,
        usable=True,
        valid_days=365,
        expected_days=365,
        rejected_days=0,
        events=events,
        heatwave_days=days,
        max_duration=duration if duration is not None else (days if events == 0 else max(days // events, 1)),
        mean_heatwave_tmax=40.0 if days else None,
        mean_excess=2.0 if days else None,
        annual_max=42.0,
    )


def test_centered_rolling_mean_leaves_edges_empty():
    assert rolling_mean([1, 2, 3, 4, 5], 3) == [None, 2, 3, 4, None]
    assert rolling_mean([1, None, 3, 4, 5], 3)[2] is None


def test_linear_trend_of_a_straight_line():
    fit = linear_trend([2000, 2001, 2002, 2003], [1, 3, 5, 7])
    assert fit is not None
    assert fit["slope_per_year"] == pytest.approx(2)
    assert fit["slope_per_decade"] == pytest.approx(20)
    assert fit["r_squared"] == pytest.approx(1)
    assert fit["p_value"] < 0.01


def test_linear_trend_of_a_constant_is_flat():
    fit = linear_trend([2000, 2001, 2002], [4, 4, 4])
    assert fit is not None
    assert fit["slope_per_year"] == 0
    assert fit["p_value"] == 1


def test_mann_kendall_directions_and_ties():
    rising = mann_kendall([2000, 2001, 2002, 2003, 2004, 2005, 2006, 2007], [1, 2, 3, 4, 5, 6, 7, 8])
    assert rising is not None
    assert rising["s"] == 28
    assert rising["direction"] == "increasing"
    assert rising["significant"] is True
    assert rising["sen_slope_per_year"] == pytest.approx(1)

    falling = mann_kendall(list(range(2000, 2008)), [8, 7, 6, 5, 4, 3, 2, 1])
    assert falling is not None
    assert falling["s"] == -28
    assert falling["direction"] == "decreasing"

    tied = mann_kendall(list(range(2000, 2008)), [1, 2, 2, 2, 2, 2, 2, 3])
    assert tied is not None
    # Hand-counted sign of every pair.
    assert tied["s"] == 13
    flat = mann_kendall(list(range(2000, 2008)), [5, 5, 5, 5, 5, 5, 5, 5])
    assert flat is not None
    assert flat["s"] == 0
    assert flat["trend"] == "no significant trend"
    assert flat["p_value"] == pytest.approx(1)


def test_period_change_windows_and_zero_cases():
    rows = [_year(1990 + offset, 1, offset + 1) for offset in range(30)]
    change = period_change(rows)
    assert change["early_start"] == 1990
    assert change["early_end"] == 1999
    assert change["late_start"] == 2010
    assert change["late_end"] == 2019
    assert change["kind"] == "percent"
    assert change["early_mean"] == pytest.approx(5.5)
    assert change["late_mean"] == pytest.approx(25.5)

    started = [_year(1990 + offset, 0, 0) for offset in range(10)] + [
        _year(2000 + offset, 1, offset + 1) for offset in range(10)
    ]
    assert period_change(started)["kind"] == "from_zero"

    zeros = [_year(1990 + offset, 0, 0) for offset in range(12)]
    assert period_change(zeros)["kind"] == "both_zero"

    ended = [_year(year, 1, 4) for year in range(1990, 2000)] + [_year(year, 0, 0) for year in range(2000, 2010)]
    assert period_change(ended)["kind"] == "to_zero"

    short = [_year(1990 + offset, 1, 2) for offset in range(9)]
    assert period_change(short)["kind"] == "insufficient"


def _insight(**overrides):
    change = {
        "kind": "percent",
        "percent": 40.2,
        "early_label": "1990–1999",
        "late_label": "2011–2020",
        "early_mean": 5,
        "late_mean": 7.01,
        "early_mean_duration": 3.5,
        "late_mean_duration": 4.2,
        "early_start": 1990,
        "early_end": 1999,
        "late_start": 2011,
        "late_end": 2020,
    }
    days_mk = {
        "significant": True,
        "direction": "increasing",
        "trend": "increasing",
        "p_value": 0.008,
        "sen_slope_per_decade": 1.5,
        "n": 31,
    }
    events_mk = {
        "significant": True,
        "direction": "increasing",
        "trend": "increasing",
        "p_value": 0.02,
        "sen_slope_per_decade": 0.4,
        "n": 31,
    }
    days_linear = {"slope_per_decade": 1.4, "p_value": 0.01, "r_squared": 0.4}
    payload = {
        "region_name": "Delhi",
        "change": change,
        "days_mk": days_mk,
        "events_mk": events_mk,
        "days_linear": days_linear,
        "threshold_c": 39.8,
        "percentile": 95,
        "min_duration": 3,
        "baseline_start": 1961,
        "baseline_end": 1990,
        "baseline_days": 10950,
        "usable_years": 31,
    }
    payload.update(overrides)
    return build_insight(**payload)


def test_insight_headlines_match_the_evidence():
    significant = _insight()
    assert significant["headline"] == (
        "Heatwave days in Delhi increased by 40% from 1990–1999 to 2011–2020."
    )
    assert significant["significant"] is True
    assert significant["direction"] == "increase"
    assert "39.8°C" in significant["detail"]
    assert "p = 0.008" in significant["detail"]
    assert "Sen's slope +1.50 days/decade" in significant["detail"]

    days_mk = {
        "significant": False,
        "direction": "increasing",
        "trend": "no significant trend",
        "p_value": 0.31,
        "sen_slope_per_decade": 0.2,
        "n": 31,
    }
    vague = _insight(days_mk=days_mk, events_mk={**days_mk, "p_value": 0.4})
    assert vague["headline"] == (
        "Heatwave days in Delhi increased by 40% from 1990–1999 to 2011–2020, "
        "but the trend is not statistically significant."
    )
    assert vague["significant"] is False

    decrease = _insight(change={**_insight.__defaults__} if False else None)
    change = {
        "kind": "percent",
        "percent": -25.4,
        "early_label": "1990–1999",
        "late_label": "2011–2020",
        "early_mean": 8,
        "late_mean": 6,
        "early_mean_duration": 4,
        "late_mean_duration": 3,
    }
    falling_mk = {
        "significant": True,
        "direction": "decreasing",
        "trend": "decreasing",
        "p_value": 0.01,
        "sen_slope_per_decade": -1.2,
        "n": 31,
    }
    decrease = _insight(change=change, days_mk=falling_mk, events_mk=falling_mk)
    assert decrease["headline"] == (
        "Heatwave days in Delhi decreased by 25% from 1990–1999 to 2011–2020."
    )
    assert decrease["direction"] == "decrease"

    same = _insight(change={**change, "percent": 0.4, "kind": "percent"})
    assert "stayed about the same" in same["headline"]
    assert same["significant"] is False

    from_zero = _insight(
        change={
            "kind": "from_zero",
            "percent": None,
            "early_label": "1990–1999",
            "late_label": "2011–2020",
            "early_mean": 0,
            "late_mean": 4.2,
            "early_mean_duration": None,
            "late_mean_duration": 4.0,
        }
    )
    assert from_zero["headline"] == (
        "Delhi had no heatwave days in 1990–1999, then averaged 4.2 a year in 2011–2020."
    )

    to_zero = _insight(
        change={
            "kind": "to_zero",
            "percent": None,
            "early_label": "1990–1999",
            "late_label": "2011–2020",
            "early_mean": 4.5,
            "late_mean": 0,
            "early_mean_duration": 3,
            "late_mean_duration": None,
        },
        days_mk=falling_mk,
    )
    assert to_zero["headline"] == (
        "Delhi averaged 4.5 heatwave days a year in 1990–1999, then none in 2011–2020."
    )

    both = _insight(
        change={
            "kind": "both_zero",
            "percent": 0,
            "early_label": "1990–1999",
            "late_label": "2011–2020",
            "early_mean": 0,
            "late_mean": 0,
            "early_mean_duration": None,
            "late_mean_duration": None,
        }
    )
    assert both["headline"] == "No heatwaves were detected in Delhi between 1990–1999 and 2011–2020."
    assert both["direction"] == "none"

    mixed_events = {
        "significant": True,
        "direction": "decreasing",
        "trend": "decreasing",
        "p_value": 0.03,
        "sen_slope_per_decade": -0.4,
        "n": 31,
    }
    mixed = _insight(events_mk=mixed_events)
    assert mixed["direction"] == "mixed"
    assert "different story" in mixed["detail"]

    short = build_insight(
        region_name="Delhi",
        change={"kind": "insufficient"},
        days_mk=None,
        events_mk=None,
        days_linear=None,
        threshold_c=39.8,
        percentile=95,
        min_duration=3,
        baseline_start=1961,
        baseline_end=1990,
        baseline_days=1000,
        usable_years=4,
    )
    assert short["headline"] == "There are not enough complete years to judge a heatwave trend in Delhi."
    assert short["direction"] == "none"


def test_sen_slope_respects_year_gaps():
    mk = mann_kendall([2000, 2002, 2004, 2006, 2008, 2010, 2012, 2014], [0, 2, 4, 6, 8, 10, 12, 14])
    assert mk is not None
    assert mk["sen_slope_per_year"] == pytest.approx(1)
    assert mann_kendall([2000, 2001, 2002], [0, 1, 2]) is None
