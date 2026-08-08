import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Tabs } from './Tabs'

const TABS = [
  { id: 'a', label: 'Itinerary' },
  { id: 'b', label: 'Map' },
  { id: 'c', label: 'PDF preview', disabled: true },
]

describe('Tabs', () => {
  it('renders every tab label', () => {
    render(
      <Tabs tabs={TABS} active="a" onChange={vi.fn()}>
        content
      </Tabs>,
    )
    expect(screen.getByRole('tab', { name: 'Itinerary' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'Map' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: 'PDF preview' })).toBeInTheDocument()
  })

  it('marks the active tab as selected', () => {
    render(
      <Tabs tabs={TABS} active="b" onChange={vi.fn()}>
        content
      </Tabs>,
    )
    expect(screen.getByRole('tab', { name: 'Map' })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Itinerary' })).toHaveAttribute('aria-selected', 'false')
  })

  it('calls onChange when a tab is clicked', async () => {
    const onChange = vi.fn()
    const user = userEvent.setup()
    render(
      <Tabs tabs={TABS} active="a" onChange={onChange}>
        content
      </Tabs>,
    )
    await user.click(screen.getByRole('tab', { name: 'Map' }))
    expect(onChange).toHaveBeenCalledWith('b')
  })

  it('disables tabs marked disabled', () => {
    render(
      <Tabs tabs={TABS} active="a" onChange={vi.fn()}>
        content
      </Tabs>,
    )
    expect(screen.getByRole('tab', { name: 'PDF preview' })).toBeDisabled()
  })

  it('renders the children content', () => {
    render(
      <Tabs tabs={TABS} active="a" onChange={vi.fn()}>
        <p>panel content</p>
      </Tabs>,
    )
    expect(screen.getByText('panel content')).toBeInTheDocument()
  })
})
