import type { Analysis, AnalyzeRequest, BBox, Place } from "@/types"

export function formatTemp(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—"
  return `${value.toFixed(1)}°C`
}

export function formatP(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—"
  if (value < 0.001) return "<0.001"
  return value.toFixed(3)
}

export function formatCount(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—"
  return value.toLocaleString("en-US", { maximumFractionDigits: digits, minimumFractionDigits: digits })
}

export function formatCoord(latitude: number, longitude: number): string {
  const ns = latitude >= 0 ? "N" : "S"
  const ew = longitude >= 0 ? "E" : "W"
  return `${Math.abs(latitude).toFixed(2)}°${ns}, ${Math.abs(longitude).toFixed(2)}°${ew}`
}

export function formatBox(box: BBox): string {
  return `Custom box · ${formatCoord((box.south + box.north) / 2, (box.west + box.east) / 2)}`
}

export function currentYear(): number {
  return new Date().getFullYear()
}

export function defaultRequest(): AnalyzeRequest {
  return {
    hazard: "heatwave",
    region_id: "delhi",
    name: "Delhi",
    mode: "city",
    latitude: 28.6139,
    longitude: 77.209,
    bbox: null,
    start_year: 1990,
    end_year: Math.min(2025, currentYear()),
    baseline_start_year: 1961,
    baseline_end_year: 1990,
    percentile: 95,
    min_duration: 3,
  }
}

export function requestFromPlace(place: Place, previous: AnalyzeRequest): AnalyzeRequest {
  return {
    ...previous,
    region_id: place.id,
    name: place.name,
    mode: place.kind === "region" ? "region" : "city",
    latitude: place.latitude,
    longitude: place.longitude,
    bbox: place.bbox,
  }
}

export function cacheMessage(analysis: Analysis): string {
  if (analysis.cached || analysis.cache.analysis === "hit") return "Loaded a saved analysis from the database."
  if (analysis.cache.weather === "hit") return "Computed from temperatures already in the database."
  if (analysis.cache.weather === "mixed") return "Filled gaps from Open-Meteo and saved them in the database."
  return "Fetched the archive and saved it in the database."
}

export function insightBadge(insight: Analysis["insight"]): string {
  if (insight.direction === "mixed") return "Mixed signals"
  if (insight.direction === "none") return "No trend estimated"
  if (insight.direction === "flat") return "Little change"
  if (!insight.significant && insight.direction === "increase") return "Increase, not significant"
  if (!insight.significant && insight.direction === "decrease") return "Decrease, not significant"
  if (insight.direction === "increase") return "Significant increase"
  if (insight.direction === "decrease") return "Significant decrease"
  return "Inconclusive"
}

export function validateRequest(draft: AnalyzeRequest): string | null {
  if (draft.end_year < draft.start_year) return "End year must be on or after the start year."
  if (draft.end_year - draft.start_year + 1 < 10) return "Choose at least 10 years so a trend can be estimated."
  if (draft.end_year - draft.start_year + 1 > 80) return "Choose a range of 80 years or fewer."
  if (draft.baseline_end_year < draft.baseline_start_year) {
    return "Baseline end year must be on or after the baseline start."
  }
  if (draft.baseline_end_year - draft.baseline_start_year + 1 < 10) return "Baseline must cover at least 10 years."
  if (draft.mode === "bbox") {
    if (!draft.bbox) return "Draw a box on the map or enter its edges."
    const width = draft.bbox.east - draft.bbox.west
    const height = draft.bbox.north - draft.bbox.south
    if (width <= 0 || height <= 0) return "The box edges are out of order."
    if (width > 15 || height > 15) return "Keep the box within 15° on each side."
    if (width < 0.1 || height < 0.1) return "That box is too small. Drop a point instead."
  } else if (draft.region_id == null && (draft.latitude == null || draft.longitude == null)) {
    return "Choose a city, a state, or a point on the map."
  }
  return null
}
