import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatInput } from './ChatInput'

describe('ChatInput', () => {
  it('sends the trimmed text on Enter', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} disabled={false} placeholder="Type..." />)

    await user.type(screen.getByPlaceholderText('Type...'), '  5 days in Paris  {Enter}')

    expect(onSend).toHaveBeenCalledWith('5 days in Paris')
  })

  it('does not send on Shift+Enter, inserts a newline instead', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} disabled={false} placeholder="Type..." />)

    const textarea = screen.getByPlaceholderText('Type...')
    await user.type(textarea, 'line one{Shift>}{Enter}{/Shift}line two')

    expect(onSend).not.toHaveBeenCalled()
    expect(textarea).toHaveValue('line one\nline two')
  })

  it('clears the input after sending', async () => {
    const user = userEvent.setup()
    render(<ChatInput onSend={vi.fn()} disabled={false} placeholder="Type..." />)
    const textarea = screen.getByPlaceholderText('Type...')

    await user.type(textarea, 'hello{Enter}')

    expect(textarea).toHaveValue('')
  })

  it('does not send an empty or whitespace-only message', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} disabled={false} placeholder="Type..." />)

    await user.type(screen.getByPlaceholderText('Type...'), '   {Enter}')

    expect(onSend).not.toHaveBeenCalled()
  })

  it('the send button is disabled while disabled prop is true', () => {
    render(<ChatInput onSend={vi.fn()} disabled placeholder="Type..." />)
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
    expect(screen.getByPlaceholderText('Type...')).toBeDisabled()
  })

  it('the send button is disabled when the input is empty', () => {
    render(<ChatInput onSend={vi.fn()} disabled={false} placeholder="Type..." />)
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()
  })

  it('clicking Send with text calls onSend', async () => {
    const onSend = vi.fn()
    const user = userEvent.setup()
    render(<ChatInput onSend={onSend} disabled={false} placeholder="Type..." />)

    await user.type(screen.getByPlaceholderText('Type...'), 'Tokyo trip')
    await user.click(screen.getByRole('button', { name: 'Send' }))

    expect(onSend).toHaveBeenCalledWith('Tokyo trip')
  })
})
