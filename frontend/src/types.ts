export type BBox = {
  west: number
  south: number
  east: number
  north: number
}

export type Place = {
  id: string
  name: string
  kind: "city" | "region"
  country: string
  admin: string
  latitude: number
  longitude: number
  bbox: BBox | null
  population?: number | null
}

export type AnalyzeRequest = {
  hazard: "heatwave"
  region_id: string | null
  name: string | null
  mode: "city" | "region" | "bbox"
  latitude: number | null
  longitude: number | null
  bbox: BBox | null
  start_year: number
  end_year: number
  baseline_start_year: number
  baseline_end_year: number
  percentile: number
  min_duration: number
}

export type TrendNumbers = {
  slope_per_year: number
  slope_per_decade: number
  intercept: number
  r_squared: number
  p_value: number
}

export type MannKendall = {
  s: number
  z: number
  p_value: number
  variance: number
  significant: boolean
  direction: "increasing" | "decreasing" | "flat"
  trend: string
  sen_slope_per_year: number
  sen_slope_per_decade: number
  n: number
}

export type TrendBlock = {
  linear: TrendNumbers | null
  mann_kendall: MannKendall | null
}

export type AnnualRow = {
  year: number
  usable: boolean
  valid_days: number
  expected_days: number
  completeness: number
  events: number | null
  heatwave_days: number | null
  max_duration: number | null
  mean_heatwave_tmax: number | null
  mean_excess: number | null
  annual_max: number | null
  rolling_events: number | null
  rolling_heatwave_days: number | null
  rolling_annual_max: number | null
  regression_events: number | null
  regression_heatwave_days: number | null
  regression_annual_max: number | null
}

export type HeatEvent = {
  start: string
  end: string
  duration: number
  mean_tmax: number
  max_tmax: number
  peak_date: string
}

export type Analysis = {
  cached: boolean
  generated_at: string
  hazard: { id: string; name: string; definition: string }
  region: {
    id: string
    name: string
    mode: "city" | "region" | "bbox"
    latitude: number
    longitude: number
    bbox: BBox | null
    sample_points: { latitude: number; longitude: number }[]
  }
  period: {
    start_year: number
    end_year: number
    start_date: string
    end_date: string
    baseline_start_year: number
    baseline_end_year: number
    baseline_overlaps_analysis: boolean
  }
  threshold: {
    percentile: number
    celsius: number
    min_duration_days: number
    baseline_valid_days: number
    comparison: string
  }
  data_quality: {
    days_expected: number
    days_valid: number
    missing_days: number
    rejected_days: number
    completeness: number
    usable_years: number
    low_data_years: number[]
    source: string
    units: string
  }
  cache: { analysis: "hit" | "miss"; weather: "hit" | "mixed" | "miss"; points: number }
  summary: {
    total_events: number
    total_heatwave_days: number
    longest_event: HeatEvent | null
    mean_event_duration: number | null
    mean_annual_events: number
    mean_annual_heatwave_days: number
    hottest_day: { date: string; tmax: number } | null
  }
  change: {
    kind: string
    early_label?: string
    late_label?: string
    early_mean?: number
    late_mean?: number
    percent?: number | null
  } | null
  insight: {
    headline: string
    detail: string
    significant: boolean
    direction: "increase" | "decrease" | "flat" | "mixed" | "none"
  }
  trends: {
    heatwave_days: TrendBlock | null
    events: TrendBlock | null
    annual_max: TrendBlock | null
    rolling_window_years: number
  }
  annual: AnnualRow[]
  events: HeatEvent[]
  assumptions: string[]
}
