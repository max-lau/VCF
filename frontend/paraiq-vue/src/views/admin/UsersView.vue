<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const users    = ref([])
const loading  = ref(false)
const search   = ref('')
const roleFilter = ref('')
const error    = ref(null)
const pending  = ref({})   // { [userId]: 'active' | 'role' }

const ROLES = ['admin', 'attorney', 'paralegal', 'associate']

const ROLE_COLORS = {
  admin:     { bg: 'rgba(201,168,76,.18)',  color: 'var(--gold)' },
  attorney:  { bg: 'rgba(74,158,255,.18)',  color: '#4a9eff' },
  paralegal: { bg: 'rgba(76,175,121,.18)',  color: '#4caf79' },
  associate: { bg: 'rgba(150,150,150,.18)', color: '#b0b0b0' },
}

const filtered = computed(() => {
  const q = search.value.trim().toLowerCase()
  return users.value.filter(u => {
    if (roleFilter.value && (u.role || '').toLowerCase() !== roleFilter.value) return false
    if (!q) return true
    return [u.username, u.email, u.role]
      .filter(Boolean).some(v => v.toLowerCase().includes(q))
  })
})

const stats = computed(() => ({
  total:      users.value.length,
  active:     users.value.filter(u => u.is_active).length,
  byRole: ROLES.reduce((acc, r) => {
    acc[r] = users.value.filter(u => (u.role || '').toLowerCase() === r).length
    return acc
  }, {})
}))

async function fetchUsers() {
  loading.value = true; error.value = null
  try {
    const { data } = await client.get('/auth/users')
    users.value = Array.isArray(data) ? data : (data.users || [])
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load users'
    users.value = []
  } finally { loading.value = false }
}

async function toggleActive(u) {
  if (u.is_active && !confirm(`Deactivate ${u.username}? They will lose access immediately.`)) return
  pending.value[u.id] = 'active'
  try {
    const next = !u.is_active
    await client.put(`/auth/users/${u.id}/active`, { is_active: next })
    u.is_active = next
  } catch (e) {
    error.value = e.response?.data?.detail || 'Update failed'
  } finally { delete pending.value[u.id] }
}

async function changeRole(u, newRole) {
  if (!newRole || newRole === u.role) return
  if (!confirm(`Change ${u.username}'s role to ${newRole}?`)) {
    // revert select via nextTick re-render trick: rely on :value binding
    return
  }
  pending.value[u.id] = 'role'
  try {
    await client.put(`/auth/users/${u.id}/role`, { role: newRole })
    u.role = newRole
  } catch (e) {
    error.value = e.response?.data?.detail || 'Role change failed'
  } finally { delete pending.value[u.id] }
}

function roleBadgeStyle(role) {
  const c = ROLE_COLORS[(role || '').toLowerCase()] || ROLE_COLORS.associate
  return { background: c.bg, color: c.color }
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—'
}

let searchTimer = null
function onSearch() { clearTimeout(searchTimer) }

onMounted(fetchUsers)
</script>

<template>
  <div class="users">
    <div class="users__header">
      <div>
        <h1 class="users__title">Users &amp; Roles</h1>
        <p class="users__sub">Manage team members, role assignments, and access</p>
      </div>
      <button class="btn-secondary" @click="fetchUsers">↻ Refresh</button>
    </div>

    <div v-if="error" class="err-msg">{{ error }}</div>

    <!-- Quick stats -->
    <div class="stat-row">
      <div class="stat-chip"><span class="stat-chip__n">{{ stats.total }}</span><span class="stat-chip__l">Total</span></div>
      <div class="stat-chip"><span class="stat-chip__n">{{ stats.active }}</span><span class="stat-chip__l">Active</span></div>
      <div v-for="r in ROLES" :key="r" class="stat-chip">
        <span class="stat-chip__n" :style="roleBadgeStyle(r)">{{ stats.byRole[r] }}</span>
        <span class="stat-chip__l" style="text-transform:capitalize">{{ r }}</span>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <input class="search-input" v-model="search" @input="onSearch" placeholder="Search username, email…" />
      <select class="bar-select" v-model="roleFilter">
        <option value="">All roles</option>
        <option v-for="r in ROLES" :key="r" :value="r" style="text-transform:capitalize">{{ r }}</option>
      </select>
    </div>

    <div v-if="loading" class="state-msg">Loading users…</div>

    <div v-else-if="!filtered.length" class="empty">
      <div class="empty__icon">👥</div>
      <div class="empty__title">No users found</div>
      <div class="empty__sub">Adjust filters or add new team members.</div>
    </div>

    <div v-else class="users-table-wrap">
      <table class="users-table">
        <thead>
          <tr>
            <th>User</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in filtered" :key="u.id">
            <td class="user-cell">
              <span class="user-avatar">{{ (u.username || '?').charAt(0).toUpperCase() }}</span>
              <span class="bold">{{ u.username || '—' }}</span>
            </td>
            <td class="dim">{{ u.email || '—' }}</td>
            <td>
              <span class="role-badge" :style="roleBadgeStyle(u.role)">{{ u.role || '—' }}</span>
            </td>
            <td>
              <span class="status-pill" :class="u.is_active ? 'status--active' : 'status--inactive'">
                {{ u.is_active ? 'Active' : 'Inactive' }}
              </span>
            </td>
            <td class="dim nowrap">{{ fmtDate(u.created_at || u.created) }}</td>
            <td class="actions-cell">
              <select
                class="role-select"
                :value="u.role"
                :disabled="!!pending[u.id]"
                @change="changeRole(u, $event.target.value)"
                title="Change role"
              >
                <option v-for="r in ROLES" :key="r" :value="r">{{ r }}</option>
              </select>
              <button
                class="toggle-btn"
                :class="u.is_active ? 'toggle-btn--deactivate' : 'toggle-btn--activate'"
                :disabled="!!pending[u.id]"
                @click="toggleActive(u)"
              >
                <span v-if="pending[u.id]">…</span>
                <template v-else>{{ u.is_active ? 'Deactivate' : 'Activate' }}</template>
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.users { padding: 2rem; max-width: 1200px; }
.users__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.users__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.users__sub { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.err-msg { color: #fc8181; font-size: 0.875rem; margin-bottom: 1rem; }
.stat-row { display: flex; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 1.25rem; }
.stat-chip { align-items: center; background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; gap: 0.4rem; padding: 0.4rem 0.75rem; }
.stat-chip__n { color: var(--gold); font-weight: 700; font-size: 0.95rem; }
.stat-chip__l { color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }
.filter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.search-input { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; outline: none; padding: 0.4rem 0.75rem; flex: 1; max-width: 340px; }
.search-input:focus { border-color: var(--gold); }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 160px; }
.users-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.users-table { border-collapse: collapse; font-size: 0.85rem; width: 100%; }
.users-table th { background: var(--bg-card); border-bottom: 1px solid var(--border); color: var(--text-muted); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.05em; padding: 0.65rem 0.9rem; text-align: left; text-transform: uppercase; white-space: nowrap; }
.users-table td { border-bottom: 1px solid var(--border); padding: 0.65rem 0.9rem; vertical-align: middle; }
.users-table tr:last-child td { border-bottom: none; }
.users-table tr:hover td { background: rgba(255,255,255,.02); }
.user-cell { display: flex; align-items: center; gap: 0.5rem; white-space: nowrap; }
.user-avatar { align-items: center; background: rgba(201,168,76,.2); border-radius: 50%; color: var(--gold); display: inline-flex; font-size: 0.65rem; font-weight: 700; height: 22px; justify-content: center; width: 22px; flex-shrink: 0; }
.role-badge { border-radius: 4px; font-size: 0.72rem; font-weight: 600; padding: 0.18rem 0.55rem; text-transform: capitalize; }
.status-pill { border-radius: 4px; font-size: 0.7rem; font-weight: 600; padding: 0.18rem 0.5rem; text-transform: capitalize; }
.status--active { background: rgba(76,175,121,.18); color: #4caf79; }
.status--inactive { background: rgba(150,150,150,.18); color: #b0b0b0; }
.actions-cell { display: flex; align-items: center; gap: 0.4rem; white-space: nowrap; }
.role-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: 0.78rem; padding: 0.25rem 0.4rem; text-transform: capitalize; }
.role-select:disabled { opacity: 0.5; cursor: not-allowed; }
.toggle-btn { background: transparent; border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 0.25rem 0.6rem; transition: all 0.15s; }
.toggle-btn--activate { border-color: #4caf79; color: #4caf79; }
.toggle-btn--activate:hover { background: rgba(76,175,121,.15); }
.toggle-btn--deactivate { border-color: #fc8181; color: #fc8181; }
.toggle-btn--deactivate:hover { background: rgba(252,129,129,.12); }
.toggle-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.nowrap { white-space: nowrap; }
.bold { font-weight: 500; }
.dim { color: var(--text-muted); }
.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon { font-size: 2.5rem; opacity: 0.3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all 0.15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
</style>
