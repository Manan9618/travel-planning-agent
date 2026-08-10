import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Header } from './Header'
import type { Itinerary, TravelPreferences } from '@/types/api'

const { createShareLink } = vi.hoisted(() => ({ createShareLink: vi.fn() }))
vi.mock('@/lib/api', () => ({ createShareLink }))

function prefs(overrides: Partial<TravelPreferences> = {}): TravelPreferences {
  return {
    origin: null,
    destination: 'Paris',
    additional_destinations: [],
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
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.getByText('AI Travel Planning Agent')).toBeInTheDocument()
  })

  it('shows the destination and day count once an itinerary exists', () => {
    render(
      <Header
        itinerary={itinerary()}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.getByText(/Paris/)).toBeInTheDocument()
    expect(screen.getByText(/2 days/)).toBeInTheDocument()
  })

  it('shows a joined label for a multi-destination trip', () => {
    render(
      <Header
        itinerary={itinerary({ preferences: prefs({ additional_destinations: ['Rome'] }) })}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.getByText(/Paris & Rome/)).toBeInTheDocument()
  })

  it('does not show "New trip" before any turns exist', () => {
    render(
      <Header
        itinerary={null}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
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
        sessionId={null}
        onNewTrip={onNewTrip}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    await user.click(screen.getByText('New trip'))
    expect(onNewTrip).toHaveBeenCalled()
  })

  it('Export PDF is disabled until the PDF is available', () => {
    render(
      <Header
        itinerary={itinerary()}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
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
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={onDownloadPdf}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={true}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Export PDF' }))
    expect(onDownloadPdf).toHaveBeenCalled()
  })

  it('calls onDownloadCalendar when Add to Calendar is clicked', async () => {
    const onDownloadCalendar = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={itinerary()}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={onDownloadCalendar}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Add to Calendar' }))
    expect(onDownloadCalendar).toHaveBeenCalled()
  })

  it('does not show Add to Calendar before any itinerary exists', () => {
    render(
      <Header
        itinerary={null}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Add to Calendar' })).not.toBeInTheDocument()
  })

  it('shows a budget bar when a budget is stated', () => {
    render(
      <Header
        itinerary={itinerary({ preferences: prefs({ budget_total: 1000 }) })}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.getByText(/\/\$1,000/)).toBeInTheDocument()
  })

  it('uses budgetEvaluation totals, formatted in the stated currency, when available', () => {
    render(
      <Header
        itinerary={itinerary({ preferences: prefs({ budget_total: 1000, budget_currency: 'EUR' }) })}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={{
          allocation: { flights: 0, hotel: 400, food: 300, activities: 300 },
          categories: [],
          total_allocated: 1000,
          total_actual: 840,
          adherence_score: 0.84,
          suggestions: [],
        }}
      />,
    )
    expect(screen.getByText(/\/€1,000/)).toBeInTheDocument()
    expect(screen.getByText('€840')).toBeInTheDocument()
  })

  it('calls onLogout when Log out is clicked', async () => {
    const onLogout = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={null}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={onLogout}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    await user.click(screen.getByText('Log out'))
    expect(onLogout).toHaveBeenCalled()
  })

  it('calls onMyTrips when My Trips is clicked', async () => {
    const onMyTrips = vi.fn()
    const user = userEvent.setup()
    render(
      <Header
        itinerary={null}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={onMyTrips}
        budgetEvaluation={null}
      />,
    )
    await user.click(screen.getByText('My Trips'))
    expect(onMyTrips).toHaveBeenCalled()
  })

  it('does not show Share before any itinerary exists', () => {
    render(
      <Header
        itinerary={null}
        sessionId={null}
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={false}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )
    expect(screen.queryByRole('button', { name: 'Share' })).not.toBeInTheDocument()
  })

  it('creates a share link, copies it, and shows a confirmation', async () => {
    createShareLink.mockResolvedValueOnce({ share_url: 'http://localhost:5173/?shared=tok-abc' })
    const user = userEvent.setup()
    const writeText = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue(undefined)
    render(
      <Header
        itinerary={itinerary()}
        sessionId="session-1"
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Share' }))

    expect(createShareLink).toHaveBeenCalledWith('session-1')
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('http://localhost:5173/?shared=tok-abc'),
    )
    expect(await screen.findByRole('button', { name: 'Link copied!' })).toBeInTheDocument()
  })

  it('shows an error label when creating a share link fails', async () => {
    createShareLink.mockRejectedValueOnce(new Error('400 Bad Request'))
    const user = userEvent.setup()
    render(
      <Header
        itinerary={itinerary()}
        sessionId="session-1"
        onNewTrip={vi.fn()}
        onDownloadPdf={vi.fn()}
        onDownloadCalendar={vi.fn()}
        pdfAvailable={false}
        hasTurns={true}
        userEmail="traveler@example.com"
        onLogout={vi.fn()}
        onMyTrips={vi.fn()}
        budgetEvaluation={null}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Share' }))
    expect(await screen.findByRole('button', { name: 'Could not share' })).toBeInTheDocument()
  })
})
