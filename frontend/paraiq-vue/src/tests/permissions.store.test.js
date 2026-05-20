import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api/client', () => ({
  default: { get: vi.fn(), post: vi.fn() }
}))

import { usePermissionsStore } from '@/stores/permissions'

const FULL_PERMS = {
  role: 'associate',
  tier: 3,
  modules: {
    matters:   { read: true,  write: false, export: false },
    documents: { read: true,  write: true,  export: true  },
    billing:   { read: false, write: false, export: false },
  }
}

describe('Permissions Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  // ── Initial state ────────────────────────────────────────────────────────
  it('can() returns false when not loaded', () => {
    expect(usePermissionsStore().can('matters')).toBe(false)
  })

  it('loaded is false initially', () => {
    expect(usePermissionsStore().loaded).toBe(false)
  })

  it('tier is 99 initially', () => {
    expect(usePermissionsStore().tier).toBe(99)
  })

  it('role is null initially', () => {
    expect(usePermissionsStore().role).toBeNull()
  })

  // ── apply() ──────────────────────────────────────────────────────────────
  it('apply() sets role, tier, modules, loaded', () => {
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)
    expect(perms.role).toBe('associate')
    expect(perms.tier).toBe(3)
    expect(perms.loaded).toBe(true)
    expect(perms.modules).toEqual(FULL_PERMS.modules)
  })

  // ── can() ────────────────────────────────────────────────────────────────
  it('can() returns true for paraiq_super on any module', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'paraiq_super', tier: 0, modules: {} })
    expect(perms.can('matters')).toBe(true)
    expect(perms.can('billing')).toBe(true)
    expect(perms.can('nonexistent_module')).toBe(true)
    expect(perms.can('billing', 'write')).toBe(true)
  })

  it('can() respects module read permission', () => {
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)
    expect(perms.can('matters',   'read')).toBe(true)
    expect(perms.can('billing',   'read')).toBe(false)
  })

  it('can() respects module write permission', () => {
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)
    expect(perms.can('documents', 'write')).toBe(true)
    expect(perms.can('matters',   'write')).toBe(false)
  })

  it('can() defaults to tier check for unknown modules', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'firm_admin', tier: 1, modules: {} })
    expect(perms.can('unknown_module')).toBe(true)   // tier 1 <= 3
  })

  // ── isTier() ─────────────────────────────────────────────────────────────
  it('isTier() returns true when tier <= maxTier', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'associate', tier: 3, modules: {} })
    expect(perms.isTier(3)).toBe(true)
    expect(perms.isTier(4)).toBe(true)
    expect(perms.isTier(5)).toBe(true)
  })

  it('isTier() returns false when tier > maxTier', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'associate', tier: 3, modules: {} })
    expect(perms.isTier(2)).toBe(false)
    expect(perms.isTier(1)).toBe(false)
  })

  // ── clear() ──────────────────────────────────────────────────────────────
  it('clear() resets all state', () => {
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)
    perms.clear()
    expect(perms.role).toBeNull()
    expect(perms.tier).toBe(99)
    expect(perms.loaded).toBe(false)
    expect(perms.can('matters')).toBe(false)
  })

  // ── Computed ─────────────────────────────────────────────────────────────
  it('isFirmAdmin is true for tier <= 1', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'firm_admin', tier: 1, modules: {} })
    expect(perms.isFirmAdmin).toBe(true)
  })

  it('isFirmAdmin is false for tier > 1', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'associate', tier: 3, modules: {} })
    expect(perms.isFirmAdmin).toBe(false)
  })

  it('isScoped is true for paralegal', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'paralegal', tier: 4, modules: {} })
    expect(perms.isScoped).toBe(true)
  })

  it('isScoped is false for associate', () => {
    const perms = usePermissionsStore()
    perms.apply({ role: 'associate', tier: 3, modules: {} })
    expect(perms.isScoped).toBe(false)
  })

  it('gates.matters is true when module allows read', () => {
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)
    expect(perms.gates.matters).toBe(true)
    expect(perms.gates.billing).toBe(false)
  })

  // ── fetch() ──────────────────────────────────────────────────────────────
  it('fetch() calls /auth/me/permissions and applies result', async () => {
    const client = (await import('@/api/client')).default
    client.get.mockResolvedValue({ data: FULL_PERMS })
    const perms = usePermissionsStore()
    await perms.fetch()
    expect(client.get).toHaveBeenCalledWith('/auth/me/permissions')
    expect(perms.role).toBe('associate')
    expect(perms.loaded).toBe(true)
  })

  it('fetch() calls clear() on network error', async () => {
    const client = (await import('@/api/client')).default
    client.get.mockRejectedValue(new Error('Network error'))
    const perms = usePermissionsStore()
    perms.apply(FULL_PERMS)   // pre-load some state
    await perms.fetch()
    expect(perms.loaded).toBe(false)  // clear() was called
  })
})
