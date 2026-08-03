import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { HumanReviewPrompt } from './HumanReviewPrompt'
import type { Conflict } from '@/types/api'

const CONFLICTS: Conflict[] = [
  {
    day_number: 0,
    conflict_type: 'budget_overrun',
    description: 'Estimated total exceeds budget by $500',
    auto_resolvable: false,
  },
]

describe('HumanReviewPrompt', () => {
  it('renders each conflict description', () => {
    render(<HumanReviewPrompt conflicts={CONFLICTS} onDecide={vi.fn()} deciding={false} />)
    expect(screen.getByText('Estimated total exceeds budget by $500')).toBeInTheDocument()
  })

  it('calls onDecide(true) when approving', async () => {
    const onDecide = vi.fn()
    const user = userEvent.setup()
    render(<HumanReviewPrompt conflicts={CONFLICTS} onDecide={onDecide} deciding={false} />)

    await user.click(screen.getByRole('button', { name: 'Approve anyway' }))

    expect(onDecide).toHaveBeenCalledWith(true)
  })

  it('calls onDecide(false) when rejecting', async () => {
    const onDecide = vi.fn()
    const user = userEvent.setup()
    render(<HumanReviewPrompt conflicts={CONFLICTS} onDecide={onDecide} deciding={false} />)

    await user.click(screen.getByRole('button', { name: 'Reject' }))

    expect(onDecide).toHaveBeenCalledWith(false)
  })

  it('disables both buttons while deciding', () => {
    render(<HumanReviewPrompt conflicts={CONFLICTS} onDecide={vi.fn()} deciding={true} />)
    expect(screen.getByRole('button', { name: 'Approve anyway' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Reject' })).toBeDisabled()
  })
})
