import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { RefinementChips } from './RefinementChips'

describe('RefinementChips', () => {
  it('calls onSelect with the chip label when clicked', async () => {
    const onSelect = vi.fn()
    const user = userEvent.setup()
    render(<RefinementChips onSelect={onSelect} disabled={false} />)

    await user.click(screen.getByRole('button', { name: 'Less walking' }))

    expect(onSelect).toHaveBeenCalledWith('Less walking')
  })

  it('disables every chip when disabled is true', () => {
    render(<RefinementChips onSelect={vi.fn()} disabled />)
    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
  })
})
