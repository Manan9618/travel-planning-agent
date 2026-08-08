import type { Itinerary } from '@/types/api'
import { WeatherBanner } from '@/components/WeatherBanner'
import { DayCard } from '@/components/DayCard'

interface Props {
  itinerary: Itinerary
}

export function ItineraryPanel({ itinerary }: Props) {
  return (
    <div>
      <WeatherBanner itinerary={itinerary} />
      <div>
        {itinerary.days.map((day) => (
          <DayCard key={day.day_number} day={day} defaultExpanded={day.day_number <= 2} />
        ))}
      </div>
    </div>
  )
}
