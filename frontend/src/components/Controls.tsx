import { useEffect, useMemo, useState } from "react"
import { geocode } from "@/api"
import { MapPanel } from "@/components/MapPanel"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { formatCoord } from "@/lib/format"
import type { AnalyzeRequest, BBox, Place } from "@/types"

const EXAMPLES = ["delhi", "phoenix", "london", "sydney", "rajasthan"]

export function Controls({
  draft,
  places,
  busy,
  samplePoints,
  onChange,
  onAnalyze,
}: {
  draft: AnalyzeRequest
  places: Place[]
  busy: boolean
  samplePoints: { latitude: number; longitude: number }[]
  onChange: (next: AnalyzeRequest) => void
  onAnalyze: () => void
}) {
  const [search, setSearch] = useState(draft.name ?? "")
  const [trackedName, setTrackedName] = useState(draft.name)
  const [open, setOpen] = useState(false)
  const [remote, setRemote] = useState<Place[]>([])
  const [searchError, setSearchError] = useState<string | null>(null)
  const [mapMode, setMapMode] = useState<"point" | "box">(draft.mode === "bbox" ? "box" : "point")
  if (draft.name !== trackedName) {
    setTrackedName(draft.name)
    setSearch(draft.name ?? "")
  }
  const visibleRemote = search.trim().length < 2 ? [] : remote

  useEffect(() => {
    const query = search.trim()
    if (query.length < 2) return
    const handle = window.setTimeout(() => {
      void geocode(query)
        .then((results) => {
          setRemote(results)
          setSearchError(null)
        })
        .catch((error: unknown) => {
          setRemote([])
          setSearchError(error instanceof Error ? error.message : "Search failed")
        })
    }, 280)
    return () => window.clearTimeout(handle)
  }, [search])

  const localMatches = useMemo(() => {
    const query = search.trim().toLowerCase()
    const pool = query
      ? places.filter((place) => `${place.name} ${place.admin} ${place.country}`.toLowerCase().includes(query))
      : places
    return pool.slice(0, 8)
  }, [places, search])

  function choose(place: Place) {
    onChange({
      ...draft,
      region_id: place.id,
      name: place.name,
      mode: place.kind === "region" ? "region" : "city",
      latitude: place.latitude,
      longitude: place.longitude,
      bbox: place.bbox,
    })
    setMapMode("point")
    setOpen(false)
  }

  function setYears(field: "start_year" | "end_year" | "baseline_start_year" | "baseline_end_year", value: string) {
    const parsed = Number(value)
    if (!Number.isFinite(parsed)) return
    onChange({ ...draft, [field]: parsed })
  }

  const examples = EXAMPLES.map((id) => places.find((place) => place.id === id)).filter((place): place is Place => Boolean(place))

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-medium tracking-[0.14em] text-muted uppercase">Hazard</p>
        <div className="grid grid-cols-3 gap-1 rounded-full bg-sand p-1" role="radiogroup" aria-label="Hazard type">
          <button
            type="button"
            role="radio"
            aria-checked="true"
            className="rounded-full bg-card px-2 py-1.5 text-xs font-medium text-ink shadow-sm"
          >
            Heatwave
          </button>
          <button type="button" role="radio" aria-checked="false" disabled className="rounded-full px-2 py-1.5 text-xs text-muted" title="Not implemented">
            Drought
          </button>
          <button type="button" role="radio" aria-checked="false" disabled className="rounded-full px-2 py-1.5 text-xs text-muted" title="Not implemented">
            Heavy rain
          </button>
        </div>
      </div>

      {examples.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {examples.map((place) => (
            <button
              key={place.id}
              type="button"
              onClick={() => choose(place)}
              className="rounded-full border border-line bg-white px-2.5 py-1 text-xs text-ink hover:border-tide/40"
            >
              {place.name}
            </button>
          ))}
        </div>
      )}

      <div className="relative">
        <label htmlFor="place-search" className="mb-1.5 block text-sm font-medium">
          City, state, or region
        </label>
        <Input
          id="place-search"
          value={search}
          placeholder="Search Jaipur, California, Cairo…"
          autoComplete="off"
          onChange={(event) => {
            setSearch(event.target.value)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 160)}
        />
        {open && (localMatches.length > 0 || visibleRemote.length > 0) && (
          <div className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-xl border border-line bg-card p-1 shadow-lg">
            {localMatches.length > 0 && <p className="px-2 pt-1 text-[11px] tracking-wide text-muted uppercase">Catalog</p>}
            {localMatches.map((place) => (
              <PlaceRow key={place.id} place={place} onPick={() => choose(place)} />
            ))}
            {visibleRemote.length > 0 && <p className="px-2 pt-2 text-[11px] tracking-wide text-muted uppercase">Open-Meteo places</p>}
            {visibleRemote.map((place) => (
              <PlaceRow key={place.id} place={place} onPick={() => choose(place)} />
            ))}
          </div>
        )}
        {searchError && <p className="mt-1 text-xs text-heat-deep">{searchError}</p>}
      </div>

      <div>
        <p className="mb-1.5 text-sm font-medium">Map selection</p>
        <div className="mb-2 grid grid-cols-2 gap-1 rounded-full bg-sand p-1">
          <button
            type="button"
            className={`rounded-full px-2 py-1.5 text-xs ${mapMode === "point" ? "bg-card font-medium shadow-sm" : "text-muted"}`}
            onClick={() => setMapMode("point")}
          >
            Drop a point
          </button>
          <button
            type="button"
            className={`rounded-full px-2 py-1.5 text-xs ${mapMode === "box" ? "bg-card font-medium shadow-sm" : "text-muted"}`}
            onClick={() => setMapMode("box")}
          >
            Draw a box
          </button>
        </div>
        <p className="mb-2 text-xs leading-relaxed text-muted">
          {mapMode === "box"
            ? "Click one corner, then the opposite corner. Boxes stay within 15° so the sample stays regional."
            : "Click the map to analyze that coordinate. Teal dots, after a run, are the points actually sampled."}
        </p>
        <MapPanel
          latitude={draft.latitude ?? 20}
          longitude={draft.longitude ?? 0}
          bbox={draft.mode === "city" ? null : draft.bbox}
          samplePoints={samplePoints}
          selectionMode={mapMode}
          onPoint={(latitude, longitude) =>
            onChange({
              ...draft,
              region_id: null,
              mode: "city",
              name: formatCoord(latitude, longitude),
              latitude,
              longitude,
              bbox: null,
            })
          }
          onBox={(box) =>
            onChange({
              ...draft,
              region_id: null,
              mode: "bbox",
              name: "Custom box",
              latitude: (box.south + box.north) / 2,
              longitude: (box.west + box.east) / 2,
              bbox: roundBox(box),
            })
          }
        />
      </div>

      {draft.mode === "bbox" && draft.bbox && (
        <div className="grid grid-cols-2 gap-2">
          <NumberField label="North" value={draft.bbox.north} onChange={(north) => onChange({ ...draft, bbox: { ...draft.bbox!, north } })} />
          <NumberField label="South" value={draft.bbox.south} onChange={(south) => onChange({ ...draft, bbox: { ...draft.bbox!, south } })} />
          <NumberField label="West" value={draft.bbox.west} onChange={(west) => onChange({ ...draft, bbox: { ...draft.bbox!, west } })} />
          <NumberField label="East" value={draft.bbox.east} onChange={(east) => onChange({ ...draft, bbox: { ...draft.bbox!, east } })} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <NumberField label="Start year" value={draft.start_year} onChange={(value) => setYears("start_year", String(value))} />
        <NumberField label="End year" value={draft.end_year} onChange={(value) => setYears("end_year", String(value))} />
      </div>

      <details className="rounded-xl border border-line bg-white px-3 py-2">
        <summary className="cursor-pointer text-sm font-medium">Threshold settings</summary>
        <div className="mt-3 space-y-3">
          <p className="text-xs leading-relaxed text-muted">
            The percentile is taken from the baseline years and then held fixed. Later warming can show up as more days above that historical extreme.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <NumberField
              label="Baseline start"
              value={draft.baseline_start_year}
              onChange={(value) => setYears("baseline_start_year", String(value))}
            />
            <NumberField
              label="Baseline end"
              value={draft.baseline_end_year}
              onChange={(value) => setYears("baseline_end_year", String(value))}
            />
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Percentile</p>
            <div className="flex flex-wrap gap-1.5">
              {[90, 95, 97, 99].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onChange({ ...draft, percentile: value })}
                  className={`rounded-full px-2.5 py-1 text-xs ${draft.percentile === value ? "bg-tide text-white" : "border border-line bg-card"}`}
                >
                  {value}th{value === 95 ? " · default" : ""}
                </button>
              ))}
            </div>
          </div>
          <div>
            <p className="mb-1.5 text-xs font-medium text-muted">Minimum run</p>
            <div className="flex gap-1.5">
              {[3, 4, 5].map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => onChange({ ...draft, min_duration: value })}
                  className={`rounded-full px-2.5 py-1 text-xs ${draft.min_duration === value ? "bg-tide text-white" : "border border-line bg-card"}`}
                >
                  {value} days
                </button>
              ))}
            </div>
          </div>
        </div>
      </details>

      <Button type="button" className="w-full" size="lg" disabled={busy} onClick={onAnalyze}>
        {busy ? "Analyzing temperatures…" : "Analyze heatwaves"}
      </Button>
    </div>
  )
}

function PlaceRow({ place, onPick }: { place: Place; onPick: () => void }) {
  return (
    <button
      type="button"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onPick}
      className="flex w-full items-baseline justify-between gap-3 rounded-lg px-2 py-1.5 text-left hover:bg-sand"
    >
      <span className="text-sm">
        {place.name}
        <span className="text-muted"> · {place.admin || place.country}</span>
      </span>
      <span className="shrink-0 text-[11px] tracking-wide text-muted uppercase">{place.kind === "region" ? "Region" : place.country}</span>
    </button>
  )
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  return (
    <label className="block text-xs font-medium text-muted">
      {label}
      <Input
        className="mt-1"
        type="number"
        inputMode="decimal"
        value={Number.isFinite(value) ? value : ""}
        onChange={(event) => onChange(Number(event.target.value))}
      />
    </label>
  )
}

function roundBox(box: BBox): BBox {
  const round = (value: number) => Math.round(value * 100) / 100
  return { west: round(box.west), south: round(box.south), east: round(box.east), north: round(box.north) }
}
