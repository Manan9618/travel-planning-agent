import { useState } from 'react'
import type { DayPlan, ItineraryItem } from '@/types/api'
import { dayColor } from '@/lib/dayColors'
import { estimatedWalkMinutes, haversineKm } from '@/lib/geo'
import { weatherCode } from '@/lib/weatherCode'

interface Props {
  day: DayPlan
  defaultExpanded?: boolean
}

function WalkConnector({ km }: { km: number }) {
  const minutes = estimatedWalkMinutes(km)
  return (
    <div className="flex items-center gap-2 py-1 pl-[3.25rem] font-mono text-[10px] text-ink-faint dark:text-ink-faint-dark">
      <span className="text-line dark:text-line-dark">↓</span>
      <span>
        ~{minutes} min walk · {km.toFixed(1)} km
      </span>
    </div>
  )
}

function ItemRow({ item }: { item: ItineraryItem }) {
  const hasDetail = Boolean(item.photo_url || item.description)
  return (
    <div className="py-1.5">
      <div className="flex items-baseline gap-3 text-sm">
        <span className="w-12 shrink-0 font-mono text-xs tabular-nums text-ink-muted dark:text-ink-muted-dark">
          {item.start_time.slice(11, 16)}
        </span>
        <span className="flex-1 text-ink dark:text-ink-dark">{item.title}</span>
        <span className="shrink-0 font-mono text-[10px] text-ink-faint uppercase dark:text-ink-faint-dark">
          {item.activity_type}
        </span>
        {item.cost != null && (
          <span className="shrink-0 font-mono text-xs tabular-nums text-ink-muted dark:text-ink-muted-dark">
            ${item.cost.toFixed(0)}
          </span>
        )}
      </div>
      {hasDetail && (
        <div className="mt-1.5 flex gap-3 pl-[3.75rem]">
          {item.photo_url && (
            <img
              src={item.photo_url}
              alt={item.title}
              loading="lazy"
              className="h-16 w-24 shrink-0 rounded-md object-cover"
            />
          )}
          {item.description && (
            <p className="text-xs leading-relaxed text-ink-muted dark:text-ink-muted-dark">
              {item.description}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export function DayCard({ day, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const color = dayColor(day.day_number)
  const cost = day.items.reduce((sum, i) => sum + (i.cost ?? 0), 0)
  const mappable = day.items.filter((i): i is ItineraryItem & { lat: number; lng: number } =>
    Boolean(i.lat != null && i.lng != null),
  )

  let totalKm = 0
  for (let i = 0; i < mappable.length - 1; i++) {
    totalKm += haversineKm([mappable[i].lat, mappable[i].lng], [mappable[i + 1].lat, mappable[i + 1].lng])
  }

  return (
    <div
      className="border-l-4 border-b border-line last:border-b-0 dark:border-line-dark"
      style={{ borderLeftColor: color }}
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left hover:bg-paper dark:hover:bg-paper-dark"
        aria-expanded={expanded}
      >
        <span
          className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full font-mono text-[10px] font-semibold text-white"
          style={{ backgroundColor: color }}
        >
          {day.day_number}
        </span>
        <span className="font-medium text-ink dark:text-ink-dark">
          Day {day.day_number}
        </span>
        <span className="hidden font-mono text-[11px] text-ink-faint sm:inline dark:text-ink-faint-dark">
          {new Date(day.date).toLocaleDateString(undefined, { weekday: 'short', month: 'short', day: 'numeric' })}
        </span>
        {day.weather && (
          <span className="hidden font-mono text-[11px] text-ink-muted md:inline dark:text-ink-muted-dark">
            {weatherCode(day.weather.condition)} {Math.round(day.weather.temp_high_c)}°/
            {Math.round(day.weather.temp_low_c)}° · {Math.round(day.weather.rain_probability * 100)}%
          </span>
        )}
        <span className="ml-auto shrink-0 font-mono text-[11px] tabular-nums text-ink-faint dark:text-ink-faint-dark">
          {mappable.length > 0 && `${mappable.length} stops · ${totalKm.toFixed(1)} km · `}
          ${cost.toFixed(0)}
        </span>
        <span className="shrink-0 text-ink-faint dark:text-ink-faint-dark" aria-hidden>
          {expanded ? '−' : '+'}
        </span>
      </button>

      {expanded && (
        <div className="px-3 pb-3">
          {day.items.length === 0 ? (
            <p className="text-sm italic text-ink-muted dark:text-ink-muted-dark">
              Free day &mdash; nothing scheduled
            </p>
          ) : (
            <div>
              {day.items.map((item, i) => {
                const next = day.items[i + 1]
                const showWalk =
                  next && item.lat != null && item.lng != null && next.lat != null && next.lng != null
                return (
                  <div key={i}>
                    <ItemRow item={item} />
                    {showWalk && (
                      <WalkConnector
                        km={haversineKm([item.lat as number, item.lng as number], [next.lat as number, next.lng as number])}
                      />
                    )}
                  </div>
                )
              })}
            </div>
          )}
          {day.warnings.length > 0 && (
            <ul className="mt-2 space-y-0.5">
              {day.warnings.map((w, i) => (
                <li key={i} className="font-mono text-[11px] text-amber-700 dark:text-amber-400">
                  {w}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
