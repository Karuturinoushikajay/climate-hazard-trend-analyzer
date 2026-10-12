import { useEffect, useMemo, useRef, useState } from "react"
import { analyze, downloadExport, fetchRegions } from "@/api"
import { Controls } from "@/components/Controls"
import { Results } from "@/components/Results"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { defaultRequest, validateRequest } from "@/lib/format"
import type { Analysis, AnalyzeRequest, Place } from "@/types"

export default function App() {
  const [draft, setDraft] = useState<AnalyzeRequest>(defaultRequest)
  const [places, setPlaces] = useState<Place[]>([])
  const [result, setResult] = useState<Analysis | null>(null)
  const [status, setStatus] = useState<"idle" | "loading" | "error">("idle")
  const [error, setError] = useState<string | null>(null)
  const [exporting, setExporting] = useState<"csv" | "pdf" | null>(null)
  const [exportError, setExportError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    void fetchRegions()
      .then((catalog) => setPlaces([...catalog.cities, ...catalog.regions]))
      .catch(() => setPlaces([]))
  }, [])

  useEffect(() => {
    void run(defaultRequest())
    return () => abortRef.current?.abort()
  }, [])

  async function run(request: AnalyzeRequest) {
    const problem = validateRequest(request)
    if (problem) {
      setError(problem)
      setStatus("error")
      return
    }
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    setStatus("loading")
    setError(null)
    setExportError(null)
    try {
      const analysis = await analyze(request, controller.signal)
      if (!controller.signal.aborted) {
        setResult(analysis)
        setStatus("idle")
      }
    } catch (caught) {
      if (controller.signal.aborted) return
      setStatus("error")
      setError(caught instanceof Error ? caught.message : "The analysis could not be completed.")
    }
  }

  async function exportFile(kind: "csv" | "pdf") {
    if (!result) return
    setExporting(kind)
    setExportError(null)
    try {
      await downloadExport(kind, result)
    } catch (caught) {
      setExportError(caught instanceof Error ? caught.message : "Export failed.")
    } finally {
      setExporting(null)
    }
  }

  const samplePoints = useMemo(() => {
    if (!result) return []
    if (result.region.id && result.region.id === draft.region_id) return result.region.sample_points
    if (draft.name && result.region.name === draft.name) return result.region.sample_points
    return []
  }, [draft.name, draft.region_id, result])

  return (
    <div className="min-h-screen">
      <header className="border-b border-line/80">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-xs font-medium tracking-[0.16em] text-tide uppercase">Heatwave climatology</p>
            <h1 className="font-serif text-3xl tracking-tight md:text-4xl">Climate Hazard Trend Analyzer</h1>
          </div>
          <p className="max-w-sm text-sm leading-relaxed text-muted md:text-right">
            Daily maximum temperature from the Open-Meteo archive, scored against a fixed historical percentile.
          </p>
        </div>
      </header>
      <main className="mx-auto grid max-w-7xl gap-6 px-4 py-6 lg:grid-cols-[340px_minmax(0,1fr)]">
        <aside className="space-y-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:self-start lg:overflow-auto lg:pr-1">
          <Card className="p-4">
            <Controls
              draft={draft}
              places={places}
              busy={status === "loading"}
              samplePoints={samplePoints}
              onChange={setDraft}
              onAnalyze={() => void run(draft)}
            />
          </Card>
        </aside>
        <section className="min-w-0 space-y-4">
          {status === "loading" && !result && <Loading />}
          {status === "error" && (
            <Card className="p-5">
              <h2 className="font-serif text-2xl">The analysis did not finish</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted">{error}</p>
              <Button type="button" className="mt-4" onClick={() => void run(draft)}>
                Try again
              </Button>
            </Card>
          )}
          {exportError && <p className="text-sm text-heat-deep">{exportError}</p>}
          {result && (
            <div className={status === "loading" ? "opacity-60" : undefined}>
              <Results analysis={result} exporting={exporting} onExport={(kind) => void exportFile(kind)} />
            </div>
          )}
        </section>
      </main>
      <footer className="border-t border-line/80">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-5 text-xs leading-relaxed text-muted md:flex-row md:justify-between">
          <p>
            Temperatures:{" "}
            <a className="underline decoration-line underline-offset-2" href="https://open-meteo.com/" target="_blank" rel="noreferrer">
              Open-Meteo
            </a>{" "}
            archive (ERA5, Copernicus). Map tiles © OpenStreetMap © CARTO.
          </p>
          <p>A heatwave here is a run of days strictly above a baseline percentile, not an official warning.</p>
        </div>
      </footer>
    </div>
  )
}

function Loading() {
  return (
    <Card className="p-5">
      <p className="text-xs font-medium tracking-[0.14em] text-tide uppercase">Reading the archive</p>
      <h2 className="mt-2 font-serif text-2xl">Pulling daily maximum temperature</h2>
      <p className="mt-2 max-w-xl text-sm leading-relaxed text-muted">
        The first look at a place can take half a minute. The series is written to the document store, so the next request for the same years is a database read.
      </p>
      <div className="mt-5 space-y-2">
        <div className="h-3 w-2/3 animate-pulse rounded-full bg-sand" />
        <div className="h-3 w-1/2 animate-pulse rounded-full bg-sand" />
        <div className="h-28 animate-pulse rounded-2xl bg-sand" />
      </div>
    </Card>
  )
}
