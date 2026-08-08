import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BudgetPanel } from './BudgetPanel'
import type { BudgetEvaluation, HotelOption, Itinerary, TravelPreferences } from '@/types/api'

function prefs(): TravelPreferences {
  return {
    origin: null,
    destination: 'Paris',
    start_date: '2026-09-01',
    end_date: '2026-09-03',
    duration_days: 3,
    travelers: 1,
    budget_total: 1500,
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

function hotel(): HotelOption {
  return {
    name: 'Hotel Paris',
    address: '1 Rue de Rivoli',
    lat: 48.85,
    lng: 2.35,
    rating: 8,
    price_per_night: 100,
    currency: 'USD',
    amenities: [],
    booking_link: null,
    is_mock_data: false,
  }
}

function itinerary(): Itinerary {
  return {
    preferences: prefs(),
    days: [{ day_number: 1, date: '2026-09-01', items: [], weather: null, warnings: [] }],
    flights: [],
    hotel: hotel(),
    budget_summary: null,
  }
}

function evaluation(): BudgetEvaluation {
  return {
    allocation: { flights: 0, hotel: 500, food: 500, activities: 500 },
    categories: [
      { category: 'hotel', allocated: 500, actual: 240, difference: -260, status: 'under' },
      { category: 'activities', allocated: 500, actual: 600, difference: 100, status: 'over' },
    ],
    total_allocated: 1500,
    total_actual: 840,
    adherence_score: 0.72,
    suggestions: ['Consider a nicer hotel'],
  }
}

describe('BudgetPanel', () => {
  it('shows the estimated total when no evaluation is given', () => {
    render(<BudgetPanel itinerary={itinerary()} evaluation={null} />)
    expect(screen.getByText(/Estimated total cost/)).toBeInTheDocument()
  })

  it('renders category rows and adherence when an evaluation is given', () => {
    render(<BudgetPanel itinerary={itinerary()} evaluation={evaluation()} />)
    expect(screen.getByText('hotel')).toBeInTheDocument()
    expect(screen.getByText('activities')).toBeInTheDocument()
    expect(screen.getByText(/ADHERENCE 72%/)).toBeInTheDocument()
  })

  it('renders suggestions when present', () => {
    render(<BudgetPanel itinerary={itinerary()} evaluation={evaluation()} />)
    expect(screen.getByText(/Consider a nicer hotel/)).toBeInTheDocument()
  })
})
