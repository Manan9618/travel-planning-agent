import { CircleMarker, MapContainer, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import { useEffect } from 'react'
import type { LatLngBoundsExpression, LatLngTuple } from 'leaflet'
import type { HotelOption, Itinerary } from '@/types/api'
import { dayColor } from '@/lib/dayColors'

interface Props {
  itinerary: Itinerary
  className?: string
}

interface Stop {
  dayNumber: number
  lat: number
  lng: number
  title: string
  time: string
  activityType: string
}

function collectStops(itinerary: Itinerary): Stop[] {
  const stops: Stop[] = []
  for (const day of itinerary.days) {
    for (const item of day.items) {
      if (item.lat == null || item.lng == null) continue
      stops.push({
        dayNumber: day.day_number,
        lat: item.lat,
        lng: item.lng,
        title: item.title,
        time: item.start_time.slice(11, 16),
        activityType: item.activity_type,
      })
    }
  }
  return stops
}

function FitBounds({ points }: { points: LatLngTuple[] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 0) return
    if (points.length === 1) {
      map.setView(points[0], 14)
      return
    }
    const bounds = points as LatLngBoundsExpression
    map.fitBounds(bounds, { padding: [32, 32] })
  }, [map, points])
  return null
}

/** Real-time Leaflet map preview: a marker per scheduled stop (color-coded
 * by day, same palette as Weeks 13/14's Folium map / PDF badges), a route
 * polyline per day, and the hotel as a distinct dark marker — driven
 * directly by the itinerary's own lat/lng data rather than embedding the
 * separately-exported Folium HTML, so it stays reactively in sync with
 * whatever itinerary is currently shown in the chat.
 */
export function MapPreview({ itinerary, className }: Props) {
  const stops = collectStops(itinerary)
  const hotel: HotelOption | null = itinerary.hotel

  const allPoints: LatLngTuple[] = [
    ...(hotel ? [[hotel.lat, hotel.lng] as LatLngTuple] : []),
    ...stops.map((s): LatLngTuple => [s.lat, s.lng]),
  ]

  if (allPoints.length === 0) {
    return (
      <div
        className={
          className ??
          'flex h-64 items-center justify-center border border-line bg-paper text-sm text-ink-muted dark:border-line-dark dark:bg-paper-dark dark:text-ink-muted-dark'
        }
      >
        No mappable stops yet
      </div>
    )
  }

  const stopsByDay = new Map<number, Stop[]>()
  for (const stop of stops) {
    const list = stopsByDay.get(stop.dayNumber) ?? []
    list.push(stop)
    stopsByDay.set(stop.dayNumber, list)
  }

  return (
    <div className={className ?? 'h-64 w-full overflow-hidden sm:h-80'} data-testid="map-preview">
      <MapContainer center={allPoints[0]} zoom={13} className="h-full w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds points={allPoints} />

        {hotel && (
          <CircleMarker
            center={[hotel.lat, hotel.lng]}
            radius={9}
            pathOptions={{ color: '#111827', fillColor: '#111827', fillOpacity: 1 }}
          >
            <Popup>
              <b>{hotel.name}</b>
              <br />
              {hotel.address}
            </Popup>
          </CircleMarker>
        )}

        {[...stopsByDay.entries()].map(([dayNumber, dayStops]) => (
          <Polyline
            key={`route-${dayNumber}`}
            positions={dayStops.map((s): LatLngTuple => [s.lat, s.lng])}
            pathOptions={{ color: dayColor(dayNumber), weight: 3, opacity: 0.7 }}
          />
        ))}

        {stops.map((stop, i) => (
          <CircleMarker
            key={i}
            center={[stop.lat, stop.lng]}
            radius={7}
            pathOptions={{
              color: dayColor(stop.dayNumber),
              fillColor: dayColor(stop.dayNumber),
              fillOpacity: 0.85,
            }}
          >
            <Popup>
              <b>Day {stop.dayNumber}</b>: {stop.title}
              <br />
              {stop.time} &middot; {stop.activityType}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>
    </div>
  )
}
