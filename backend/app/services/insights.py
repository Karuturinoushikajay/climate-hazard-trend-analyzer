"""Plain-language reading of the trend numbers.

The headline describes the change in heatwave days between the early and late
part of the selected window. Statistical significance comes from the Mann–Kendall
test on the yearly series. A large percent change with a high p-value is reported
as a description, not as a detected trend.
"""

from __future__ import annotations


def format_p(p_value: float) -> str:
    if p_value < 0.001:
        return "<0.001"
    return f"{p_value:.3f}"


def format_percent(percent: float) -> str:
    magnitude = abs(percent)
    if magnitude >= 10:
        return f"{magnitude:.0f}%"
    return f"{magnitude:.1f}%"


def build_insight(
    *,
    region_name: str,
    change: dict | None,
    days_mk: dict | None,
    events_mk: dict | None,
    days_linear: dict | None,
    threshold_c: float,
    percentile: float,
    min_duration: int,
    baseline_start: int,
    baseline_end: int,
    baseline_days: int,
    usable_years: int,
) -> dict:
    kind = (change or {}).get("kind")
    if change is None or kind == "insufficient" or days_mk is None:
        return {
            "headline": (
                f"There are not enough complete years to judge a heatwave trend in {region_name}."
            ),
            "detail": (
                f"{usable_years} years have at least 80% of days present. "
                f"The threshold would be {threshold_c:.1f}°C, the {percentile:g}th percentile "
                f"of daily maxima in {baseline_start}–{baseline_end}."
            ),
            "significant": False,
            "direction": "none",
        }

    percent = change.get("percent")
    early = change["early_label"]
    late = change["late_label"]
    if kind == "both_zero":
        headline = f"No heatwaves were detected in {region_name} between {early} and {late}."
        direction = "none"
        about_same = False
    elif kind == "from_zero":
        headline = (
            f"{region_name} had no heatwave days in {early}, "
            f"then averaged {change['late_mean']:.1f} a year in {late}."
        )
        direction = "increase"
        about_same = False
    elif kind == "to_zero":
        headline = (
            f"{region_name} averaged {change['early_mean']:.1f} heatwave days a year in {early}, "
            f"then none in {late}."
        )
        direction = "decrease"
        about_same = False
    else:
        assert percent is not None
        about_same = abs(percent) < 1
        if about_same:
            headline = (
                f"Heatwave days in {region_name} stayed about the same from {early} to {late} "
                f"({format_percent(percent)} change)."
            )
            direction = "flat"
        else:
            verb = "increased" if percent > 0 else "decreased"
            headline = (
                f"Heatwave days in {region_name} {verb} by {format_percent(percent)} "
                f"from {early} to {late}"
            )
            direction = "increase" if percent > 0 else "decrease"
            if days_mk["significant"]:
                headline += "."
            else:
                headline += ", but the trend is not statistically significant."

    significant = bool(days_mk["significant"]) and direction in {"increase", "decrease"} and not about_same
    if kind == "both_zero":
        significant = False
        direction = "none"

    mixed = (
        events_mk is not None
        and days_mk["significant"]
        and events_mk["significant"]
        and days_mk["direction"] in {"increasing", "decreasing"}
        and events_mk["direction"] in {"increasing", "decreasing"}
        and days_mk["direction"] != events_mk["direction"]
    )
    if mixed and direction in {"increase", "decrease"}:
        direction = "mixed"

    detail_parts = [
        (
            f"A heatwave is {min_duration} or more consecutive days above {threshold_c:.1f}°C, "
            f"the {percentile:g}th percentile of daily maximum temperature during "
            f"{baseline_start}–{baseline_end} ({baseline_days} valid days)."
        ),
        (
            f"Mann–Kendall on annual heatwave days: {days_mk['trend']} "
            f"(p = {format_p(days_mk['p_value'])}, "
            f"Sen's slope {days_mk['sen_slope_per_decade']:+.2f} days/decade, n = {days_mk['n']})."
        ),
    ]
    if days_linear is not None:
        detail_parts.append(
            (
                f"Linear trend: {days_linear['slope_per_decade']:+.2f} days/decade "
                f"(p = {format_p(days_linear['p_value'])}, R² = {days_linear['r_squared']:.2f})."
            )
        )
    early_duration = change.get("early_mean_duration")
    late_duration = change.get("late_mean_duration")
    if early_duration is not None and late_duration is not None:
        detail_parts.append(
            f"Mean event duration went from {early_duration:.1f} to {late_duration:.1f} days."
        )
    elif late_duration is not None and kind == "from_zero":
        detail_parts.append(f"Events in the later window lasted {late_duration:.1f} days on average.")
    if mixed and events_mk is not None:
        detail_parts.append(
            (
                f"Event counts tell a different story ({events_mk['trend']}, "
                f"p = {format_p(events_mk['p_value'])}). "
                "Duration can shift even when the number of spells does not."
            )
        )
    if days_mk["n"] < 20:
        detail_parts.append(
            f"With only {days_mk['n']} complete years, that p-value is a rough normal approximation."
        )
    return {
        "headline": headline,
        "detail": " ".join(detail_parts),
        "significant": significant,
        "direction": direction,
    }
