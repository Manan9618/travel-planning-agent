import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { AuthProvider, useAuth } from '@/lib/useAuth'

const { getAuthToken, setAuthToken, login, register, getCurrentUser } = vi.hoisted(() => ({
  getAuthToken: vi.fn(),
  setAuthToken: vi.fn(),
  login: vi.fn(),
  register: vi.fn(),
  getCurrentUser: vi.fn(),
}))
vi.mock('@/lib/api', () => ({ getAuthToken, setAuthToken, login, register, getCurrentUser }))

function renderAuth() {
  return renderHook(() => useAuth(), { wrapper: AuthProvider })
}

describe('useAuth', () => {
  beforeEach(() => {
    getAuthToken.mockReturnValue(null)
  })

  it('throws when used outside an AuthProvider', () => {
    expect(() => renderHook(() => useAuth())).toThrow(/AuthProvider/)
  })

  it('starts with no user and stops loading when there is no stored token', async () => {
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(getCurrentUser).not.toHaveBeenCalled()
  })

  it('restores the user from a stored token on mount', async () => {
    getAuthToken.mockReturnValue('stored-token')
    getCurrentUser.mockResolvedValueOnce({ user_id: 'u1', email: 'traveler@example.com' })

    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toEqual({ user_id: 'u1', email: 'traveler@example.com' })
  })

  it('clears a stored token that no longer validates', async () => {
    getAuthToken.mockReturnValue('stale-token')
    getCurrentUser.mockRejectedValueOnce(new Error('401 Unauthorized'))

    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.user).toBeNull()
    expect(setAuthToken).toHaveBeenCalledWith(null)
  })

  it('login stores the token and sets the user', async () => {
    login.mockResolvedValueOnce({
      access_token: 'tok',
      token_type: 'bearer',
      user_id: 'u1',
      email: 'traveler@example.com',
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.login('traveler@example.com', 'hunter2222')
    })

    expect(setAuthToken).toHaveBeenCalledWith('tok')
    expect(result.current.user).toEqual({ user_id: 'u1', email: 'traveler@example.com' })
    expect(result.current.error).toBeNull()
  })

  it('register stores the token and sets the user', async () => {
    register.mockResolvedValueOnce({
      access_token: 'tok2',
      token_type: 'bearer',
      user_id: 'u2',
      email: 'new@example.com',
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await result.current.register('new@example.com', 'hunter2222')
    })

    expect(setAuthToken).toHaveBeenCalledWith('tok2')
    expect(result.current.user).toEqual({ user_id: 'u2', email: 'new@example.com' })
  })

  it('login failure sets an error and leaves the user unset', async () => {
    login.mockRejectedValueOnce(new Error('401 Unauthorized'))
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))

    await act(async () => {
      await expect(result.current.login('traveler@example.com', 'wrong')).rejects.toThrow()
    })

    expect(result.current.user).toBeNull()
    expect(result.current.error).toMatch(/401/)
  })

  it('logout clears the token and the user', async () => {
    login.mockResolvedValueOnce({
      access_token: 'tok',
      token_type: 'bearer',
      user_id: 'u1',
      email: 'traveler@example.com',
    })
    const { result } = renderAuth()
    await waitFor(() => expect(result.current.loading).toBe(false))
    await act(async () => {
      await result.current.login('traveler@example.com', 'hunter2222')
    })

    act(() => {
      result.current.logout()
    })

    expect(setAuthToken).toHaveBeenCalledWith(null)
    expect(result.current.user).toBeNull()
  })
})
