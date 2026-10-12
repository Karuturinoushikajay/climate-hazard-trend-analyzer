import { useEffect, useRef } from "react"
import * as L from "leaflet"
import "leaflet/dist/leaflet.css"
import type { BBox } from "@/types"

type Point = { latitude: number; longitude: number }

const EMPTY: Point[] = []

export function MapPanel({
  latitude,
  longitude,
  bbox,
  samplePoints = EMPTY,
  selectionMode,
  onPoint,
  onBox,
}: {
  latitude: number
  longitude: number
  bbox: BBox | null
  samplePoints?: Point[]
  selectionMode: "point" | "box"
  onPoint: (latitude: number, longitude: number) => void
  onBox: (box: BBox) => void
}) {
  const containerRef = useRef<HTMLDivElement | null>(null)
  const mapRef = useRef<L.Map | null>(null)
  const layerRef = useRef<L.LayerGroup | null>(null)
  const modeRef = useRef(selectionMode)
  const cornerRef = useRef<L.LatLng | null>(null)
  const onPointRef = useRef(onPoint)
  const onBoxRef = useRef(onBox)

  useEffect(() => {
    modeRef.current = selectionMode
    onPointRef.current = onPoint
    onBoxRef.current = onBox
  }, [onBox, onPoint, selectionMode])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    const startLat = Number(element.dataset.lat)
    const startLon = Number(element.dataset.lon)
    const map = L.map(element, { scrollWheelZoom: false }).setView(
      [Number.isFinite(startLat) ? startLat : 20, Number.isFinite(startLon) ? startLon : 0],
      5,
    )
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      attribution: "&copy; OpenStreetMap &copy; CARTO",
      subdomains: "abcd",
      maxZoom: 12,
    }).addTo(map)
    const layers = L.layerGroup().addTo(map)
    layerRef.current = layers
    map.on("click", (event: L.LeafletMouseEvent) => {
      const spot = event.latlng
      if (modeRef.current === "box") {
        if (!cornerRef.current) {
          cornerRef.current = spot
          return
        }
        const first = cornerRef.current
        cornerRef.current = null
        onBoxRef.current({
          west: Math.min(first.lng, spot.lng),
          east: Math.max(first.lng, spot.lng),
          south: Math.min(first.lat, spot.lat),
          north: Math.max(first.lat, spot.lat),
        })
        return
      }
      cornerRef.current = null
      onPointRef.current(spot.lat, spot.lng)
    })
    mapRef.current = map
    const timer = window.setTimeout(() => map.invalidateSize(), 180)
    return () => {
      window.clearTimeout(timer)
      map.remove()
      mapRef.current = null
      layerRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    const layers = layerRef.current
    if (!map || !layers) return
    layers.clearLayers()
    if (bbox) {
      const bounds = L.latLngBounds([bbox.south, bbox.west], [bbox.north, bbox.east])
      L.rectangle(bounds, {
        color: "#1d4a46",
        weight: 2,
        fillColor: "#1d4a46",
        fillOpacity: 0.12,
      }).addTo(layers)
      map.fitBounds(bounds.pad(0.25), { animate: false })
    } else if (Number.isFinite(latitude) && Number.isFinite(longitude)) {
      L.circleMarker([latitude, longitude], {
        radius: 7,
        color: "#8c3416",
        fillColor: "#c4491d",
        fillOpacity: 0.95,
        weight: 2,
      }).addTo(layers)
      map.setView([latitude, longitude], 6, { animate: false })
    }
    for (const point of samplePoints) {
      L.circleMarker([point.latitude, point.longitude], {
        radius: 4,
        color: "#1d4a46",
        fillColor: "#fbf8f3",
        fillOpacity: 1,
        weight: 2,
      }).addTo(layers)
    }
  }, [bbox, latitude, longitude, samplePoints])

  return (
    <div className="relative z-0 h-56 overflow-hidden rounded-2xl border border-line sm:h-64">
      <div ref={containerRef} data-lat={latitude} data-lon={longitude} className="h-full w-full" />
    </div>
  )
}
