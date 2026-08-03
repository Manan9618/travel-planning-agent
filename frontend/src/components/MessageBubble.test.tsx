import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MessageBubble } from './MessageBubble'

describe('MessageBubble', () => {
  it('renders its content', () => {
    render(<MessageBubble role="user">Hello there</MessageBubble>)
    expect(screen.getByText('Hello there')).toBeInTheDocument()
  })

  it('right-aligns user messages', () => {
    render(<MessageBubble role="user">Hi</MessageBubble>)
    const wrapper = screen.getByText('Hi').parentElement
    expect(wrapper?.className).toContain('justify-end')
  })

  it('left-aligns assistant messages', () => {
    render(<MessageBubble role="assistant">Hi</MessageBubble>)
    const wrapper = screen.getByText('Hi').parentElement
    expect(wrapper?.className).toContain('justify-start')
  })

  it('applies error styling when tone is error', () => {
    render(
      <MessageBubble role="assistant" tone="error">
        Failed
      </MessageBubble>,
    )
    expect(screen.getByText('Failed').className).toContain('text-red-700')
  })
})
