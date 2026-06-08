import axios from 'axios'
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client from '@/api/client'
import { usePermissionsStore } from './permissions'

export const useAuthStore = defineStore('auth', () => {
  const token    = ref(localStorage.getItem('paraiq_token') || null)
  const user     = ref((() => { try { return JSON.parse(localStorage.getItem('paraiq_user') || 'null') } catch(e) { localStorage.removeItem('paraiq_user'); return null } })())
  const loading  = ref(false)
  const error    = ref(null)

  const isAuthenticated = computed(() => !!token.value)
  const firmId          = computed(() => user.value?.firm_id || 'default')
  const FIRM_NAMES = {
    'default':       'ParaIQ',
    'firm_abc':      'Thornton & Associates',
    'meridian_legal':'Meridian Legal Group',
  }
  const firmName = computed(() => FIRM_NAMES[firmId.value] || firmId.value)
  const userEmail       = computed(() => user.value?.email || user.value?.username || '')
  const userId          = computed(() => user.value?.user_id || null)

  // Fallback tier mapping for legacy role strings before roles migration
  function _roleTier(role) {
    const map = {
      paraiq_super:    0,
      firm_admin:      1, admin: 1,
      senior_attorney: 2,
      associate:       3, user: 3,
      paralegal:       4,
      client_viewer:   5,
      billing_contact: 6,
    }
    return map[role] ?? 3
  }

  async function login(username, password, firm_id = 'default') {
    loading.value = true
    error.value   = null
    try {
      const { data } = await axios.post('/auth/login', { username, password })

      token.value = data.token
      user.value  = {
        user_id:  data.user_id,
        username: data.username,
        email:    data.email || '',
        firm_id:  data.firm_id || firm_id,
        role:     data.role,
        tier:     data.tier ?? _roleTier(data.role),
      }

      localStorage.setItem('paraiq_token', data.token)
      localStorage.setItem('paraiq_user',  JSON.stringify(user.value))

      // Bootstrap permissions from login response or fetch separately
      const permStore = usePermissionsStore()
      if (data.permissions) {
        permStore.apply(data.permissions)
      } else {
        await permStore.fetch()
      }

      return { ok: true }
    } catch (e) {
      error.value = e.response?.data?.detail || e.response?.data?.error || 'Login failed'
      return { ok: false, error: error.value }
    } finally {
      loading.value = false
    }
  }

  async function logout() {
    token.value = null
    user.value  = null
    localStorage.removeItem('paraiq_token')
    localStorage.removeItem('paraiq_user')
    const permStore = usePermissionsStore()
    permStore.clear()
  }

  // Re-hydrate permissions from localStorage token on app mount
  async function init() {
    if (!token.value) return
    const permStore = usePermissionsStore()
    if (!permStore.loaded) {
      await permStore.fetch()
    }
  }

  return {
    token, user, loading, error,
    isAuthenticated, firmId, firmName, userEmail, userId,
    login, logout, init,
  }
})
