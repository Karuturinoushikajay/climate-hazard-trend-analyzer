import type { Analysis, AnalyzeRequest, Place } from "@/types"

const base = import.meta.env.VITE_API_BASE ?? ""

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") return body.detail
    if (Array.isArray(body.detail)) {
      const messages = body.detail
        .map((item) => (item && typeof item === "object" && "msg" in item ? String(item.msg) : ""))
        .filter(Boolean)
      if (messages.length) return messages.join(" ")
    }
  } catch {
    return `Request failed (${response.status})`
  }
  return `Request failed (${response.status})`
}

export async function fetchRegions(): Promise<{ cities: Place[]; regions: Place[] }> {
  const response = await fetch(`${base}/api/regions`)
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<{ cities: Place[]; regions: Place[] }>
}

export async function geocode(query: string): Promise<Place[]> {
  const response = await fetch(`${base}/api/geocode?q=${encodeURIComponent(query)}`)
  if (!response.ok) throw new Error(await readError(response))
  const body = (await response.json()) as { results: Place[] }
  return body.results
}

export async function analyze(body: AnalyzeRequest, signal?: AbortSignal): Promise<Analysis> {
  const response = await fetch(`${base}/api/analyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(body),
    signal,
  })
  if (!response.ok) throw new Error(await readError(response))
  return response.json() as Promise<Analysis>
}

export async function downloadExport(kind: "csv" | "pdf", analysis: Analysis): Promise<void> {
  const response = await fetch(`${base}/api/export/${kind}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ analysis }),
  })
  if (!response.ok) throw new Error(await readError(response))
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  const disposition = response.headers.get("Content-Disposition") ?? ""
  const match = disposition.match(/filename="([^"]+)"/)
  link.href = url
  link.download = match?.[1] ?? `heatwave-trend.${kind}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
