import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ResetPasswordPage } from './ResetPasswordPage'

const { resetPassword } = vi.hoisted(() => ({ resetPassword: vi.fn() }))
vi.mock('@/lib/api', () => ({ resetPassword }))

describe('ResetPasswordPage', () => {
  it('shows the set-new-password form initially', () => {
    render(<ResetPasswordPage token="tok" onDone={vi.fn()} />)
    expect(screen.getByRole('heading', { name: 'Set a new password' })).toBeInTheDocument()
  })

  it('rejects mismatched passwords without calling resetPassword', async () => {
    const user = userEvent.setup()
    render(<ResetPasswordPage token="tok" onDone={vi.fn()} />)

    await user.type(screen.getByLabelText('New password'), 'password-one')
    await user.type(screen.getByLabelText('Confirm password'), 'password-two')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(await screen.findByText('Passwords do not match.')).toBeInTheDocument()
    expect(resetPassword).not.toHaveBeenCalled()
  })

  it('submits the token and new password, then shows success', async () => {
    resetPassword.mockResolvedValueOnce({ message: 'ok' })
    const user = userEvent.setup()
    render(<ResetPasswordPage token="tok-123" onDone={vi.fn()} />)

    await user.type(screen.getByLabelText('New password'), 'brand-new-password')
    await user.type(screen.getByLabelText('Confirm password'), 'brand-new-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(resetPassword).toHaveBeenCalledWith('tok-123', 'brand-new-password')
    expect(await screen.findByRole('heading', { name: 'Password updated' })).toBeInTheDocument()
  })

  it('calls onDone when "Go to sign in" is clicked after success', async () => {
    resetPassword.mockResolvedValueOnce({ message: 'ok' })
    const onDone = vi.fn()
    const user = userEvent.setup()
    render(<ResetPasswordPage token="tok" onDone={onDone} />)

    await user.type(screen.getByLabelText('New password'), 'brand-new-password')
    await user.type(screen.getByLabelText('Confirm password'), 'brand-new-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))
    await user.click(await screen.findByRole('button', { name: 'Go to sign in' }))

    expect(onDone).toHaveBeenCalled()
  })

  it('shows a friendly message for an invalid or expired token', async () => {
    resetPassword.mockRejectedValueOnce(new Error('400 Bad Request'))
    const user = userEvent.setup()
    render(<ResetPasswordPage token="expired-tok" onDone={vi.fn()} />)

    await user.type(screen.getByLabelText('New password'), 'brand-new-password')
    await user.type(screen.getByLabelText('Confirm password'), 'brand-new-password')
    await user.click(screen.getByRole('button', { name: 'Reset password' }))

    expect(
      await screen.findByText('This reset link is invalid or has expired. Request a new one.'),
    ).toBeInTheDocument()
  })
})
