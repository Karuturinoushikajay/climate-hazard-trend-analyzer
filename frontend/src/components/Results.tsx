import { useMemo, useState } from "react"
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { Download } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cacheMessage, formatCount, formatP, formatTemp, insightBadge } from "@/lib/format"
import type { Analysis, AnnualRow, HeatEvent, TrendBlock } from "@/types"

const HEAT = "#c4491d"
const TIDE = "#1d4a46"
const DEEP = "#8c3416"
const BAR = "#f0c2b2"

export function Results({
  analysis,
  exporting,
  onExport,
}: {
  analysis: Analysis
  exporting: "csv" | "pdf" | null
  onExport: (kind: "csv" | "pdf") => void
}) {
  const badge = insightBadge(analysis.insight)
  const daysTrend = analysis.trends.heatwave_days?.mann_kendall
  const quality = analysis.data_quality
  return (
    <div className="space-y-4">
      <Card className="p-5 md:p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <Badge>{badge}</Badge>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" disabled={exporting !== null} onClick={() => onExport("csv")}>
              <Download className="h-3.5 w-3.5" aria-hidden />
              {exporting === "csv" ? "Preparing…" : "CSV"}
            </Button>
            <Button type="button" variant="outline" size="sm" disabled={exporting !== null} onClick={() => onExport("pdf")}>
              <Download className="h-3.5 w-3.5" aria-hidden />
              {exporting === "pdf" ? "Preparing…" : "PDF"}
            </Button>
          </div>
        </div>
        <h2 className="mt-3 font-serif text-3xl leading-snug tracking-tight text-ink md:text-[2.15rem]" aria-live="polite">
          {analysis.insight.headline}
        </h2>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">{analysis.insight.detail}</p>
        <p className="mt-4 text-xs text-muted">
          {cacheMessage(analysis)} {quality.usable_years} complete years · {(quality.completeness * 100).toFixed(1)}% of days present ·{" "}
          {analysis.cache.points} sample {analysis.cache.points === 1 ? "point" : "points"} · threshold {formatTemp(analysis.threshold.celsius)}
        </p>
        {quality.low_data_years.length > 0 && (
          <p className="mt-2 text-xs text-heat-deep">
            Left out of the totals because fewer than 80% of days were present: {quality.low_data_years.join(", ")}.
          </p>
        )}
        {analysis.period.baseline_overlaps_analysis && (
          <p className="mt-2 text-xs text-muted">
            The baseline overlaps the analysis window, so those shared years help set the threshold and are also scored against it.
          </p>
        )}
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Heatwave events" value={formatCount(analysis.summary.total_events)} note={`${formatCount(analysis.summary.mean_annual_events, 1)} per year`} />
        <Stat label="Heatwave days" value={formatCount(analysis.summary.total_heatwave_days)} note={`${formatCount(analysis.summary.mean_annual_heatwave_days, 1)} per year`} />
        <Stat
          label="Longest spell"
          value={analysis.summary.longest_event ? `${analysis.summary.longest_event.duration} days` : "None"}
          note={analysis.summary.longest_event ? `${analysis.summary.longest_event.start} to ${analysis.summary.longest_event.end}` : "No run met the rule"}
        />
        <Stat
          label="Sen's slope"
          value={daysTrend ? `${daysTrend.sen_slope_per_decade > 0 ? "+" : ""}${daysTrend.sen_slope_per_decade.toFixed(2)}` : "—"}
          note={daysTrend ? `days/decade · p ${formatP(daysTrend.p_value)}` : "Not enough complete years"}
        />
      </div>

      <Card className="p-4 md:p-5">
        <Tabs defaultValue="charts">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h3 className="font-medium">Frequency, exposure, and intensity</h3>
              <p className="text-xs text-muted">Bars are annual values. The teal line is a {analysis.trends.rolling_window_years}-year centered mean. The dashed line is the linear fit.</p>
            </div>
            <TabsList aria-label="Result views">
              <TabsTrigger value="charts">Charts</TabsTrigger>
              <TabsTrigger value="table">Yearly table</TabsTrigger>
            </TabsList>
          </div>
          <TabsContent value="charts" className="space-y-6">
            <ChartBlock
              title="Events per year"
              caption={trendCaption(analysis.trends.events, "events")}
              data={analysis.annual}
              barKey="events"
              barName="Events"
              rollKey="rolling_events"
              fitKey="regression_events"
            />
            <ChartBlock
              title="Heatwave days per year"
              caption={trendCaption(analysis.trends.heatwave_days, "days")}
              data={analysis.annual}
              barKey="heatwave_days"
              barName="Heatwave days"
              rollKey="rolling_heatwave_days"
              fitKey="regression_heatwave_days"
            />
            <ChartBlock
              title="Hottest day each year"
              caption={trendCaption(analysis.trends.annual_max, "°C")}
              data={analysis.annual}
              barKey="annual_max"
              barName="Annual maximum"
              rollKey="rolling_annual_max"
              fitKey="regression_annual_max"
              variant="line"
              threshold={analysis.threshold.celsius}
            />
          </TabsContent>
          <TabsContent value="table">
            <YearTable rows={analysis.annual} />
          </TabsContent>
        </Tabs>
      </Card>

      <Card className="p-4 md:p-5">
        <h3 className="font-medium">Events</h3>
        <p className="mb-3 text-xs text-muted">
          {analysis.events.length === 0
            ? `No spell lasted ${analysis.threshold.min_duration_days} or more days above ${formatTemp(analysis.threshold.celsius)}.`
            : `${analysis.events.length} spells in complete years, longest first.`}
          {analysis.summary.hottest_day ? ` Hottest day ${analysis.summary.hottest_day.date} reached ${formatTemp(analysis.summary.hottest_day.tmax)}.` : ""}
        </p>
        {analysis.events.length > 0 && <EventsTable events={analysis.events} />}
      </Card>

      <Card className="p-4 md:p-5">
        <h3 className="font-medium">How this number was made</h3>
        <p className="mt-2 text-sm leading-relaxed text-muted">{analysis.hazard.definition}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <Fact term="Threshold" detail={`${formatTemp(analysis.threshold.celsius)} from ${analysis.threshold.baseline_valid_days.toLocaleString("en-US")} baseline days`} />
          <Fact term="Comparison" detail="Strictly above the threshold. Equal days do not count." />
          <Fact term="Source" detail={quality.source} />
          <Fact term="Sample" detail={analysis.region.sample_points.map((point) => `${point.latitude.toFixed(2)}, ${point.longitude.toFixed(2)}`).join(" · ")} />
        </dl>
        <ul className="mt-4 space-y-2 text-sm leading-relaxed text-muted">
          {analysis.assumptions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </Card>
    </div>
  )
}

function Stat({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <Card className="p-4">
      <p className="text-xs tracking-wide text-muted uppercase">{label}</p>
      <p className="mt-1 font-serif text-2xl tracking-tight">{value}</p>
      <p className="mt-1 text-xs text-muted">{note}</p>
    </Card>
  )
}

function Fact({ term, detail }: { term: string; detail: string }) {
  return (
    <div>
      <dt className="text-xs tracking-wide text-muted uppercase">{term}</dt>
      <dd className="mt-1">{detail}</dd>
    </div>
  )
}

function trendCaption(block: TrendBlock | null, unit: string): string {
  const mk = block?.mann_kendall
  const linear = block?.linear
  if (!mk && !linear) return "Not enough complete years for a trend line."
  const slope = mk ? `${mk.sen_slope_per_decade > 0 ? "+" : ""}${mk.sen_slope_per_decade.toFixed(2)} ${unit}/decade (Sen)` : ""
  const fit = linear ? `${linear.slope_per_decade > 0 ? "+" : ""}${linear.slope_per_decade.toFixed(2)} ${unit}/decade (linear, p ${formatP(linear.p_value)})` : ""
  const verdict = mk ? `${mk.trend}, p ${formatP(mk.p_value)}` : ""
  return [verdict, slope, fit].filter(Boolean).join(" · ")
}

type TipPayload = { name?: string; value?: number | string | null; color?: string }

function Tip({ active, payload, label }: { active?: boolean; payload?: TipPayload[]; label?: string | number }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-line bg-card px-3 py-2 text-xs shadow-sm">
      <p className="mb-1 font-medium">{label}</p>
      {payload.map((item) => (
        <p key={item.name} style={{ color: item.color }}>
          {item.name}: {item.value == null || item.value === "" ? "—" : item.value}
        </p>
      ))}
    </div>
  )
}

function ChartBlock({
  title,
  caption,
  data,
  barKey,
  barName,
  rollKey,
  fitKey,
  variant = "bar",
  threshold,
}: {
  title: string
  caption: string
  data: AnnualRow[]
  barKey: keyof AnnualRow
  barName: string
  rollKey: keyof AnnualRow
  fitKey: keyof AnnualRow
  variant?: "bar" | "line"
  threshold?: number
}) {
  return (
    <figure>
      <figcaption className="mb-2">
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted">{caption}</p>
      </figcaption>
      <div className="h-72 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="#e4dccf" vertical={false} />
            <XAxis dataKey="year" tick={{ fill: "#6d655c", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fill: "#6d655c", fontSize: 12 }} axisLine={false} tickLine={false} width={40} />
            <Tooltip content={<Tip />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            {threshold != null && <ReferenceLine y={threshold} stroke={DEEP} strokeDasharray="2 3" label={{ value: "Threshold", fill: DEEP, fontSize: 11 }} />}
            {variant === "bar" ? (
              <Bar dataKey={barKey} name={barName} fill={BAR} stroke={HEAT} radius={[3, 3, 0, 0]} />
            ) : (
              <Line dataKey={barKey} name={barName} stroke={HEAT} strokeWidth={2} dot={{ r: 2 }} connectNulls={false} />
            )}
            <Line dataKey={rollKey} name="5-year mean" stroke={TIDE} strokeWidth={2} dot={false} connectNulls={false} />
            <Line dataKey={fitKey} name="Linear trend" stroke={DEEP} strokeDasharray="5 4" strokeWidth={1.5} dot={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  )
}

function YearTable({ rows }: { rows: AnnualRow[] }) {
  return (
    <div className="max-h-96 overflow-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead className="sticky top-0 bg-card text-xs tracking-wide text-muted uppercase">
          <tr>
            <th className="py-2 pr-3 font-medium">Year</th>
            <th className="py-2 pr-3 font-medium">Events</th>
            <th className="py-2 pr-3 font-medium">Days</th>
            <th className="py-2 pr-3 font-medium">Longest</th>
            <th className="py-2 pr-3 font-medium">Annual max</th>
            <th className="py-2 font-medium">Complete</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.year} className="border-t border-line">
              <td className="py-1.5 pr-3">{row.year}</td>
              <td className="py-1.5 pr-3">{formatCount(row.events)}</td>
              <td className="py-1.5 pr-3">{formatCount(row.heatwave_days)}</td>
              <td className="py-1.5 pr-3">{formatCount(row.max_duration)}</td>
              <td className="py-1.5 pr-3">{formatTemp(row.annual_max)}</td>
              <td className="py-1.5">{row.usable ? `${Math.round(row.completeness * 100)}%` : "Insufficient"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function EventsTable({ events }: { events: HeatEvent[] }) {
  const [sort, setSort] = useState<"duration" | "start" | "max_tmax">("duration")
  const rows = useMemo(() => {
    const copy = [...events]
    copy.sort((a, b) => {
      if (sort === "start") return a.start.localeCompare(b.start)
      if (sort === "max_tmax") return b.max_tmax - a.max_tmax
      return b.duration - a.duration || b.max_tmax - a.max_tmax
    })
    return copy
  }, [events, sort])
  return (
    <div className="max-h-80 overflow-auto">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead className="sticky top-0 bg-card text-xs tracking-wide text-muted uppercase">
          <tr>
            <SortHeader label="Start" active={sort === "start"} onClick={() => setSort("start")} />
            <th className="py-2 pr-3 font-medium">End</th>
            <SortHeader label="Duration" active={sort === "duration"} onClick={() => setSort("duration")} />
            <th className="py-2 pr-3 font-medium">Mean</th>
            <SortHeader label="Max" active={sort === "max_tmax"} onClick={() => setSort("max_tmax")} />
          </tr>
        </thead>
        <tbody>
          {rows.map((event) => (
            <tr key={`${event.start}-${event.end}`} className="border-t border-line">
              <td className="py-1.5 pr-3">{event.start}</td>
              <td className="py-1.5 pr-3">{event.end}</td>
              <td className="py-1.5 pr-3">{event.duration} days</td>
              <td className="py-1.5 pr-3">{formatTemp(event.mean_tmax)}</td>
              <td className="py-1.5">{formatTemp(event.max_tmax)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SortHeader({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <th className="py-2 pr-3 font-medium">
      <button type="button" className={active ? "text-ink" : ""} onClick={onClick}>
        {label}
      </button>
    </th>
  )
}
