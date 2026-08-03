import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ItineraryCard } from './ItineraryCard'
import type { BudgetEvaluation, HotelOption, Itinerary } from '@/types/api'

// react-leaflet's MapContainer needs real layout measurements that jsdom
// doesn't provide; MapPreview itself is covered by the live browser test
// (see scripts/frontend note in README), so it's stubbed out here to keep
// this test focused on ItineraryCard's own day/budget rendering logic.
vi.mock('@/components/MapPreview', () => ({
  MapPreview: () => <div data-testid="map-stub" />,
}))

function hotel(): HotelOption {
  return {
    name: 'Hotel Paris',
    address: '1 Rue de Rivoli',
    lat: 48.85,
    lng: 2.35,
    rating: 8.5,
    price_per_night: 120,
    currency: 'USD',
    amenities: [],
    booking_link: null,
    is_mock_data: false,
  }
}

function itinerary(): Itinerary {
  return {
    preferences: {
      origin: 'Boston',
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
      raw_text: 'trip',
    },
    days: [
      {
        day_number: 1,
        date: '2026-09-01',
        items: [],
        weather: null,
        warnings: [],
      },
      {
        day_number: 2,
        date: '2026-09-02',
        items: [
          {
            time_slot: 'morning',
            start_time: '2026-09-02T09:00:00',
            end_time: '2026-09-02T11:00:00',
            activity_type: 'attraction',
            title: 'Louvre Museum',
            category: 'Museum',
            location: null,
            lat: 48.86,
            lng: 2.33,
            cost: 20,
            notes: null,
          },
        ],
        weather: null,
        warnings: ['Pack rain gear'],
      },
    ],
    flights: [],
    hotel: hotel(),
    budget_summary: null,
  }
}

function budgetEvaluation(): BudgetEvaluation {
  return {
    allocation: { flights: 0, hotel: 500, food: 500, activities: 500 },
    categories: [
      { category: 'hotel', allocated: 500, actual: 240, difference: -260, status: 'under' },
      { category: 'activities', allocated: 500, actual: 600, difference: 100, status: 'over' },
    ],
    total_allocated: 1500,
    total_actual: 840,
    adherence_score: 0.72,
    suggestions: [],
  }
}

describe('ItineraryCard', () => {
  it('shows the destination and day count', () => {
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.getByText('Paris')).toBeInTheDocument()
    expect(screen.getByText('Paris').parentElement?.textContent).toContain('2 days')
  })

  it('shows a free-day message for an empty day', () => {
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.getByText(/Free day/)).toBeInTheDocument()
  })

  it('day 2 starts expanded and shows its item', () => {
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.getByText('Louvre Museum')).toBeInTheDocument()
    expect(screen.getByText('Pack rain gear')).toBeInTheDocument()
  })

  it('collapsing a day hides its items', async () => {
    const user = userEvent.setup()
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: /Day 2/ }))
    expect(screen.queryByText('Louvre Museum')).not.toBeInTheDocument()
  })

  it('PDF button is disabled when not available and calls onDownloadPdf when it is', async () => {
    const onDownloadPdf = vi.fn()
    const user = userEvent.setup()
    const { rerender } = render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={onDownloadPdf}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: 'Download PDF' })).toBeDisabled()

    rerender(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={true}
        mapAvailable={false}
        onDownloadPdf={onDownloadPdf}
        onOpenMap={vi.fn()}
      />,
    )
    await user.click(screen.getByRole('button', { name: 'Download PDF' }))
    expect(onDownloadPdf).toHaveBeenCalled()
  })

  it('renders the budget table when an evaluation is provided', () => {
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={budgetEvaluation()}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.getByText('Budget')).toBeInTheDocument()
    expect(screen.getByText(/Budget adherence/).textContent).toContain('72%')
    expect(screen.getByText('over')).toBeInTheDocument()
  })

  it('omits the budget table when no evaluation is provided', () => {
    render(
      <ItineraryCard
        itinerary={itinerary()}
        budgetEvaluation={null}
        pdfAvailable={false}
        mapAvailable={false}
        onDownloadPdf={vi.fn()}
        onOpenMap={vi.fn()}
      />,
    )
    expect(screen.queryByText('Budget')).not.toBeInTheDocument()
  })
})
