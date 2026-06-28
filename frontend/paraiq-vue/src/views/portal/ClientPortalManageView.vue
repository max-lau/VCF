<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const grants      = ref([])
const loading     = ref(false)
const showCreate  = ref(false)
const saving      = ref(false)
const error       = ref(null)
const cases       = ref([])

const form = ref({ case_id: null, client_name: '', client_email: '', expires_days: 30 })
const newGrant = ref(null)

async function fetchGrants() {
  loading.value = true
  error.value = null
  try {
    const { data } = await client.get('/client-portal/grants')
    grants.value = data.grants || []
  } catch { grants.value = [] }
  finally { loading.value = false }
}

async function fetchCases() {
  try {
    const { data } = await client.get('/cases/search?q=')
    cases.value = data.cases || []
  } catch { cases.value = [] }
}

async function createGrant() {
  if (!form.value.case_id || !form.value.client_name) return
  saving.value = true
  try {
    const { data } = await client.post('/client-portal/grant', form.value)
    newGrant.value = data
    showCreate.value = false
    form.value = { case_id: null, client_name: '', client_email: '', expires_days: 30 }
    await fetchGrants()
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to create'
  } finally { saving.value = false }
}

async function revokeGrant(token) {
  if (!confirm('Revoke client portal access?')) return
  try {
    await client.delete(`/client-portal/revoke/${token}`)
    await fetchGrants()
  } catch {}
}

function copyUrl(url) {
  navigator.clipboard.writeText(url)
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function statusColor(s) {
  return { active: '#48bb78', expired: '#fc8181', revoked: '#718096' }[s] || '#718096'
}

onMounted(() => { fetchGrants(); fetchCases() })
</script>

<template>
  <div class="portal">
    <div class="portal__header">
      <div>
        <h1 class="portal__title">Client Portal</h1>
        <p class="portal__sub">Grant clients secure access to case status, documents, and messaging</p>
      </div>
      <button class="btn-gold" @click="showCreate = true; newGrant = null">+ Grant Access</button>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!grants.length" class="empty-state">
      <div class="empty-icon">🔐</div>
      <div class="empty-title">No client portal access granted</div>
      <div class="empty-sub">Grant clients secure access to view their case status, upload documents, and message your firm.</div>
      <button class="btn-gold mt" @click="showCreate = true">+ Grant Access</button>
    </div>

    <div v-else class="grant-list">
      <div v-for="g in grants" :key="g.token" class="grant-card">
        <div class="grant-card__body">
          <div class="grant-card__top">
            <span class="grant-name">{{ g.client_name }}</span>
            <span class="grant-status" :style="{ color: statusColor(g.status) }">● {{ g.status }}</span>
          </div>
          <div class="grant-card__meta">
            <span class="dim">{{ g.client_email || '—' }}</span>
            <span v-if="g.case_number" class="dim">· {{ g.case_number }}</span>
            <span class="dim">· Expires {{ fmtDate(g.expires_at) }}</span>
            <span class="dim">· Created {{ fmtDate(g.created_at) }}</span>
          </div>
        </div>
        <div class="grant-card__actions">
          <button class="btn-secondary sm" @click="copyUrl(g.portal_url || `/client-portal/view/${g.token}`)">Copy Link</button>
          <button v-if="g.status === 'active'" class="btn-secondary sm" @click="revokeGrant(g.token)">Revoke</button>
        </div>
      </div>
    </div>

    <!-- New grant result -->
    <Teleport to="body">
      <div v-if="newGrant" class="modal-overlay" @click.self="newGrant = null">
        <div class="modal">
          <div class="modal__header">
            <h2>✓ Portal Access Granted</h2>
            <button class="close-btn" @click="newGrant = null">✕</button>
          </div>
          <div class="modal__body">
            <p class="success-msg">Share this secure link with {{ newGrant.client_name }}:</p>
            <div class="url-box">
              <input :value="newGrant.portal_url" readonly class="url-input" @click="$event.target.select()" />
              <button class="btn-gold sm" @click="copyUrl(newGrant.portal_url)">Copy</button>
            </div>
            <p class="hint">The link expires in {{ form.expires_days || 30 }} days. The client can view case status, upload documents, and send messages without an account.</p>
          </div>
          <div class="modal__footer">
            <button class="btn-gold" @click="newGrant = null">Done</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Create modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
        <div class="modal">
          <div class="modal__header">
            <h2>Grant Portal Access</h2>
            <button class="close-btn" @click="showCreate = false">✕</button>
          </div>
          <div class="modal__body">
            <div class="field">
              <label>Case *</label>
              <select v-model="form.case_id">
                <option :value="null">Select a case…</option>
                <option v-for="c in cases" :key="c.id" :value="c.id">{{ c.case_number }} — {{ c.client_name }}</option>
              </select>
            </div>
            <div class="field"><label>Client Name *</label><input v-model="form.client_name" placeholder="John Smith" /></div>
            <div class="field"><label>Client Email</label><input v-model="form.client_email" type="email" placeholder="john@example.com" /></div>
            <div class="field"><label>Expires (days)</label><input type="number" v-model="form.expires_days" min="1" max="365" /></div>
          </div>
          <div class="modal__footer">
            <button class="btn-secondary" @click="showCreate = false">Cancel</button>
            <button class="btn-gold" @click="createGrant" :disabled="saving || !form.case_id || !form.client_name">
              {{ saving ? 'Creating…' : 'Grant Access' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.portal { padding: 2rem; max-width: 900px; }
.portal__header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.25rem; }
.portal__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.portal__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim { color: var(--text-muted); }

.empty-state { text-align: center; padding: 3rem 1rem; }
.empty-icon { font-size: 2.5rem; opacity: .3; margin-bottom: .75rem; }
.empty-title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty-sub { color: var(--text-muted); font-size: .85rem; margin-top: .3rem; max-width: 420px; margin-left: auto; margin-right: auto; }
.mt { margin-top: 1rem; }

.grant-list { display: flex; flex-direction: column; gap: .5rem; }
.grant-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; justify-content: space-between; align-items: center; padding: .85rem 1rem; transition: border-color .15s; }
.grant-card:hover { border-color: var(--gold); }
.grant-card__body { flex: 1; min-width: 0; }
.grant-card__top { display: flex; justify-content: space-between; align-items: center; margin-bottom: .2rem; }
.grant-name { font-size: .9rem; font-weight: 600; color: var(--text-primary); }
.grant-status { font-size: .75rem; font-weight: 600; }
.grant-card__meta { display: flex; gap: .5rem; font-size: .75rem; flex-wrap: wrap; }
.grant-card__actions { display: flex; gap: .4rem; flex-shrink: 0; }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: .8rem; font-weight: 700; padding: .5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .4; cursor: not-allowed; }
.btn-gold.sm { padding: .3rem .6rem; font-size: .72rem; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .85rem; padding: .5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary.sm { padding: .3rem .6rem; font-size: .72rem; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 500px; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: .85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: .75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }

.field { display: flex; flex-direction: column; gap: .25rem; }
.field label { font-size: .7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .875rem; padding: .5rem .75rem; outline: none; font-family: inherit; }
.field input:focus, .field select:focus { border-color: var(--gold); }

.success-msg { color: #48bb78; font-size: .9rem; margin: 0; }
.url-box { display: flex; gap: .5rem; align-items: center; }
.url-input { flex: 1; background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); font-size: .75rem; font-family: var(--font-mono); padding: .4rem .5rem; }
.hint { color: var(--text-muted); font-size: .78rem; line-height: 1.5; }
</style>
