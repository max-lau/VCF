<script setup>
import { ref, computed, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import axios from 'axios'

const auth = useAuthStore()
const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: `Bearer ${token()}` })

// ── State ─────────────────────────────────────────────────────────────────────
const activeTab    = ref('users')
const users        = ref([])
const loading      = ref(true)
const loadError    = ref(null)
const search       = ref('')
const filterRole   = ref('')
const saving       = ref({})
const showInvite   = ref(false)
const inviteForm   = ref({ username: '', email: '', password: '', role: 'associate', firm_id: auth.firmId || 'default' })
const inviteError  = ref(null)
const inviteSaving = ref(false)
const auditRows    = ref([])
const auditLoading = ref(false)
const health       = ref(null)

// ── Constants ─────────────────────────────────────────────────────────────────
const ROLES = [
  { value: 'paraiq_super',    label: 'ParaIQ Super',    tier: 0, desc: 'Internal platform administrators' },
  { value: 'firm_admin',      label: 'Firm Admin',      tier: 1, desc: 'Full access to all firm modules and settings' },
  { value: 'senior_attorney', label: 'Senior Attorney', tier: 2, desc: 'Full matter access, can delegate to juniors' },
  { value: 'associate',       label: 'Associate',       tier: 3, desc: 'Full matter access, standard permissions' },
  { value: 'paralegal',       label: 'Paralegal',       tier: 4, desc: 'Scoped to assigned matters only' },
  { value: 'client_viewer',   label: 'Client Viewer',   tier: 5, desc: 'Read-only access to assigned matters' },
  { value: 'billing_contact', label: 'Billing Contact', tier: 6, desc: 'Billing information only' },
]

const TABS = [
  { id: 'users',  label: 'Users'     },
  { id: 'roles',  label: 'Roles'     },
  { id: 'audit',  label: 'Audit Log' },
  { id: 'system',  label: 'System'   },
  { id: 'billing', label: 'SaaS Billing' },
]

// ── Computed ──────────────────────────────────────────────────────────────────
const filteredUsers = computed(() =>
  users.value.filter(u => {
    const q = search.value.toLowerCase()
    const matchSearch = !q || u.username.toLowerCase().includes(q) || u.email.toLowerCase().includes(q)
    const matchRole   = !filterRole.value || u.role === filterRole.value
    return matchSearch && matchRole
  })
)

const usersByRole = computed(() => {
  const counts = {}
  users.value.forEach(u => { counts[u.role] = (counts[u.role] || 0) + 1 })
  return counts
})

const tabsWithCounts = computed(() =>
  TABS.map(t => ({
    ...t,
    count: t.id === 'users' ? users.value.length
         : t.id === 'audit' ? auditRows.value.length
         : null,
  }))
)

// ── Data fetching ─────────────────────────────────────────────────────────────
async function fetchUsers() {
  loading.value = true
  loadError.value = null
  try {
    const { data } = await axios.get('/auth/users', { headers: authHdr() })
    users.value = data.users.map(u => ({ ...u, _role: u.role }))
  } catch (e) {
    loadError.value = e.response?.data?.detail || 'Failed to load users'
  } finally {
    loading.value = false
  }
}

async function fetchAudit() {
  auditLoading.value = true
  try {
    const { data } = await axios.get('/api/audit/logs?limit=50', { headers: authHdr() })
    auditRows.value = data.entries || data.log || (Array.isArray(data) ? data : [])
  } catch {
    auditRows.value = []
  } finally {
    auditLoading.value = false
  }
}

async function fetchHealth() {
  health.value = null
  try {
    const { data } = await axios.get('/health')
    health.value = data.status === 'ok'
  } catch {
    health.value = false
  }
}

// ── Actions ───────────────────────────────────────────────────────────────────
async function updateRole(user) {
  if (user._role === user.role) return
  saving.value = { ...saving.value, [user.id]: true }
  try {
    await axios.put(`/auth/users/${user.id}/role`, { role: user._role }, { headers: authHdr() })
    user.role = user._role
  } catch (e) {
    user._role = user.role
    alert(e.response?.data?.detail || 'Failed to update role')
  } finally {
    const s = { ...saving.value }
    delete s[user.id]
    saving.value = s
  }
}

async function toggleStatus(user) {
  if (user.id === auth.userId) return
  saving.value = { ...saving.value, [user.id]: true }
  try {
    const { data } = await axios.put(`/auth/users/${user.id}/active`, {}, { headers: authHdr() })
    user.active = data.active
  } catch (e) {
    alert(e.response?.data?.detail || 'Failed to update status')
  } finally {
    const s = { ...saving.value }
    delete s[user.id]
    saving.value = s
  }
}

async function submitInvite() {
  inviteError.value = null
  if (!inviteForm.value.username || !inviteForm.value.email || !inviteForm.value.password) {
    inviteError.value = 'All fields are required'
    return
  }
  inviteSaving.value = true
  try {
    const payload = { ...inviteForm.value, firm_id: auth.firmId || 'default' }
    await axios.post('/auth/register', payload, { headers: authHdr() })
    showInvite.value = false
    inviteForm.value = { username: '', email: '', password: '', role: 'associate' }
    await fetchUsers()
  } catch (e) {
    inviteError.value = e.response?.data?.detail || 'Failed to create user'
  } finally {
    inviteSaving.value = false
  }
}

function switchTab(id) {
  activeTab.value = id
  if (id === 'audit' && !auditRows.value.length) fetchAudit()
  if (id === 'system') fetchHealth()
}

// ── Utils ─────────────────────────────────────────────────────────────────────
function formatDate(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-US', {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
  })
}

function tierColor(tier) {
  return ['#c9a84c','#b8972a','#4a7cf7','#48bb78','#718096','#a0aec0','#718096'][tier] ?? '#718096'
}

function roleLabel(value) {
  return ROLES.find(r => r.value === value)?.label ?? value
}

onMounted(fetchUsers)
</script>

<template>
  <div class="admin">

    <!-- Header -->
    <div class="admin__header">
      <div>
        <h1 class="admin__title">Firm Administration</h1>
        <p class="admin__sub">{{ auth.firmId }} · {{ users.length }} member{{ users.length !== 1 ? 's' : '' }}</p>
      </div>
      <button class="piq-btn-gold" @click="showInvite = true">+ Invite User</button>
    </div>

    <!-- Invite Modal -->
    <div v-if="showInvite" class="modal-backdrop" @click.self="showInvite = false">
      <div class="modal">
        <h2 class="modal__title">Invite User</h2>
        <div class="modal__field">
          <label>Username</label>
          <input v-model="inviteForm.username" class="piq-input" placeholder="jane.smith" />
        </div>
        <div class="modal__field">
          <label>Email</label>
          <input v-model="inviteForm.email" class="piq-input" type="email" placeholder="jane@firm.com" />
        </div>
        <div class="modal__field">
          <label>Password</label>
          <input v-model="inviteForm.password" class="piq-input" type="password" placeholder="Min 8 characters" />
        </div>
        <div class="modal__field">
          <label>Role</label>
          <select v-model="inviteForm.role" class="piq-input">
            <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </div>
        <div class="modal__field">
          <label>Firm</label>
          <input v-model="inviteForm.firm_id" class="piq-input" placeholder="default" />
        </div>
        <div v-if="inviteError" class="modal__error">{{ inviteError }}</div>
        <div class="modal__actions">
          <button class="action-btn" @click="showInvite = false">Cancel</button>
          <button class="piq-btn-gold" :disabled="inviteSaving" @click="submitInvite">
            {{ inviteSaving ? 'Creating…' : 'Create User' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Tabs -->
    <div class="admin__tabs">
      <button
        v-for="tab in tabsWithCounts" :key="tab.id"
        :class="['admin__tab', { 'admin__tab--active': activeTab === tab.id }]"
        @click="switchTab(tab.id)"
      >
        {{ tab.label }}
        <span v-if="tab.count" class="admin__tab-badge">{{ tab.count }}</span>
      </button>
    </div>

    <!-- ── USERS ─────────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'users'" class="tab-pane">
      <div v-if="loading" class="state-msg">Loading members…</div>
      <div v-else-if="loadError" class="state-msg state-msg--error">{{ loadError }}</div>
      <template v-else>

        <div class="table-controls">
          <input v-model="search"     class="piq-input" placeholder="Search name or email…" />
          <select v-model="filterRole" class="piq-input piq-input--sm">
            <option value="">All roles</option>
            <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </div>

        <div class="piq-table-wrap">
          <table class="piq-table">
            <thead>
              <tr>
                <th>ID</th><th>User</th><th>Role</th>
                <th>Status</th><th>Last Login</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in filteredUsers" :key="user.id"
                  :class="{ 'row--inactive': !user.active }">
                <td class="dim mono">{{ user.id }}</td>
                <td>
                  <div class="user-cell">
                    <span class="user-name">{{ user.username }}</span>
                    <span class="user-email">{{ user.email }}</span>
                  </div>
                </td>
                <td>
                  <select v-model="user._role" class="role-select"
                    :disabled="!!saving[user.id]" @change="updateRole(user)">
                    <option v-for="r in ROLES" :key="r.value" :value="r.value">{{ r.label }}</option>
                  </select>
                </td>
                <td>
                  <span :class="['status-pill', user.active ? 'status-pill--on' : 'status-pill--off']">
                    {{ user.active ? 'Active' : 'Inactive' }}
                  </span>
                </td>
                <td class="dim">{{ formatDate(user.last_login) }}</td>
                <td>
                  <button class="action-btn"
                    :class="user.active ? 'action-btn--warn' : 'action-btn--ok'"
                    :disabled="!!saving[user.id] || user.id === auth.userId"
                    @click="toggleStatus(user)">
                    {{ saving[user.id] ? '…' : user.active ? 'Deactivate' : 'Activate' }}
                  </button>
                </td>
              </tr>
              <tr v-if="!filteredUsers.length">
                <td colspan="6" class="empty-row">No users match your filter.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </template>
    </div>

    <!-- ── ROLES ─────────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'roles'" class="tab-pane">
      <div class="roles-grid">
        <div v-for="role in ROLES" :key="role.value" class="role-card">
          <div class="role-card__top">
            <span class="role-card__name">{{ role.label }}</span>
            <span class="role-card__tier" :style="{ background: tierColor(role.tier) }">T{{ role.tier }}</span>
          </div>
          <p class="role-card__desc">{{ role.desc }}</p>
          <div class="role-card__footer">
            <span>{{ usersByRole[role.value] || 0 }} member{{ (usersByRole[role.value] || 0) !== 1 ? 's' : '' }}</span>
          </div>
        </div>
      </div>

      <div class="access-legend">
        <h3 class="legend-title">Access Model</h3>
        <div class="legend-row">
          <span class="legend-dot legend-dot--open"></span>
          Tiers 0–3 (Super → Associate): default open — full module access
        </div>
        <div class="legend-row">
          <span class="legend-dot legend-dot--closed"></span>
          Tiers 4–6 (Paralegal → Billing): default closed — scoped to assigned matters only
        </div>
      </div>
    </div>

    <!-- ── AUDIT LOG ──────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'audit'" class="tab-pane">
      <div v-if="auditLoading" class="state-msg">Loading audit log…</div>
      <div v-else-if="!auditRows.length" class="state-msg dim">No audit entries found.</div>
      <div v-else class="piq-table-wrap">
        <table class="piq-table">
          <thead>
            <tr><th>Time</th><th>User</th><th>Method</th><th>Path</th><th>Status</th></tr>
          </thead>
          <tbody>
            <tr v-for="(row, i) in auditRows" :key="i">
              <td class="dim mono nowrap">{{ formatDate(row.timestamp || row.created_at) }}</td>
              <td>{{ row.username || row.user_id || '—' }}</td>
              <td>
                <span :class="['method-pill', `method-pill--${(row.method||'get').toLowerCase()}`]">
                  {{ row.method || 'GET' }}
                </span>
              </td>
              <td class="dim mono small">{{ row.path }}</td>
              <td>
                <span :class="['status-pill', (row.status_code||200) < 400 ? 'status-pill--on' : 'status-pill--off']">
                  {{ row.status_code || '—' }}
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ── SYSTEM ─────────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'system'" class="tab-pane">
      <div class="sys-grid">
        <div class="sys-card">
          <div class="sys-card__label">API Status</div>
          <div class="sys-card__val" :style="{ color: health === null ? 'var(--text-muted)' : health ? '#48bb78' : '#fc8181' }">
            {{ health === null ? 'Checking…' : health ? '● Online' : '● Offline' }}
          </div>
        </div>
        <div class="sys-card">
          <div class="sys-card__label">Firm</div>
          <div class="sys-card__val mono">{{ auth.firmId }}</div>
        </div>
        <div class="sys-card">
          <div class="sys-card__label">Total Members</div>
          <div class="sys-card__val">{{ users.length }}</div>
        </div>
        <div class="sys-card">
          <div class="sys-card__label">Active Members</div>
          <div class="sys-card__val">{{ users.filter(u => u.active).length }}</div>
        </div>
        <div class="sys-card">
          <div class="sys-card__label">Your Role</div>
          <div class="sys-card__val">{{ roleLabel(auth.user?.role) }}</div>
        </div>
        <div class="sys-card">
          <div class="sys-card__label">Your Tier</div>
          <div class="sys-card__val">T{{ auth.user?.tier ?? '—' }}</div>
        </div>
      </div>
    </div>

    <!-- ── BILLING ──────────────────────────────────────────────────────── -->
    <div v-if="activeTab === 'billing'" class="tab-pane">
      <div class="billing-grid">
        <div class="plan-card plan-card--current">
          <div class="plan-card__badge">Current Plan</div>
          <h2 class="plan-card__name">Professional</h2>
          <div class="plan-card__price">$49<span>/mo per user</span></div>
          <ul class="plan-card__features">
            <li>&#x2713; Unlimited matters</li>
            <li>&#x2713; AI privilege detection</li>
            <li>&#x2713; Discovery intake pipeline</li>
            <li>&#x2713; Legal-BERT enclave</li>
            <li>&#x2713; PDF exports</li>
            <li>&#x2713; Up to 10 users</li>
          </ul>
          <div class="plan-card__firm">Firm: <span class="mono">{{ auth.firmId }}</span></div>
        </div>
        <div class="plan-card plan-card--upgrade">
          <div class="plan-card__badge plan-card__badge--gold">Enterprise</div>
          <h2 class="plan-card__name">Enterprise</h2>
          <div class="plan-card__price">Custom<span> pricing</span></div>
          <ul class="plan-card__features">
            <li>&#x2713; Everything in Professional</li>
            <li>&#x2713; Unlimited users</li>
            <li>&#x2713; Dedicated enclave VPS</li>
            <li>&#x2713; SSO / Microsoft Entra ID</li>
            <li>&#x2713; SLA + priority support</li>
          </ul>
          <button class="piq-btn-gold" style="width:100%;margin-top:1rem">Contact Sales</button>
        </div>
      </div>
      <div class="usage-section">
        <h3 class="usage-title">Usage</h3>
        <div class="usage-grid">
          <div class="usage-card">
            <div class="usage-card__label">Active Users</div>
            <div class="usage-card__bar">
              <div class="usage-card__fill" :style="{ width: (Math.min(users.filter(u=>u.active).length,10)/10*100)+'%' }"></div>
            </div>
            <div class="usage-card__val">{{ users.filter(u=>u.active).length }} / 10</div>
          </div>
        </div>
      </div>
    </div>

  </div>
</template>

<style scoped>
.admin           { padding: 2rem; max-width: 1200px; }
.admin__header   { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.5rem; }
.admin__title    { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.admin__sub      { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

/* Tabs */
.admin__tabs     { display: flex; gap: 0.25rem; border-bottom: 1px solid var(--border); margin-bottom: 1.5rem; }
.admin__tab      {
  background: none; border: none; border-bottom: 2px solid transparent;
  color: var(--text-muted); cursor: pointer; font-size: 0.875rem; padding: 0.6rem 1.1rem;
  transition: color .2s, border-color .2s; display: flex; align-items: center; gap: 0.4rem;
}
.admin__tab:hover      { color: var(--text-primary); }
.admin__tab--active    { color: var(--gold); border-bottom-color: var(--gold); }
.admin__tab-badge      {
  background: var(--border); border-radius: 20px;
  color: var(--text-muted); font-size: 0.7rem; padding: 0.1rem 0.45rem;
}

/* Tab pane */
.tab-pane { animation: fadeIn .15s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(3px); } to { opacity: 1; } }

/* Table controls */
.table-controls { display: flex; gap: 0.75rem; margin-bottom: 1rem; flex-wrap: wrap; }
.piq-input--sm  { max-width: 180px; }

/* Table */
.piq-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.piq-table      { border-collapse: collapse; font-size: 0.875rem; width: 100%; }
.piq-table th   {
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  color: var(--text-muted); font-size: 0.72rem; font-weight: 600;
  letter-spacing: 0.05em; padding: 0.65rem 1rem; text-align: left; text-transform: uppercase;
}
.piq-table td          { border-bottom: 1px solid var(--border); padding: 0.75rem 1rem; }
.piq-table tr:last-child td { border-bottom: none; }
.piq-table tr:hover td { background: rgba(255,255,255,.02); }
.row--inactive td      { opacity: 0.45; }
.empty-row             { color: var(--text-muted); padding: 2rem !important; text-align: center; }

/* User cell */
.user-cell  { display: flex; flex-direction: column; gap: 0.1rem; }
.user-name  { color: var(--text-primary); font-weight: 500; }
.user-email { color: var(--text-muted); font-size: 0.75rem; }

/* Role select */
.role-select {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 4px;
  color: var(--text-primary); cursor: pointer; font-size: 0.8rem;
  outline: none; padding: 0.3rem 0.5rem; transition: border-color .2s;
}
.role-select:hover:not(:disabled) { border-color: var(--gold); }
.role-select:disabled { cursor: not-allowed; opacity: 0.4; }

/* Pills */
.status-pill {
  border-radius: 20px; font-size: 0.72rem; font-weight: 600;
  letter-spacing: 0.04em; padding: 0.2rem 0.6rem; text-transform: uppercase;
}
.status-pill--on  { background: rgba(72,187,120,.15); color: #48bb78; }
.status-pill--off { background: rgba(252,129,129,.1);  color: #fc8181; }

.method-pill { border-radius: 3px; font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.4rem; }
.method-pill--get    { background: rgba(74,124,247,.15); color: #4a7cf7; }
.method-pill--post   { background: rgba(72,187,120,.15); color: #48bb78; }
.method-pill--put    { background: rgba(236,201,75,.15);  color: #ecc94b; }
.method-pill--delete { background: rgba(252,129,129,.1);  color: #fc8181; }

/* Action button */
.action-btn {
  background: none; border: 1px solid var(--border); border-radius: 4px;
  color: var(--text-muted); cursor: pointer; font-size: 0.78rem;
  padding: 0.3rem 0.7rem; transition: all .2s;
}
.action-btn:hover:not(:disabled)      { border-color: var(--gold); color: var(--gold); }
.action-btn:disabled                  { cursor: not-allowed; opacity: 0.3; }
.action-btn--warn:hover:not(:disabled) { border-color: #fc8181; color: #fc8181; }
.action-btn--ok:hover:not(:disabled)   { border-color: #48bb78; color: #48bb78; }

/* Roles grid */
.roles-grid { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(210px,1fr)); margin-bottom: 1.5rem; }
.role-card  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem; }
.role-card__top  { align-items: center; display: flex; justify-content: space-between; margin-bottom: 0.5rem; }
.role-card__name { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; }
.role-card__tier { border-radius: 4px; color: #000; font-size: 0.7rem; font-weight: 700; padding: 0.15rem 0.45rem; }
.role-card__desc { color: var(--text-muted); font-size: 0.8rem; line-height: 1.4; margin: 0 0 0.75rem; }
.role-card__footer { border-top: 1px solid var(--border); color: var(--text-muted); font-size: 0.78rem; padding-top: 0.5rem; }

/* Access legend */
.access-legend { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
.legend-title  { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; margin: 0 0 0.75rem; text-transform: uppercase; }
.legend-row    { align-items: center; color: var(--text-primary); display: flex; font-size: 0.85rem; gap: 0.75rem; margin-bottom: 0.5rem; }
.legend-dot    { border-radius: 50%; flex-shrink: 0; height: 10px; width: 10px; }
.legend-dot--open   { background: #48bb78; }
.legend-dot--closed { background: #fc8181; }

/* System grid */
.sys-grid    { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(170px,1fr)); }
.sys-card    { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
.sys-card__label { color: var(--text-muted); font-size: 0.72rem; letter-spacing: 0.05em; margin-bottom: 0.5rem; text-transform: uppercase; }
.sys-card__val   { color: var(--text-primary); font-size: 1.35rem; font-weight: 600; }

/* Buttons */
.piq-btn-gold {
  background: var(--gold); border: none; border-radius: 6px; color: #000;
  cursor: pointer; font-size: 0.875rem; font-weight: 600; padding: 0.55rem 1.1rem;
  transition: opacity .2s;
}
.piq-btn-gold:hover:not(:disabled) { opacity: 0.85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: 0.4; }

/* Modal */
.modal-backdrop {
  align-items: center; background: rgba(0,0,0,.85); backdrop-filter: blur(4px);
  bottom: 0; display: flex; justify-content: center; left: 0;
  position: fixed; right: 0; top: 0; z-index: 100;
}
.modal {
  background: var(--bg-surface); border: 1px solid var(--border); border-radius: 12px;
  padding: 2rem; width: 100%; max-width: 420px;
}
.modal__title  { color: var(--gold); font-family: var(--font-display); font-size: 1.3rem; margin: 0 0 1.5rem; }
.modal__field  { display: flex; flex-direction: column; gap: 0.35rem; margin-bottom: 1rem; }
.modal__field label { color: var(--text-muted); font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.05em; }
.modal__error  { color: #fc8181; font-size: 0.85rem; margin-bottom: 1rem; }
.modal__actions { display: flex; gap: 0.75rem; justify-content: flex-end; margin-top: 1.5rem; }
.dim   { color: var(--text-muted); }
.mono  { font-family: var(--font-mono); }
.small { font-size: 0.8rem; }
.nowrap { white-space: nowrap; }
.state-msg { color: var(--text-muted); padding: 2rem; text-align: center; }
.state-msg--error { color: #fc8181; }
/* Billing */
.billing-grid { display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fill, minmax(280px,1fr)); margin-bottom: 2rem; }
.plan-card    { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; padding: 1.75rem; }
.plan-card--current { border-color: var(--gold); }
.plan-card__badge    { background: var(--border); border-radius: 20px; color: var(--text-muted); display: inline-block; font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; margin-bottom: 0.75rem; padding: 0.2rem 0.65rem; text-transform: uppercase; }
.plan-card__badge--gold { background: rgba(201,168,76,.2); color: var(--gold); }
.plan-card__name  { color: var(--text-primary); font-size: 1.4rem; font-weight: 700; margin: 0 0 0.5rem; }
.plan-card__price { color: var(--gold); font-size: 1.8rem; font-weight: 700; margin-bottom: 1.25rem; }
.plan-card__price span { color: var(--text-muted); font-size: 0.85rem; font-weight: 400; }
.plan-card__features { color: var(--text-primary); font-size: 0.875rem; line-height: 1.8; list-style: none; margin: 0 0 1rem; padding: 0; }
.plan-card__firm { color: var(--text-muted); font-size: 0.8rem; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border); }
.usage-section { }
.usage-title   { color: var(--text-muted); font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; margin: 0 0 1rem; text-transform: uppercase; }
.usage-grid    { display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(240px,1fr)); }
.usage-card    { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.1rem; }
.usage-card__label { color: var(--text-muted); font-size: 0.78rem; margin-bottom: 0.6rem; }
.usage-card__bar   { background: var(--border); border-radius: 4px; height: 6px; margin-bottom: 0.4rem; overflow: hidden; }
.usage-card__fill  { background: var(--gold); border-radius: 4px; height: 100%; transition: width .5s ease; }
.usage-card__val   { color: var(--text-primary); font-size: 0.85rem; font-weight: 600; }
</style>
