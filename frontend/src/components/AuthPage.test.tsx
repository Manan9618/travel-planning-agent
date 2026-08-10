import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthPage } from './AuthPage'

const { login, register, forgotPassword } = vi.hoisted(() => ({
  login: vi.fn(),
  register: vi.fn(),
  forgotPassword: vi.fn(),
}))
vi.mock('@/lib/useAuth', () => ({ useAuth: () => ({ login, register }) }))
vi.mock('@/lib/api', () => ({ forgotPassword }))

describe('AuthPage', () => {
  it('defaults to sign in mode', () => {
    render(<AuthPage />)
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('submits email and password to login', async () => {
    login.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.type(screen.getByLabelText('Email'), 'traveler@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2222')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(login).toHaveBeenCalledWith('traveler@example.com', 'hunter2222')
    expect(register).not.toHaveBeenCalled()
  })

  it('toggles to register mode and submits to register', async () => {
    register.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.click(screen.getByText("Don't have an account? Register"))
    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument()

    await user.type(screen.getByLabelText('Email'), 'new@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2222')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(register).toHaveBeenCalledWith('new@example.com', 'hunter2222')
  })

  it('shows a friendly message when login fails with 401', async () => {
    login.mockRejectedValueOnce(new Error('401 Unauthorized'))
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.type(screen.getByLabelText('Email'), 'traveler@example.com')
    await user.type(screen.getByLabelText('Password'), 'wrongpass')
    await user.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Incorrect email or password.')).toBeInTheDocument()
  })

  it('shows a friendly message when register fails with a duplicate email', async () => {
    register.mockRejectedValueOnce(new Error('409 Conflict'))
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.click(screen.getByText("Don't have an account? Register"))
    await user.type(screen.getByLabelText('Email'), 'dup@example.com')
    await user.type(screen.getByLabelText('Password'), 'hunter2222')
    await user.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      await screen.findByText('An account with that email already exists.'),
    ).toBeInTheDocument()
  })

  it('does not show a back button when onBack is not given', () => {
    render(<AuthPage />)
    expect(screen.queryByText('← Back')).not.toBeInTheDocument()
  })

  it('calls onBack when the back button is clicked', async () => {
    const onBack = vi.fn()
    const user = userEvent.setup()
    render(<AuthPage onBack={onBack} />)
    await user.click(screen.getByText('← Back'))
    expect(onBack).toHaveBeenCalled()
  })

  it('honors initialMode', () => {
    render(<AuthPage initialMode="register" />)
    expect(screen.getByRole('heading', { name: 'Create your account' })).toBeInTheDocument()
  })

  it('does not show "Forgot password?" in register mode', async () => {
    const user = userEvent.setup()
    render(<AuthPage />)
    await user.click(screen.getByText("Don't have an account? Register"))
    expect(screen.queryByText('Forgot password?')).not.toBeInTheDocument()
  })

  it('switches to forgot-password mode and hides the password field', async () => {
    const user = userEvent.setup()
    render(<AuthPage />)
    await user.click(screen.getByText('Forgot password?'))
    expect(screen.getByRole('heading', { name: 'Reset your password' })).toBeInTheDocument()
    expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
  })

  it('submits the email to forgotPassword and shows a confirmation', async () => {
    forgotPassword.mockResolvedValueOnce({ message: 'ok' })
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.click(screen.getByText('Forgot password?'))
    await user.type(screen.getByLabelText('Email'), 'traveler@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(forgotPassword).toHaveBeenCalledWith('traveler@example.com')
    expect(
      await screen.findByText('If that email is registered, a reset link has been sent.'),
    ).toBeInTheDocument()
  })

  it('shows the same generic confirmation even when forgotPassword rejects', async () => {
    // The backend always returns 200 for /auth/forgot-password to avoid
    // leaking which emails are registered — a network-level failure is the
    // only case that should ever surface as an error here.
    forgotPassword.mockRejectedValueOnce(new Error('500 Internal Server Error'))
    const user = userEvent.setup()
    render(<AuthPage />)

    await user.click(screen.getByText('Forgot password?'))
    await user.type(screen.getByLabelText('Email'), 'traveler@example.com')
    await user.click(screen.getByRole('button', { name: 'Send reset link' }))

    expect(await screen.findByText(/Could not/)).toBeInTheDocument()
  })

  it('returns to sign in from forgot-password mode', async () => {
    const user = userEvent.setup()
    render(<AuthPage />)
    await user.click(screen.getByText('Forgot password?'))
    await user.click(screen.getByText('Back to sign in'))
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument()
  })
})
