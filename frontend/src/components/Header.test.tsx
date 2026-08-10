import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Header } from './Header'
import type { Itinerary, TravelPreferences } from '@/types/api'

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

describe('Header', () => {
  it('shows a default title before any trip exists', () => {
    render(
      <Header
        itinerary={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    expect(screen.getByText('AI Travel Planning Agent')).toBeInTheDocument()
  })

  it('shows the destination and day count once an itinerary exists', () => {
    render(
      <Header
        itinerary={itinerary()}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    expect(screen.getByText(/Paris/)).toBeInTheDocument()
    expect(screen.getByText(/2 days/)).toBeInTheDocument()
  })

  it('does not show "New trip" before any turns exist', () => {
    render(
      <Header
        itinerary={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    expect(screen.queryByText('New trip')).not.toBeInTheDocument()
  })

  it('calls onNewTrip when clicked', async () => {
    const onNewTrip = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={null}
        onNewTrip={onNewTrip}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    await user.click(screen.getByText('New trip'))
    expect(onNewTrip).toHaveBeenCalled()
  })

  it('Export PDF is disabled until the PDF is available', () => {
    render(
      <Header
        itinerary={itinerary()}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Export PDF' })).toBeDisabled()
  })

  it('calls onDownloadPdf when Export PDF is clicked and available', async () => {
    const onDownloadPdf = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={itinerary()}
        onNewTrip={vi.fn()}
        onDownloadPdf={onDownloadPdf}
        pdfAvailable={true}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Export PDF' }))
    expect(onDownloadPdf).toHaveBeenCalled()
  })

  it('shows a budget bar when a budget is stated', () => {
    render(
      <Header
        itinerary={itinerary({ preferences: prefs({ budget_total: 1000 }) })}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
      />,
    )
    expect(screen.getByText(/\/\$1,000/)).toBeInTheDocument()
  })

  it('calls onLogout when Log out is clicked', async () => {
    const onLogout = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={onLogout}
      />,
    )
    await user.click(screen.getByText('Log out'))
    expect(onLogout).toHaveBeenCalled()
  })
})
