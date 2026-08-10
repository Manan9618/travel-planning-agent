import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LandingPage } from './LandingPage'

describe('LandingPage', () => {
  it('shows the hero headline and feature highlights', () => {
    render(<LandingPage onSignIn={vi.fn()} onGetStarted={vi.fn()} />)
    expect(screen.getByText(/Waypoint plans it/)).toBeInTheDocument()
    expect(screen.getByText('Parallel search')).toBeInTheDocument()
    expect(screen.getByText('Budget-aware')).toBeInTheDocument()
    expect(screen.getByText('Refine in plain English')).toBeInTheDocument()
    expect(screen.getByText('Take it with you')).toBeInTheDocument()
  })

  it('calls onSignIn when the header Sign in button is clicked', async () => {
    const onSignIn = vi.fn()
    const user = userEvent.setup()
    render(<LandingPage onSignIn={onSignIn} onGetStarted={vi.fn()} />)
    await user.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(onSignIn).toHaveBeenCalled()
  })

  it('calls onGetStarted when the hero CTA is clicked', async () => {
    const onGetStarted = vi.fn()
    const user = userEvent.setup()
    render(<LandingPage onSignIn={vi.fn()} onGetStarted={onGetStarted} />)
    await user.click(screen.getByRole('button', { name: /Plan your first trip/ }))
    expect(onGetStarted).toHaveBeenCalled()
  })
})
