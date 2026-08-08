import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { DayCard } from './DayCard'
import type { DayPlan, ItineraryItem } from '@/types/api'

function item(overrides: Partial<ItineraryItem>): ItineraryItem {
  return {
    time_slot: 'morning',
    start_time: '2026-09-02T09:00:00',
    end_time: '2026-09-02T11:00:00',
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
    ...overrides,
  }
}

function emptyDay(): DayPlan {
  return { day_number: 1, date: '2026-09-01', items: [], weather: null, warnings: [] }
}

describe('DayCard', () => {
  it('shows a free-day message for an empty day when expanded', () => {
    render(<DayCard day={emptyDay()} defaultExpanded />)
    expect(screen.getByText(/Free day/)).toBeInTheDocument()
  })

  it('is collapsed by default unless defaultExpanded is set', () => {
    const day: DayPlan = { ...emptyDay(), items: [item({})] }
    render(<DayCard day={day} />)
    expect(screen.queryByText('Louvre Museum')).not.toBeInTheDocument()
  })

  it('expands on click to reveal items', async () => {
    const day: DayPlan = { ...emptyDay(), items: [item({})] }
    const user = userEvent.setup()
    render(<DayCard day={day} />)
    await user.click(screen.getByRole('button', { name: /Day 1/ }))
    expect(screen.getByText('Louvre Museum')).toBeInTheDocument()
  })

  it('shows a walk connector between two consecutive stops with coordinates', () => {
    const day: DayPlan = {
      ...emptyDay(),
      items: [
        item({ title: 'A', lat: 48.86, lng: 2.33 }),
        item({ title: 'B', lat: 48.858, lng: 2.294, start_time: '2026-09-02T12:00:00' }),
      ],
    }
    render(<DayCard day={day} defaultExpanded />)
    expect(screen.getByText(/min walk/)).toBeInTheDocument()
  })

  it('shows the day cost total in the header', () => {
    const day: DayPlan = { ...emptyDay(), items: [item({ cost: 25 }), item({ cost: 15 })] }
    render(<DayCard day={day} />)
    expect(screen.getByText(/\$40/)).toBeInTheDocument()
  })

  it('renders warnings when present', () => {
    const day: DayPlan = { ...emptyDay(), warnings: ['Pack rain gear'] }
    render(<DayCard day={day} defaultExpanded />)
    expect(screen.getByText('Pack rain gear')).toBeInTheDocument()
  })

  it('shows a photo thumbnail for an attraction with a photo_url', () => {
    const day: DayPlan = {
      ...emptyDay(),
      items: [item({ photo_url: 'https://images.unsplash.com/eiffel' })],
    }
    render(<DayCard day={day} defaultExpanded />)
    expect(screen.getByRole('img', { name: 'Louvre Museum' })).toHaveAttribute(
      'src',
      'https://images.unsplash.com/eiffel',
    )
  })

  it('shows a description under the title when present', () => {
    const day: DayPlan = {
      ...emptyDay(),
      items: [item({ description: 'A world-famous art museum in Paris.' })],
    }
    render(<DayCard day={day} defaultExpanded />)
    expect(screen.getByText('A world-famous art museum in Paris.')).toBeInTheDocument()
  })

  it('renders no thumbnail or description when neither is present', () => {
    const day: DayPlan = { ...emptyDay(), items: [item({})] }
    render(<DayCard day={day} defaultExpanded />)
    expect(screen.queryByRole('img')).not.toBeInTheDocument()
  })
})
