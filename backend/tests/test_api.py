"""API validation, caching, exports, and the featured-region catalog."""

from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.data.regions import CITIES, REGIONS, sample_points
from app.db.store import TinyStore
from app.models.schemas import AnalyzeRequest
from app.sanitize import csv_safe
from app.services.analysis import run_analysis
from app.services.exporting import build_csv, build_pdf


def _series(start: date, end: date, warming: bool) -> list[tuple[date, float]]:
    cursor = start
    rows: list[tuple[date, float]] = []
    while cursor <= end:
        doy = cursor.timetuple().tm_yday
        seasonal = 24 + 11 * math.cos((doy - 200) * 2 * math.pi / 365.25)
        trend = max(0, cursor.year - 1990) * (0.15 if warming else 0.0)
        rows.append((cursor, seasonal + trend))
        cursor += timedelta(days=1)
    return rows


def test_catalog_boxes_are_small_enough_to_sample():
    assert any(city["id"] == "delhi" for city in CITIES)
    for region in REGIONS:
        box = region["bbox"]
        points = sample_points(
            region["latitude"],
            region["longitude"],
            (box["west"], box["south"], box["east"], box["north"]),
        )
        assert 1 <= len(points) <= 4
    delhi = sample_points(28.6139, 77.2090, None)
    assert delhi == [(28.61, 77.21)]
    with pytest.raises(ValueError):
        sample_points(10, 10, (0, 0, 20, 10))


def test_run_analysis_caches_weather_and_the_finished_result(tmp_path):
    store = TinyStore(tmp_path / "docs.json")
    calls: list[tuple] = []

    def fetcher(lat, lon, start, end):
        calls.append((lat, lon, start, end))
        return _series(start, end, warming=True)

    body = AnalyzeRequest(
        region_id="delhi",
        start_year=1990,
        end_year=2015,
        baseline_start_year=1961,
        baseline_end_year=1990,
    )
    first = run_analysis(body, store, fetcher, today=date(2026, 10, 12))
    assert calls and calls[0][0] == 28.61 and calls[0][1] == 77.21
    assert first["cached"] is False
    assert first["cache"]["weather"] == "miss"
    assert first["insight"]["direction"] == "increase"
    assert first["threshold"]["celsius"] > 20
    assert first["summary"]["total_heatwave_days"] > 0
    assert first["trends"]["heatwave_days"]["mann_kendall"]["significant"] is True
    assert len(first["annual"]) == 26

    second = run_analysis(body, store, fetcher, today=date(2026, 10, 12))
    assert second["cached"] is True
    assert second["cache"]["analysis"] == "hit"
    assert len(calls) == 1

    cooler = body.model_copy(update={"percentile": 90})
    third = run_analysis(cooler, store, fetcher, today=date(2026, 10, 12))
    assert third["cached"] is False
    assert third["cache"]["weather"] == "hit"
    assert len(calls) == 1
    assert third["summary"]["total_heatwave_days"] >= first["summary"]["total_heatwave_days"]


def test_state_region_samples_four_points(tmp_path):
    store = TinyStore(tmp_path / "docs.json")
    calls: list[tuple] = []

    def fetcher(lat, lon, start, end):
        calls.append((round(lat, 2), round(lon, 2)))
        return _series(start, end, warming=False)

    body = AnalyzeRequest(region_id="rajasthan", start_year=2000, end_year=2012, baseline_start_year=1980, baseline_end_year=1999)
    result = run_analysis(body, store, fetcher, today=date(2026, 10, 12))
    assert len(calls) == 4
    assert result["cache"]["points"] == 4
    assert result["region"]["name"] == "Rajasthan"
    assert result["region"]["mode"] == "region"


def test_health_validation_geocode_and_export(client, monkeypatch):
    health = client.get("/api/health")
    assert health.status_code == 200
    assert health.json()["store"] == "tinydb"
    assert health.headers["x-content-type-options"] == "nosniff"

    short = client.post(
        "/api/analyze",
        json={"region_id": "delhi", "start_year": 2018, "end_year": 2020},
    )
    assert short.status_code == 422

    drought = client.post(
        "/api/analyze",
        json={"hazard": "drought", "region_id": "delhi", "start_year": 1990, "end_year": 2005},
    )
    assert drought.status_code == 422

    huge = client.post(
        "/api/analyze",
        json={
            "mode": "bbox",
            "name": "Too big",
            "bbox": {"west": 70, "south": 8, "east": 90, "north": 20},
            "start_year": 1990,
            "end_year": 2005,
        },
    )
    assert huge.status_code == 422

    unknown = client.post("/api/analyze", json={"region_id": "atlantis", "start_year": 1990, "end_year": 2005})
    assert unknown.status_code == 400

    script = client.get("/api/geocode", params={"q": "<script>"})
    assert script.status_code == 400

    def fake_geocode(query: str):
        return [
            {
                "id": "om-1",
                "name": "Jaipur",
                "kind": "city",
                "country": "India",
                "admin": "Rajasthan",
                "latitude": 26.9,
                "longitude": 75.8,
                "population": 3000000,
                "bbox": None,
            }
        ]

    monkeypatch.setattr("app.services.open_meteo.geocode_places", fake_geocode)
    found = client.get("/api/geocode", params={"q": "Jaipur"})
    assert found.status_code == 200
    assert found.json()["results"][0]["name"] == "Jaipur"
    again = client.get("/api/geocode", params={"q": "jaipur"})
    assert again.json()["cached"] is True

    calls: list[int] = []

    def fetcher(lat, lon, start, end):
        calls.append(1)
        return _series(start, end, warming=True)

    monkeypatch.setattr("app.services.open_meteo.fetch_daily_tmax", fetcher)
    from app.limiter import limiter

    limiter.enabled = True
    analyzed = client.post(
        "/api/analyze",
        json={
            "region_id": "phoenix",
            "start_year": 1995,
            "end_year": 2010,
            "baseline_start_year": 1971,
            "baseline_end_year": 1990,
        },
    )
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert "Heatwave" in body["hazard"]["name"]
    assert body["region"]["name"] == "Phoenix"
    assert body["annual"]

    exported = client.post("/api/export/csv", json={"analysis": body})
    assert exported.status_code == 200
    assert "Phoenix" in exported.text
    assert exported.text.startswith("\ufeff")

    pdf = client.post("/api/export/pdf", json={"analysis": body})
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")

    rejected = client.post("/api/export/csv", json={"analysis": {"insight": {"headline": ""}, "annual": [], "events": []}})
    assert rejected.status_code == 422


def test_csv_formula_injection_is_neutralized():
    assert csv_safe("=HYPERLINK(\"http://example.test\")") == "'=HYPERLINK(\"http://example.test\")"
    assert csv_safe(-12.5) == -12.5
    text = build_csv(
        {
            "region": {"name": "=cmd"},
            "period": {"start_year": 1990, "end_year": 2000},
            "threshold": {"celsius": 40, "percentile": 95, "min_duration_days": 3},
            "insight": {"headline": "No heatwaves were detected in =cmd between 1990–1999 and 2000–2009."},
            "summary": {"total_events": 0, "total_heatwave_days": 0},
            "annual": [{"year": 1990, "usable": True, "events": 0, "heatwave_days": 0}],
            "events": [],
            "assumptions": [],
            "trends": {},
        }
    )
    assert "'=cmd" in text
    assert build_pdf(
        {
            "region": {"name": "Delhi"},
            "period": {"start_year": 1990, "end_year": 2000, "baseline_start_year": 1961, "baseline_end_year": 1990},
            "threshold": {"celsius": 40.2, "percentile": 95, "min_duration_days": 3},
            "insight": {"headline": "No heatwaves were detected.", "detail": "Threshold 40.2°C."},
            "summary": {"total_events": 0, "total_heatwave_days": 0, "mean_event_duration": None, "longest_event": None},
            "annual": [{"year": 1990, "events": 0, "heatwave_days": 0, "max_duration": 0, "annual_max": 38.0, "rolling_heatwave_days": None}],
            "events": [],
            "trends": {"heatwave_days": {"mann_kendall": None, "linear": None}},
            "assumptions": ["Fixed baseline threshold."],
        }
    ).startswith(b"%PDF")
