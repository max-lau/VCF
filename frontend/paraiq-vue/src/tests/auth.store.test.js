import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() }
}))
vi.mock('axios', () => ({
  default: { post: vi.fn() }
}))

import { useAuthStore } from '@/stores/auth'

describe('Auth Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('isAuthenticated is false with no token', () => {
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(false)
  })

  it('isAuthenticated is true when localStorage has token', () => {
    localStorage.setItem('paraiq_token', 'some-jwt')
    setActivePinia(createPinia())
    const auth = useAuthStore()
    expect(auth.isAuthenticated).toBe(true)
  })

  it('firmId returns "default" when no user', () => {
    expect(useAuthStore().firmId).toBe('default')
  })

  it('userEmail returns empty string when no user', () => {
    expect(useAuthStore().userEmail).toBe('')
  })

  it('userId returns null when no user', () => {
    expect(useAuthStore().userId).toBeNull()
  })

  it('login success sets token, user, and localStorage', async () => {
    const axios = (await import('axios')).default
    axios.post.mockResolvedValue({
      data: {
        token: 'test-jwt',
        user_id: 42,
        username: 'testuser',
        email: 'test@firm.com',
        role: 'associate',
        tier: 3,
        firm_id: 'acme',
        permissions: { role: 'associate', tier: 3, modules: {} },
      }
    })

    const auth = useAuthStore()
    const result = await auth.login('testuser', 'pass123', 'acme')

    expect(result.ok).toBe(true)
    expect(auth.isAuthenticated).toBe(true)
    expect(auth.userEmail).toBe('test@firm.com')
    expect(auth.firmId).toBe('acme')
    expect(localStorage.getItem('paraiq_token')).toBe('test-jwt')
    expect(JSON.parse(localStorage.getItem('paraiq_user')).email).toBe('test@firm.com')
  })

  it('login failure returns ok:false and sets error', async () => {
    const axios = (await import('axios')).default
    axios.post.mockRejectedValue({
      response: { status: 401, data: { detail: 'Invalid username or password' } }
    })

    const auth = useAuthStore()
    const result = await auth.login('wrong', 'bad')

    expect(result.ok).toBe(false)
    expect(result.error).toContain('Invalid')
    expect(auth.isAuthenticated).toBe(false)
  })

  it('login sets loading to false after failure', async () => {
    const axios = (await import('axios')).default
    axios.post.mockRejectedValue({ response: { status: 401, data: {} } })
    const auth = useAuthStore()
    await auth.login('x', 'y')
    expect(auth.loading).toBe(false)
  })

  it('logout clears token, user, and localStorage', async () => {
    localStorage.setItem('paraiq_token', 'tok')
    localStorage.setItem('paraiq_user', JSON.stringify({ email: 'x@x.com' }))
    setActivePinia(createPinia())
    const auth = useAuthStore()
    await auth.logout()
    expect(auth.isAuthenticated).toBe(false)
    expect(localStorage.getItem('paraiq_token')).toBeNull()
    expect(localStorage.getItem('paraiq_user')).toBeNull()
  })

  it('_roleTier maps paraiq_super to tier 0', async () => {
    const axios = (await import('axios')).default
    axios.post.mockResolvedValue({
      data: {
        token: 'tok', user_id: 1, username: 'su', email: 'su@x.com',
        role: 'paraiq_super', tier: 0, firm_id: 'hq',
        permissions: { role: 'paraiq_super', tier: 0, modules: {} },
      }
    })
    const auth = useAuthStore()
    await auth.login('su', 'pass')
    expect(auth.user.tier).toBe(0)
  })
})
