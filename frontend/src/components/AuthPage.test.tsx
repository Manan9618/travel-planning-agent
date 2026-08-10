import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AuthPage } from './AuthPage'

const { login, register } = vi.hoisted(() => ({ login: vi.fn(), register: vi.fn() }))
vi.mock('@/lib/useAuth', () => ({ useAuth: () => ({ login, register }) }))

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
})
