<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }
const token   = () => localStorage.getItem('paraiq_token')
const authHdr = () => ({ Authorization: 'Bearer ' + token() })

const matters   = ref([])
const accesses  = ref([])
const selected  = ref(null)
const showGrant = ref(false)
const saving    = ref(false)
const copied    = ref(null)

const PERM_OPTIONS = ['timeline', 'documents', 'correspondence', 'contacts']

const form = ref({
  client_name: '',
  client_email: '',
  permissions: 'timeline,documents,correspondence',
  expires_days: 30,
})

async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
    if (matters.value.length) { selected.value = matters.value[0]; fetchAccesses() }
  } catch {}
}

async function fetchAccesses() {
  if (!selected.value) return
  try {
    const { data } = await client.get('/client-portal/matter/' + selected.value.id + '/accesses')
    accesses.value = data
  } catch { accesses.value = [] }
}

async function grantAccess() {
  if (!form.value.client_name.trim() || !form.value.client_email.trim()) return
  saving.value = true
  try {
    await client.post('/client-portal/grant', {
      ...form.value,
      matter_id: selected.value.id,
      firm_id: firmId(),
    }, { headers: authHdr() })
    showGrant.value = false
    form.value = { client_name: '', client_email: '', permissions: 'timeline,documents,correspondence', expires_days: 30 }
    fetchAccesses()
  } catch {} finally { saving.value = false }
}

async function revokeAccess(id) {
  if (!confirm('Revoke this portal access?')) return
  await client.delete('/client-portal/access/' + id)
  fetchAccesses()
}

function copyLink(access) {
  const url = window.location.origin + '/client-portal/view/' + access.access_token
  navigator.clipboard.writeText(url)
  copied.value = access.id
  setTimeout(() => { copied.value = null }, 2000)
}

function hasPerm(perm) {
  return form.value.permissions.split(',').includes(perm)
}

function togglePerm(perm) {
  const perms = form.value.permissions.split(',').filter(Boolean)
  const idx = perms.indexOf(perm)
  if (idx >= 0) perms.splice(idx, 1); else perms.push(perm)
  form.value.permissions = perms.join(',')
}

function fmtDate(d) {
  return d ? new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : '—'
}

function isExpired(d) { return d && new Date(d) < new Date() }

onMounted(fetchMatters)
</script>

<template>
  <div class="portal">
    <div class="portal__header">
      <div>
        <h1 class="portal__title">Client Portal</h1>
        <p class="portal__sub">Share secure read-only matter views with clients</p>
      </div>
      <button class="btn-gold" @click="showGrant = true" :disabled="!selected">+ Grant Access</button>
    </div>

    <div class="matter-bar">
      <label class="bar-label">Matter</label>
      <select class="bar-select" v-model="selected" @change="fetchAccesses">
        <option v-for="m in matters" :key="m.id" :value="m">{{ m.case_number }} — {{ m.client_name }}</option>
      </select>
    </div>

    <div v-if="!accesses.length" class="empty">
      <div class="empty__icon">🔗</div>
      <div class="empty__title">No portal links yet</div>
      <div class="empty__sub">Grant clients secure read-only access to their matter.</div>
      <button class="btn-gold mt" @click="showGrant = true">+ Grant First Access</button>
    </div>

    <div v-else class="access-list">
      <div v-for="a in accesses" :key="a.id" class="access-card"
           :class="{ expired: !a.is_active || isExpired(a.expires_at) }">
        <div class="access-card__avatar">{{ a.client_name?.charAt(0)?.toUpperCase() }}</div>
        <div class="access-card__body">
          <div class="access-name">{{ a.client_name }}</div>
          <div class="dim sm">{{ a.client_email }}</div>
          <div class="access-meta">
            <span class="dim sm mono">{{ a.permissions?.replace(/,/g,' · ') }}</span>
            <span v-if="a.expires_at" class="dim sm">Expires {{ fmtDate(a.expires_at) }}</span>
            <span v-if="a.last_accessed" class="dim sm">Last viewed {{ fmtDate(a.last_accessed) }}</span>
          </div>
        </div>
        <div class="access-card__actions">
          <span v-if="!a.is_active || isExpired(a.expires_at)" class="expired-badge">Expired</span>
          <span v-else class="active-badge">Active</span>
          <button class="btn-secondary sm" @click="copyLink(a)">
            {{ copied === a.id ? '✓ Copied' : 'Copy Link' }}
          </button>
          <button class="icon-btn del" @click="revokeAccess(a.id)">✕</button>
        </div>
      </div>
    </div>

    <!-- Grant modal -->
    <div v-if="showGrant" class="modal-overlay" @click.self="showGrant = false">
      <div class="modal">
        <div class="modal__header">
          <h2>Grant Portal Access</h2>
          <button class="close-btn" @click="showGrant = false">✕</button>
        </div>
        <div class="modal__body">
          <div class="field">
            <label>Client Name *</label>
            <input v-model="form.client_name" placeholder="Jane Smith" />
          </div>
          <div class="field">
            <label>Client Email *</label>
            <input type="email" v-model="form.client_email" placeholder="jane@example.com" />
          </div>
          <div class="field">
            <label>Permissions</label>
            <div class="perm-toggles">
              <span v-for="p in PERM_OPTIONS" :key="p"
                class="perm-toggle" :class="{ active: hasPerm(p) }"
                @click="togglePerm(p)">{{ p }}</span>
            </div>
          </div>
          <div class="field">
            <label>Expires in (days)</label>
            <select v-model="form.expires_days">
              <option v-for="d in [7,14,30,60,90]" :key="d" :value="d">{{ d }} days</option>
            </select>
          </div>
        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showGrant = false">Cancel</button>
          <button class="btn-gold" @click="grantAccess"
            :disabled="saving || !form.client_name.trim() || !form.client_email.trim()">
            {{ saving ? 'Granting…' : 'Grant Access' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.portal { padding: 2rem; max-width: 860px; }
.portal__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.portal__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.portal__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.matter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.5rem; }
.bar-label  { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 340px; }

.access-list { display: flex; flex-direction: column; gap: 0.6rem; }
.access-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: center; gap: 1rem; padding: 1rem 1.25rem; transition: border-color .15s; }
.access-card:hover { border-color: var(--gold); }
.access-card.expired { opacity: .55; }
.access-card__avatar { align-items: center; background: rgba(201,168,76,.2); border-radius: 50%; color: var(--gold); display: flex; font-size: 1rem; font-weight: 700; height: 38px; justify-content: center; width: 38px; flex-shrink: 0; }
.access-card__body { flex: 1; min-width: 0; }
.access-card__actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
.access-name { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; }
.access-meta { display: flex; gap: 1rem; margin-top: 0.3rem; flex-wrap: wrap; }
.active-badge  { background: rgba(72,187,120,.15); border-radius: 4px; color: #48bb78; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; }
.expired-badge { background: rgba(113,128,150,.15); border-radius: 4px; color: #718096; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; }

.perm-toggles { display: flex; gap: 0.5rem; flex-wrap: wrap; }
.perm-toggle  { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: 0.78rem; font-weight: 600; padding: 0.25rem 0.65rem; text-transform: capitalize; transition: all .15s; user-select: none; }
.perm-toggle.active { background: rgba(201,168,76,.15); border-color: var(--gold); color: var(--gold); }

.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.mt { margin-top: 1.25rem; }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.8rem; padding: 0.4rem 0.85rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary.sm { font-size: 0.75rem; padding: 0.35rem 0.75rem; }
.icon-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.15rem 0.3rem; }
.icon-btn.del:hover { color: #fc8181; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 480px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 0.85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; padding: 0.5rem 0.75rem; outline: none; font-family: inherit; }
.field input:focus, .field select:focus { border-color: var(--gold); }
.mono { font-family: var(--font-mono); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
