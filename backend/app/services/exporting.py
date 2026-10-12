"""CSV and PDF exports of an analysis the API already computed."""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.config import get_settings
from app.sanitize import ascii_fold, csv_safe, slug

ANNUAL_FIELDS = (
    "year",
    "usable",
    "events",
    "heatwave_days",
    "max_duration",
    "annual_max",
    "mean_excess",
    "rolling_heatwave_days",
    "regression_heatwave_days",
    "completeness",
)
EVENT_FIELDS = ("start", "end", "duration", "mean_tmax", "max_tmax", "peak_date")


def build_csv(analysis: dict) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    region = analysis.get("region") or {}
    period = analysis.get("period") or {}
    threshold = analysis.get("threshold") or {}
    insight = analysis.get("insight") or {}
    summary = analysis.get("summary") or {}
    writer.writerow(["record_type", "field", "value"])
    meta = {
        "region": region.get("name"),
        "mode": region.get("mode"),
        "start_year": period.get("start_year"),
        "end_year": period.get("end_year"),
        "baseline_start_year": period.get("baseline_start_year"),
        "baseline_end_year": period.get("baseline_end_year"),
        "threshold_c": threshold.get("celsius"),
        "percentile": threshold.get("percentile"),
        "min_duration_days": threshold.get("min_duration_days"),
        "headline": insight.get("headline"),
        "total_events": summary.get("total_events"),
        "total_heatwave_days": summary.get("total_heatwave_days"),
    }
    for field, value in meta.items():
        writer.writerow(["meta", field, csv_safe(value)])
    writer.writerow([])
    writer.writerow(["record_type", *ANNUAL_FIELDS])
    for row in analysis.get("annual") or []:
        if not isinstance(row, dict):
            continue
        writer.writerow(["annual", *[csv_safe(row.get(field)) for field in ANNUAL_FIELDS]])
    writer.writerow([])
    writer.writerow(["record_type", *EVENT_FIELDS])
    for row in analysis.get("events") or []:
        if not isinstance(row, dict):
            continue
        writer.writerow(["event", *[csv_safe(row.get(field)) for field in EVENT_FIELDS]])
    return "\ufeff" + buffer.getvalue()


def export_filename(analysis: dict, extension: str) -> str:
    region = (analysis.get("region") or {}).get("name") or "region"
    period = analysis.get("period") or {}
    start = period.get("start_year") or "start"
    end = period.get("end_year") or "end"
    return f"heatwave-{slug(region)}-{start}-{end}.{extension}"


def _font_ready() -> tuple[bool, str, str]:
    settings = get_settings()
    regular = Path(settings.font_regular)
    bold = Path(settings.font_bold)
    if regular.is_file() and bold.is_file():
        return True, str(regular), str(bold)
    return False, "", ""


def build_pdf(analysis: dict) -> bytes:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos

    unicode_font, regular, bold = _font_ready()
    family = "Report" if unicode_font else "Helvetica"

    def text(value: object) -> str:
        raw = "" if value is None else str(value)
        raw = " ".join(raw.replace("\n", " ").split())
        if unicode_font:
            return raw
        return ascii_fold(raw)

    class Report(FPDF):
        def footer(self) -> None:
            self.set_y(-12)
            self.set_font(family, "", 8)
            self.set_text_color(90, 84, 76)
            self.cell(0, 8, text(f"Open-Meteo ERA5  ·  page {self.page_no()}"), align="C")

    pdf = Report(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(14, 14, 14)
    if unicode_font:
        pdf.add_font("Report", "", regular)
        pdf.add_font("Report", "B", bold)

    region = analysis.get("region") or {}
    period = analysis.get("period") or {}
    threshold = analysis.get("threshold") or {}
    insight = analysis.get("insight") or {}
    summary = analysis.get("summary") or {}
    trends = ((analysis.get("trends") or {}).get("heatwave_days") or {})
    mk = trends.get("mann_kendall") or {}
    linear = trends.get("linear") or {}

    pdf.add_page()
    pdf.set_title(text(f"Heatwave trend — {region.get('name') or 'Region'}"))
    pdf.set_font(family, "B", 16)
    pdf.set_text_color(28, 25, 21)
    pdf.multi_cell(0, 8, text("Climate Hazard Trend Analyzer"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, "", 11)
    pdf.set_text_color(109, 101, 92)
    pdf.multi_cell(
        0,
        6,
        text(
            f"{region.get('name') or 'Region'}  ·  heatwave  ·  "
            f"{period.get('start_year')}–{period.get('end_year')}"
        ),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(2)
    pdf.set_text_color(28, 25, 21)
    pdf.set_font(family, "B", 13)
    pdf.multi_cell(0, 7, text(insight.get("headline")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(1)
    pdf.set_font(family, "", 10)
    pdf.multi_cell(0, 5, text(insight.get("detail")), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(3)

    pdf.set_font(family, "B", 11)
    pdf.cell(0, 7, text("Summary"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, "", 10)
    longest = summary.get("longest_event") or {}
    rows = [
        ("Threshold", f"{threshold.get('celsius')} °C ({threshold.get('percentile')}th percentile)"),
        ("Baseline", f"{period.get('baseline_start_year')}–{period.get('baseline_end_year')}"),
        ("Heatwave events", summary.get("total_events")),
        ("Heatwave days", summary.get("total_heatwave_days")),
        ("Longest spell", f"{longest.get('duration')} days ({longest.get('start')} to {longest.get('end')})" if longest else "None"),
        ("Mean event duration", summary.get("mean_event_duration")),
        ("Sen's slope", f"{mk.get('sen_slope_per_decade')} days/decade" if mk else "n/a"),
        ("Mann–Kendall p", mk.get("p_value") if mk else "n/a"),
        ("Linear slope", f"{linear.get('slope_per_decade')} days/decade" if linear else "n/a"),
    ]
    for label, value in rows:
        pdf.set_font(family, "B", 9)
        pdf.cell(55, 6, text(label))
        pdf.set_font(family, "", 9)
        pdf.cell(0, 6, text(value), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(2)

    pdf.set_font(family, "B", 11)
    pdf.cell(0, 7, text("Annual series"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, "B", 8)
    widths = (18, 22, 32, 28, 28, 28)
    headers = ("Year", "Events", "Heatwave days", "Max duration", "Annual max", "5-year mean")
    for header, width in zip(headers, widths, strict=True):
        pdf.cell(width, 6, text(header))
    pdf.ln(6)
    pdf.set_font(family, "", 8)
    for row in analysis.get("annual") or []:
        if not isinstance(row, dict):
            continue
        values = (
            row.get("year"),
            "—" if row.get("events") is None else row.get("events"),
            "—" if row.get("heatwave_days") is None else row.get("heatwave_days"),
            "—" if row.get("max_duration") is None else row.get("max_duration"),
            "—" if row.get("annual_max") is None else row.get("annual_max"),
            "—" if row.get("rolling_heatwave_days") is None else row.get("rolling_heatwave_days"),
        )
        for value, width in zip(values, widths, strict=True):
            pdf.cell(width, 5, text(value))
        pdf.ln(5)

    pdf.ln(2)
    pdf.set_font(family, "B", 11)
    pdf.cell(0, 7, text("Longest events"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(family, "B", 8)
    event_widths = (28, 28, 22, 28, 28)
    event_headers = ("Start", "End", "Duration", "Mean °C", "Max °C")
    for header, width in zip(event_headers, event_widths, strict=True):
        pdf.cell(width, 6, text(header))
    pdf.ln(6)
    pdf.set_font(family, "", 8)
    events = [item for item in (analysis.get("events") or []) if isinstance(item, dict)][:15]
    if not events:
        pdf.cell(0, 6, text("No events met the definition."), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    for row in events:
        values = (row.get("start"), row.get("end"), row.get("duration"), row.get("mean_tmax"), row.get("max_tmax"))
        for value, width in zip(values, event_widths, strict=True):
            pdf.cell(width, 5, text(value))
        pdf.ln(5)

    assumptions = analysis.get("assumptions") or []
    if assumptions:
        pdf.ln(3)
        pdf.set_font(family, "B", 11)
        pdf.cell(0, 7, text("Assumptions"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font(family, "", 8)
        for item in assumptions:
            if isinstance(item, str):
                pdf.multi_cell(0, 4, text(f"• {item}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
                pdf.ln(1)

    output = pdf.output()
    return bytes(output)
