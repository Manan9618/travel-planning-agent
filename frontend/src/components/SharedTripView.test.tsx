import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { SharedTripView } from './SharedTripView'
import type { Itinerary, TravelPreferences } from '@/types/api'

const { getSharedTrip, fetchSharedPdfBlobUrl } = vi.hoisted(() => ({
  getSharedTrip: vi.fn(),
  fetchSharedPdfBlobUrl: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ getSharedTrip, fetchSharedPdfBlobUrl }))

// MapPreview (Leaflet) has no jsdom-friendly test setup anywhere in this
// project (see MapPreview.tsx's own lack of a test file) — stubbed here so
// this test can focus on SharedTripView's own loading/error/tab-switch
// logic without dragging in Leaflet's DOM requirements.
vi.mock('@/components/MapPreview', () => ({ MapPreview: () => <div>map preview</div> }))

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
    days: [{ day_number: 1, date: '2026-09-01', items: [], weather: null, warnings: [] }],
    flights: [],
    hotel: null,
    budget_summary: null,
    ...overrides,
  }
}

describe('SharedTripView', () => {
  it('shows a loading state before the trip resolves', () => {
    getSharedTrip.mockReturnValueOnce(new Promise(() => {}))
    render(<SharedTripView token="tok" onPlanYourOwn={vi.fn()} />)
    expect(screen.getByText(/Loading shared trip/)).toBeInTheDocument()
  })

  it('shows the destination once loaded', async () => {
    getSharedTrip.mockResolvedValueOnce({
      itinerary: itinerary(),
      budget_evaluation: null,
      pdf_available: false,
      map_available: false,
    })
    render(<SharedTripView token="tok" onPlanYourOwn={vi.fn()} />)
    expect(await screen.findByText(/Paris — shared trip/)).toBeInTheDocument()
  })

  it('shows an invalid-link message and a CTA when the token is unknown', async () => {
    getSharedTrip.mockRejectedValueOnce(new Error('404 Not Found'))
    const user = userEvent.setup()
    const onPlanYourOwn = vi.fn()
    render(<SharedTripView token="bad-tok" onPlanYourOwn={onPlanYourOwn} />)

    expect(await screen.findByText(/invalid or no longer available/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Plan your own trip' }))
    expect(onPlanYourOwn).toHaveBeenCalled()
  })

  it('calls onPlanYourOwn from the header CTA once loaded', async () => {
    getSharedTrip.mockResolvedValueOnce({
      itinerary: itinerary(),
      budget_evaluation: null,
      pdf_available: false,
      map_available: false,
    })
    const onPlanYourOwn = vi.fn()
    const user = userEvent.setup()
    render(<SharedTripView token="tok" onPlanYourOwn={onPlanYourOwn} />)

    await user.click(await screen.findByRole('button', { name: 'Plan your own trip' }))
    expect(onPlanYourOwn).toHaveBeenCalled()
  })

  it('disables the PDF tab when no PDF is available', async () => {
    getSharedTrip.mockResolvedValueOnce({
      itinerary: itinerary(),
      budget_evaluation: null,
      pdf_available: false,
      map_available: false,
    })
    render(<SharedTripView token="tok" onPlanYourOwn={vi.fn()} />)
    expect(await screen.findByRole('tab', { name: 'PDF preview' })).toBeDisabled()
  })

  it('switches to the budget tab and shows the fallback total without an evaluation', async () => {
    getSharedTrip.mockResolvedValueOnce({
      itinerary: itinerary(),
      budget_evaluation: null,
      pdf_available: false,
      map_available: false,
    })
    const user = userEvent.setup()
    render(<SharedTripView token="tok" onPlanYourOwn={vi.fn()} />)

    await user.click(await screen.findByRole('tab', { name: 'Budget' }))
    expect(screen.getByText(/Estimated total cost/)).toBeInTheDocument()
  })

  it('fetches the shared PDF blob URL when the PDF tab is used', async () => {
    getSharedTrip.mockResolvedValueOnce({
      itinerary: itinerary(),
      budget_evaluation: null,
      pdf_available: true,
      map_available: false,
    })
    fetchSharedPdfBlobUrl.mockResolvedValueOnce('blob:shared-pdf')
    const user = userEvent.setup()
    render(<SharedTripView token="tok-123" onPlanYourOwn={vi.fn()} />)

    await user.click(await screen.findByRole('tab', { name: 'PDF preview' }))
    await waitFor(() => expect(fetchSharedPdfBlobUrl).toHaveBeenCalledWith('tok-123'))
  })
})
