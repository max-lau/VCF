import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/api/client'

// Roles whose access is scoped to assigned matters only
const SCOPED_ROLES = new Set(['paralegal', 'client_viewer'])

export const usePermissionsStore = defineStore('permissions', () => {
  const role     = ref(null)
  const tier     = ref(99)
  const modules  = ref({})
  const loaded   = ref(false)
  const isScoped = computed(() => SCOPED_ROLES.has(role.value))

  // Apply a permissions object (from login response or /api/me/permissions)
  function apply(perms) {
    role.value    = perms.role    ?? null
    tier.value    = perms.tier    ?? 99
    modules.value = perms.modules ?? {}
    loaded.value  = true
  }

  // Fetch from backend (on app mount if token already exists)
  async function fetch() {
    try {
      const { data } = await client.get('/auth/me/permissions')
      apply(data)
    } catch {
      // If fetch fails, clear — navigation guard will redirect to login
      clear()
    }
  }

  function clear() {
    role.value    = null
    tier.value    = 99
    modules.value = {}
    loaded.value  = false
  }

  // ── Core permission check ──────────────────────────────────────────
  function can(module, action = 'read') {
    if (!loaded.value) return false
    if (role.value === 'paraiq_super') return true
    const mod = modules.value[module]
    if (!mod) return tier.value <= 3  // default open for firm_admin+
    return !!mod[action]
  }

  // Tier check: lower = more authority
  function isTier(maxTier) {
    return tier.value <= maxTier
  }

  function isRole(roleName) {
    return role.value === roleName
  }

  // ── Pre-computed permission flags (used in Sidebar / route guards) ─
  const isFirmAdmin   = computed(() => isTier(1))
  const isAttorney    = computed(() => isTier(2))
  const isLegalStaff  = computed(() => isTier(4))

  // Module gates used across the app
  const gates = computed(() => ({
    // Case work
    matters:       can('matters',       'read'),
    documents:     can('documents',     'read'),
    privilege_log: can('privilege_log', 'read'),
    timeline:      can('timeline',      'read'),
    discovery:     can('discovery',     'read'),
    depositions:   can('depositions',   'read'),
    motions:       can('motions',       'read'),
    contracts:     can('contracts',     'read'),
    correspondence:can('correspondence','read'),
    calendar:      can('calendar',      'read'),
    contacts:      can('contacts',      'read'),
    // AI & Analysis
    legal_bert:    can('legal_bert',    'read'),
    legal_research:can('legal_research','read'),
    ai_config:     can('ai_config',     'read'),
    exports:       can('exports',       'export'),
    reports:       can('reports',       'read'),
    // NLP tools
    risk:          can('risk',          'read'),
    intake:        can('intake',        'read'),
    redaction:     can('redaction',     'read'),
    review:        can('review',        'read'),
    scorer:        can('scorer',        'read'),
    analyzer:      can('analyzer',      'read'),
    batch:         can('batch',         'read'),
    citations:     can('citations',     'read'),
    compare:       can('compare',       'read'),
    credibility:   can('credibility',   'read'),
    interrogation: can('interrogation', 'read'),
    media:         can('media',         'read'),
    model:         can('model',         'read'),
    multilingual:  can('multilingual',  'read'),
    insights:      can('insights',      'read'),
    // Client portal
    client_portal: can('client_portal', 'read'),
    // Firm admin
    users_roles:   can('users_roles',   'read'),
    audit_log:     can('audit_log',     'read'),
    enclave_mgmt:  can('enclave_mgmt',  'read'),
    billing:       can('billing',       'read'),
  }))

  return {
    role, tier, modules, loaded, isScoped,
    isFirmAdmin, isAttorney, isLegalStaff, gates,
    apply, fetch, clear, can, isTier, isRole,
  }
})
