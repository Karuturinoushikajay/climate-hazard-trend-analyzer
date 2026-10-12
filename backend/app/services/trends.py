"""Frequency and intensity trends.

Ordinary least squares describes the average change per year. The Mann–Kendall
test asks whether a monotonic trend is detectable without assuming a straight
line, and Sen's slope estimates that change with less pull from a single
extreme year. p-values use the normal approximation with a continuity correction
and a correction for tied values. That approximation is rough on short series.
"""

from __future__ import annotations

from collections import Counter
from math import sqrt
from statistics import median

from scipy import stats

from app.services.heatwave import YearStat

ROLLING_WINDOW = 5
SIGNIFICANCE = 0.05


def rolling_mean(values: list[float | None], window: int = ROLLING_WINDOW) -> list[float | None]:
    """Centered rolling mean. Windows that are incomplete or contain a gap are None."""
    if window < 1 or window % 2 == 0:
        raise ValueError("window must be a positive odd integer")
    half = window // 2
    output: list[float | None] = [None] * len(values)
    for index in range(len(values)):
        start = index - half
        stop = index + half + 1
        if start < 0 or stop > len(values):
            continue
        chunk = values[start:stop]
        if any(item is None for item in chunk):
            continue
        output[index] = float(sum(item for item in chunk if item is not None) / window)
    return output


def linear_trend(years: list[int], values: list[float]) -> dict | None:
    if len(years) != len(values) or len(values) < 3:
        return None
    if len(set(years)) < 3:
        return None
    if len(set(values)) == 1:
        return {
            "slope_per_year": 0.0,
            "slope_per_decade": 0.0,
            "intercept": float(values[0]),
            "r_squared": 0.0,
            "p_value": 1.0,
        }
    fit = stats.linregress(years, values)
    p_value = float(fit.pvalue)
    r_value = float(fit.rvalue)
    if p_value != p_value:
        p_value = 1.0
    if r_value != r_value:
        r_value = 0.0
    return {
        "slope_per_year": float(fit.slope),
        "slope_per_decade": float(fit.slope) * 10.0,
        "intercept": float(fit.intercept),
        "r_squared": r_value**2,
        "p_value": p_value,
    }


def mann_kendall(years: list[int], values: list[float]) -> dict | None:
    """Two-sided Mann–Kendall test with Sen's slope.

    `years` must be in chronological order. Sen's slope divides by the year gap,
    so a missing year does not get treated as an adjacent step.
    """
    n = len(values)
    if n < 8 or len(years) != n:
        return None
    score = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = values[j] - values[i]
            if diff > 0:
                score += 1
            elif diff < 0:
                score -= 1
    tie_term = 0
    for count in Counter(values).values():
        if count > 1:
            tie_term += count * (count - 1) * (2 * count + 5)
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if variance <= 0 or score == 0:
        z_score = 0.0
    elif score > 0:
        z_score = (score - 1) / sqrt(variance)
    else:
        z_score = (score + 1) / sqrt(variance)
    p_value = float(2 * stats.norm.sf(abs(z_score)))
    if score > 0:
        direction = "increasing"
    elif score < 0:
        direction = "decreasing"
    else:
        direction = "flat"
    significant = p_value < SIGNIFICANCE and direction != "flat"
    trend = direction if significant else "no significant trend"
    return {
        "s": score,
        "z": z_score,
        "p_value": p_value,
        "variance": variance,
        "significant": significant,
        "direction": direction,
        "trend": trend,
        "sen_slope_per_year": _sen_slope(years, values),
        "sen_slope_per_decade": _sen_slope(years, values) * 10.0,
        "n": n,
    }


def _sen_slope(years: list[int], values: list[float]) -> float:
    slopes: list[float] = []
    for i in range(len(values) - 1):
        for j in range(i + 1, len(values)):
            span = years[j] - years[i]
            if span == 0:
                continue
            slopes.append((values[j] - values[i]) / span)
    if not slopes:
        return 0.0
    return float(median(slopes))


def _mean(values: list[float]) -> float:
    return float(sum(values) / len(values))


def _span_label(years: list[int]) -> str:
    if years[-1] - years[0] + 1 == len(years):
        return f"{years[0]}–{years[-1]}"
    return f"{len(years)} complete years from {years[0]} to {years[-1]}"


def _duration(rows: list[YearStat]) -> float | None:
    events = sum(row.events for row in rows)
    days = sum(row.heatwave_days for row in rows)
    if events <= 0:
        return None
    return days / events


def period_change(stats: list[YearStat], field: str = "heatwave_days") -> dict:
    """Compare the earliest and latest complete years.

    Twenty or more years use the first and last decades. Shorter series are
    split in half. Fewer than ten complete years is not enough for this contrast.
    """
    usable = [row for row in stats if row.usable]
    if len(usable) < 10:
        return {"kind": "insufficient", "usable_years": len(usable)}
    if len(usable) >= 20:
        early = usable[:10]
        late = usable[-10:]
    else:
        midpoint = len(usable) // 2
        early = usable[:midpoint]
        late = usable[midpoint:]
    early_values = [float(getattr(row, field)) for row in early]
    late_values = [float(getattr(row, field)) for row in late]
    early_mean = _mean(early_values)
    late_mean = _mean(late_values)
    early_years = [row.year for row in early]
    late_years = [row.year for row in late]
    result = {
        "metric": field,
        "early_label": _span_label(early_years),
        "late_label": _span_label(late_years),
        "early_start": early_years[0],
        "early_end": early_years[-1],
        "late_start": late_years[0],
        "late_end": late_years[-1],
        "early_mean": early_mean,
        "late_mean": late_mean,
        "early_mean_duration": _duration(early),
        "late_mean_duration": _duration(late),
        "usable_years": len(usable),
    }
    if abs(early_mean) < 1e-9 and abs(late_mean) < 1e-9:
        result["kind"] = "both_zero"
        result["percent"] = 0.0
    elif abs(early_mean) < 1e-9:
        result["kind"] = "from_zero"
        result["percent"] = None
    elif abs(late_mean) < 1e-9:
        result["kind"] = "to_zero"
        result["percent"] = None
    else:
        result["kind"] = "percent"
        result["percent"] = (late_mean - early_mean) / early_mean * 100.0
    return result


def trend_block(stats: list[YearStat], field: str) -> dict | None:
    pairs = [(row.year, float(getattr(row, field))) for row in stats if row.usable and getattr(row, field) is not None]
    if len(pairs) < 8:
        return None
    years = [year for year, _ in pairs]
    values = [value for _, value in pairs]
    return {"linear": linear_trend(years, values), "mann_kendall": mann_kendall(years, values)}
