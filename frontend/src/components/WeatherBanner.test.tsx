import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { WeatherBanner } from './WeatherBanner'
import type { DayPlan, Itinerary, TravelPreferences } from '@/types/api'

function prefs(): TravelPreferences {
  return {
    origin: null,
    destination: 'Paris',
    start_date: '2026-09-01',
    end_date: '2026-09-03',
    duration_days: 3,
    travelers: 1,
    budget_total: null,
    budget_currency: 'USD',
    budget_tier: null,
    trip_style: null,
    pace: 'moderate',
    interests: [],
    must_see: [],
    dietary_restrictions: [],
    accessibility_needs: [],
    priority_weights: {},
    raw_text: 't',
  }
}

function day(overrides: Partial<DayPlan>): DayPlan {
  return {
    day_number: 1,
    date: '2026-09-01',
    items: [],
    weather: null,
    warnings: [],
    ...overrides,
  }
}

function itinerary(days: DayPlan[]): Itinerary {
  return { preferences: prefs(), days, flights: [], hotel: null, budget_summary: null }
}

describe('WeatherBanner', () => {
  it('renders nothing when no day has a warning', () => {
    const { container } = render(<WeatherBanner itinerary={itinerary([day({})])} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('surfaces the first day with a warning', () => {
    const flaggedDay = day({
      day_number: 2,
      date: '2026-09-02',
      warnings: ['Pack rain gear — 90% chance of rain'],
      weather: {
        day: '2026-09-02',
        condition: 'Rain',
        temp_high_c: 18,
        temp_low_c: 12,
        rain_probability: 0.9,
        wind_speed_kph: 10,
        comfort_score: 3,
      },
    })
    render(<WeatherBanner itinerary={itinerary([day({}), flaggedDay])} />)
    expect(screen.getByText(/Day 2/)).toBeInTheDocument()
    expect(screen.getByText(/Pack rain gear/)).toBeInTheDocument()
  })
})
