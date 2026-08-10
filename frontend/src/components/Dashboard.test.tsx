import { describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Dashboard } from './Dashboard'

const { listSessions } = vi.hoisted(() => ({ listSessions: vi.fn() }))
vi.mock('@/lib/api', () => ({ listSessions }))

describe('Dashboard', () => {
  it('shows a loading state before sessions resolve', () => {
    listSessions.mockReturnValueOnce(new Promise(() => {}))
    render(<Dashboard onSelect={vi.fn()} onNewTrip={vi.fn()} />)
    expect(screen.getByText(/Loading your trips/)).toBeInTheDocument()
  })

  it('shows an empty state with a CTA when there are no trips', async () => {
    listSessions.mockResolvedValueOnce({ sessions: [] })
    render(<Dashboard onSelect={vi.fn()} onNewTrip={vi.fn()} />)
    expect(await screen.findByText(/No trips yet/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Plan your first trip' })).toBeInTheDocument()
  })

  it('calls onNewTrip from the empty state CTA', async () => {
    listSessions.mockResolvedValueOnce({ sessions: [] })
    const onNewTrip = vi.fn()
    const user = userEvent.setup()
    render(<Dashboard onSelect={vi.fn()} onNewTrip={onNewTrip} />)
    await user.click(await screen.findByRole('button', { name: 'Plan your first trip' }))
    expect(onNewTrip).toHaveBeenCalled()
  })

  it('lists trips with their status and calls onSelect when clicked', async () => {
    listSessions.mockResolvedValueOnce({
      sessions: [
        {
          session_id: 's1',
          raw_text: '5 days in Paris',
          status: 'completed',
          created_at: new Date().toISOString(),
        },
      ],
    })
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<Dashboard onSelect={onSelect} onNewTrip={vi.fn()} />)

    const card = await screen.findByText('5 days in Paris')
    expect(screen.getByText('Completed')).toBeInTheDocument()
    await user.click(card)
    expect(onSelect).toHaveBeenCalledWith(
      expect.objectContaining({ session_id: 's1', raw_text: '5 days in Paris' }),
    )
  })

  it('calls onNewTrip from the header button', async () => {
    listSessions.mockResolvedValueOnce({ sessions: [] })
    const onNewTrip = vi.fn()
    const user = userEvent.setup()
    render(<Dashboard onSelect={vi.fn()} onNewTrip={onNewTrip} />)
    await user.click(screen.getByRole('button', { name: '+ New trip' }))
    expect(onNewTrip).toHaveBeenCalled()
  })

  it('shows an error message when listing sessions fails', async () => {
    listSessions.mockRejectedValueOnce(new Error('500 Internal Server Error'))
    render(<Dashboard onSelect={vi.fn()} onNewTrip={vi.fn()} />)
    await waitFor(() =>
      expect(screen.getByText('500 Internal Server Error')).toBeInTheDocument(),
    )
  })
})
