"""HTTP API for region lookup, heatwave analysis, and exports."""

from __future__ import annotations

import re

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from app.data.regions import CITIES, REGIONS
from app.errors import APIError
from app.models.schemas import AnalyzeRequest, ExportRequest
from app.services import open_meteo
from app.services.analysis import run_analysis
from app.services.exporting import build_csv, build_pdf, export_filename
from app.limiter import limiter

router = APIRouter(prefix="/api")

_QUERY = re.compile(r"[\w .,'’\-+()]+", flags=re.UNICODE)


def clean_query(query: str) -> str:
    text = " ".join(query.split())
    if len(text) < 2 or len(text) > 80:
        raise APIError(400, "Search must be between 2 and 80 characters")
    if any(ord(char) < 32 for char in text) or _QUERY.fullmatch(text) is None:
        raise APIError(400, "Search contains invalid characters")
    return text


def cached_geocode(store, query: str) -> tuple[list[dict], bool]:
    key = query.casefold()
    hit = store.get_document("geocode", key)
    if hit and isinstance(hit.get("results"), list):
        return hit["results"], True
    results = open_meteo.geocode_places(query)
    store.put_document("geocode", key, {"query": query, "results": results})
    return results, False


@router.get("/health")
def health(request: Request) -> dict:
    store = request.app.state.store
    return {"status": "ok", "store": store.kind, "hazard": "heatwave"}


@router.get("/hazards")
def hazards() -> dict:
    return {
        "hazards": [
            {
                "id": "heatwave",
                "name": "Heatwave",
                "enabled": True,
                "summary": "3 or more consecutive days above the local baseline 95th percentile of daily maximum temperature.",
            },
            {
                "id": "drought",
                "name": "Drought",
                "enabled": False,
                "summary": "Not implemented. Heatwave is the hazard this analyzer scores.",
            },
            {
                "id": "heavy-rain",
                "name": "Heavy rainfall",
                "enabled": False,
                "summary": "Not implemented. Heatwave is the hazard this analyzer scores.",
            },
        ]
    }


@router.get("/regions")
def regions() -> dict:
    return {"cities": CITIES, "regions": REGIONS}


@router.get("/geocode")
@limiter.limit("30/minute")
def geocode(request: Request, q: str = Query(min_length=2, max_length=80)) -> dict:
    query = clean_query(q)
    try:
        results, hit = cached_geocode(request.app.state.store, query)
    except Exception as exc:
        from app.errors import OpenMeteoError

        if isinstance(exc, OpenMeteoError):
            raise APIError(502, f"Place search failed: {exc}") from exc
        raise
    return {"query": query, "cached": hit, "results": results}


@router.post("/analyze")
@limiter.limit("10/minute")
def analyze(request: Request, body: AnalyzeRequest) -> dict:
    return run_analysis(body, request.app.state.store)


@router.post("/export/csv")
@limiter.limit("20/minute")
def export_csv(request: Request, body: ExportRequest) -> Response:
    payload = build_csv(body.analysis)
    filename = export_filename(body.analysis, "csv")
    return Response(
        content=payload,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/export/pdf")
@limiter.limit("20/minute")
def export_pdf(request: Request, body: ExportRequest) -> Response:
    payload = build_pdf(body.analysis)
    filename = export_filename(body.analysis, "pdf")
    return Response(
        content=payload,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
