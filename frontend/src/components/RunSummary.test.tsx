import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RunSummary } from './RunSummary'
import type { Itinerary, SessionStateResponse, TravelPreferences } from '@/types/api'

function prefs(overrides: Partial<TravelPreferences> = {}): TravelPreferences {
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
    ...overrides,
  }
}

function itinerary(overrides: Partial<Itinerary> = {}): Itinerary {
  return {
    preferences: prefs(),
    days: [
      { day_number: 1, date: '2026-09-01', items: [], weather: null, warnings: [] },
      { day_number: 2, date: '2026-09-02', items: [], weather: null, warnings: [] },
    ],
    flights: [],
    hotel: null,
    budget_summary: null,
    ...overrides,
  }
}

function state(overrides: Partial<SessionStateResponse> = {}): SessionStateResponse {
  return {
    session_id: 's1',
    status: 'completed',
    completed_steps: [],
    errors: [],
    preferences: prefs(),
    itinerary: itinerary(),
    conflict_log: [],
    unresolved_conflicts: [],
    budget_evaluation: null,
    pdf_path: null,
    map_html_available: false,
    ...overrides,
  }
}

describe('RunSummary', () => {
  it('renders nothing without an itinerary', () => {
    const { container } = render(<RunSummary state={state({ itinerary: null })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a day-count badge', () => {
    render(<RunSummary state={state()} />)
    expect(screen.getByText('2 DAYS')).toBeInTheDocument()
  })

  it('shows a budget adherence badge when evaluation is present', () => {
    render(
      <RunSummary
        state={state({
          budget_evaluation: {
            allocation: { flights: 0, hotel: 0, food: 0, activities: 0 },
            categories: [],
            total_allocated: 100,
            total_actual: 80,
            adherence_score: 0.8,
            suggestions: [],
          },
        })}
      />,
    )
    expect(screen.getByText('BUDGET 80%')).toBeInTheDocument()
  })

  it('shows resolved-conflict count when conflict_log is non-empty', () => {
    render(
      <RunSummary
        state={state({
          conflict_log: [
            { day_number: 1, conflict_type: 'overlap', action: 'shifted time', resolved: true },
            { day_number: 2, conflict_type: 'budget_overrun', action: 'trimmed item', resolved: false },
          ],
        })}
      />,
    )
    expect(screen.getByText('1/2 CONFLICTS RESOLVED')).toBeInTheDocument()
  })

  it('shows must-see coverage when preferences specify must_see terms', () => {
    render(
      <RunSummary
        state={state({
          itinerary: itinerary({
            preferences: prefs({ must_see: ['Louvre'] }),
            days: [
              {
                day_number: 1,
                date: '2026-09-01',
                items: [
                  {
                    time_slot: 'morning',
                    start_time: '2026-09-01T09:00:00',
                    end_time: '2026-09-01T11:00:00',
                    activity_type: 'attraction',
                    title: 'Louvre Museum',
                    category: null,
                    location: null,
                    lat: null,
                    lng: null,
                    cost: null,
                    notes: null,
                    photo_url: null,
                    description: null,
                  },
                ],
                weather: null,
                warnings: [],
              },
            ],
          }),
        })}
      />,
    )
    expect(screen.getByText('1/1 MUST-SEE')).toBeInTheDocument()
  })

  it('shows an unresolved-conflicts warning badge', () => {
    render(
      <RunSummary
        state={state({
          unresolved_conflicts: [
            { day_number: 0, conflict_type: 'budget_overrun', description: 'x', auto_resolvable: false },
          ],
        })}
      />,
    )
    expect(screen.getByText('1 UNRESOLVED')).toBeInTheDocument()
  })
})
