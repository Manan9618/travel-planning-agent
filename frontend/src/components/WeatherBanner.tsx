import type { Itinerary } from '@/types/api'

interface Props {
  itinerary: Itinerary
}

/** Surfaces the first day with a real weather warning (Week 7's
 * weather_matcher — "Pack rain gear", heat/cold/wind alerts), rather than
 * inventing a generic weather summary. Silent when there's nothing to warn
 * about, which is the common case for trips far enough out that the
 * free-tier forecast horizon hasn't kicked in yet. */
export function WeatherBanner({ itinerary }: Props) {
  const flagged = itinerary.days.find((d) => d.warnings.length > 0)
  if (!flagged) return null

  const dateLabel = new Date(flagged.date).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
  })
  const conditionLabel = flagged.weather
    ? `${flagged.weather.condition} · ${Math.round(flagged.weather.temp_high_c)}°/${Math.round(
        flagged.weather.temp_low_c,
      )}°C · ${Math.round(flagged.weather.rain_probability * 100)}% rain`
    : ''

  return (
    <div className="flex items-start gap-2 border-b border-line bg-accent-soft px-3 py-2 text-xs dark:border-line-dark dark:bg-accent-soft-dark">
      <span aria-hidden>⛅</span>
      <div className="min-w-0">
        <span className="font-medium text-ink dark:text-ink-dark">
          Day {flagged.day_number} ({dateLabel})
        </span>
        {conditionLabel && (
          <span className="ml-1 font-mono text-ink-muted dark:text-ink-muted-dark">
            {conditionLabel}
          </span>
        )}
        <span className="ml-1 text-ink-muted dark:text-ink-muted-dark">
          — {flagged.warnings.join('; ')}
        </span>
      </div>
    </div>
  )
}
