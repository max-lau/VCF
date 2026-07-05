<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const enclaves   = ref([])
const status     = ref(null)
const loading    = ref(false)
const showCreate = ref(false)
const saving     = ref(false)
const testing    = ref({})

const form = ref({ client_id:'', enclave_url:'', enclave_name:'', api_key:'' })
function emptyForm() { return { client_id:'', enclave_url:'', enclave_name:'', api_key:'' } }

async function fetchStatus() {
  try {
    const { data } = await client.get('/legal-bert/status')
    status.value = data
  } catch {}
}

async function fetchEnclaves() {
  loading.value = true
  try {
    const { data } = await client.get('/privilege/admin/list-enclaves')
    enclaves.value = Array.isArray(data) ? data : (data.enclaves || [])
  } catch { enclaves.value = [] }
  finally { loading.value = false }
}

async function testEnclave(enclave) {
  testing.value = { ...testing.value, [enclave.id || enclave.client_id]: true }
  try {
    const cid = enclave.client_id
    const { data } = await client.get(`/privilege/health/${encodeURIComponent(cid)}`)
    alert(`Enclave ${enclave.enclave_name || enclave.client_id}: ${data.status || 'online'}`)
  } catch {
    alert('Could not reach enclave — check URL and network.')
  } finally {
    const t = { ...testing.value }
    delete t[enclave.id || enclave.client_id]
    testing.value = t
  }
}

async function createEnclave() {
  if (!form.value.client_id.trim() || !form.value.enclave_url.trim()) return
  saving.value = true
  try {
    await client.post('/privilege/admin/register-enclave', {
      client_id:   form.value.client_id,
      enclave_url: form.value.enclave_url,
      api_key:     form.value.api_key,
      firm_name:   form.value.enclave_name,
    })
    showCreate.value = false
    form.value = emptyForm()
    fetchEnclaves()
  } catch {
    alert('Failed to create enclave. Check the URL and try again.')
  } finally { saving.value = false }
}

async function deleteEnclave(id) {
  if (!confirm('Remove this enclave?')) return
  try {
    await client.delete(`/privilege/admin/deactivate-enclave/${id}`)
    fetchEnclaves()
  } catch {}
}

function statusColor(s) {
  return { online:'#48bb78', offline:'#fc8181', unknown:'#ecc94b', degraded:'#fc8181' }[s] || '#718096'
}

function fmtDate(d) { return d ? new Date(d).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '—' }

onMounted(() => { fetchStatus(); fetchEnclaves() })
</script>

<template>
  <div class="enc">
    <div class="enc__header">
      <div><h1 class="enc__title">Enclave Management</h1><p class="enc__sub">Per-client Legal-BERT privilege detection enclaves</p></div>
      <button class="btn-gold" @click="showCreate = true; form = emptyForm()">+ New Enclave</button>
    </div>

    <!-- Global BERT status -->
    <div v-if="status" class="status-card">
      <div class="status-card__icon">🧠</div>
      <div class="status-card__body">
        <div class="status-card__title">Legal-BERT Status</div>
        <div class="status-card__sub">
          Mode: <strong>{{ status.mode }}</strong>
          <span v-if="status.url"> · {{ status.url }}</span>
        </div>
      </div>
      <span class="status-dot" :style="{ color: status.mode === 'enclave' ? '#48bb78' : '#ecc94b' }">◉</span>
      <span class="status-label" :style="{ color: status.mode === 'enclave' ? '#48bb78' : '#ecc94b' }">
        {{ status.mode === 'enclave' ? 'Enclave Online' : 'Heuristic Mode' }}
      </span>
    </div>

    <!-- Info box when no enclaves -->
    <div class="info-box" v-if="!loading && !enclaves.length && !showCreate">
      <div class="info-box__icon">ℹ</div>
      <div class="info-box__body">
        <div class="info-box__title">About Privilege Enclaves</div>
        <div class="info-box__text">
          Each client enclave runs a dedicated Legal-BERT INT8 instance on a separate Hetzner CX21 VPS,
          providing isolated privilege detection. Data never leaves the client's enclave.
          Set <code>ENCLAVE_LEGAL_BERT_URL</code> in your .env to enable global enclave mode,
          or register per-client enclaves below.
        </div>
      </div>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="enclaves.length" class="enclave-list">
      <div class="section-title">Registered Enclaves</div>
      <div v-for="e in enclaves" :key="e.id || e.client_id" class="enclave-card">
        <div class="enclave-card__icon">🔒</div>
        <div class="enclave-card__body">
          <div class="enclave-name">{{ e.enclave_name || e.client_id }}</div>
          <div class="enclave-meta">
            <span class="dim sm mono">{{ e.enclave_url || e.url }}</span>
            <span v-if="e.client_id" class="dim sm">Client: {{ e.client_id }}</span>
            <span v-if="e.created_at" class="dim sm">Added {{ fmtDate(e.created_at) }}</span>
          </div>
        </div>
        <div class="enclave-card__actions">
          <span v-if="e.status" class="status-pill" :style="{ background: statusColor(e.status)+'22', color: statusColor(e.status) }">
            ◉ {{ e.status }}
          </span>
          <button class="btn-secondary sm" @click="testEnclave(e)" :disabled="testing[e.id || e.client_id]">
            {{ testing[e.id || e.client_id] ? 'Testing…' : 'Test' }}
          </button>
          <button class="icon-btn del" @click="deleteEnclave(e.id || e.client_id)">✕</button>
        </div>
      </div>
    </div>

    <!-- Env var reference -->
    <div class="env-section">
      <div class="section-title">Environment Configuration</div>
      <div class="env-card">
        <div class="env-row">
          <span class="env-key">ENCLAVE_LEGAL_BERT_URL</span>
          <span class="dim sm">Global enclave endpoint (overrides heuristic for all clients)</span>
        </div>
        <div class="env-row">
          <span class="env-key">PARAIQ_ADMIN_KEY</span>
          <span class="dim sm">Admin API key for enclave provisioning endpoints</span>
        </div>
      </div>
      <div class="env-hint dim sm">Edit in <code>/root/nlp-portfolio/backend/demo1/.env</code> then run <code>pm2 restart paraiq-api --update-env</code></div>
    </div>

    <!-- Create modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal__header">
          <h2>Register Enclave</h2>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal__body">
          <div class="field">
            <label>Client ID *</label>
            <input v-model="form.client_id" placeholder="acme-corp (unique identifier)" />
          </div>
          <div class="field">
            <label>Enclave Name</label>
            <input v-model="form.enclave_name" placeholder="Acme Corp Legal-BERT" />
          </div>
          <div class="field">
            <label>Enclave URL *</label>
            <input v-model="form.enclave_url" placeholder="https://enclave-acme.yourdomain.com" />
          </div>
          <div class="field">
            <label>API Key</label>
            <input type="password" v-model="form.api_key" placeholder="Optional API key for this enclave" />
          </div>
          <div class="info-hint dim sm">
            The enclave VPS must be running the ParaIQ privilege-enclave Docker container and reachable from this server.
          </div>
        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showCreate = false">Cancel</button>
          <button class="btn-gold" @click="createEnclave" :disabled="saving || !form.client_id.trim() || !form.enclave_url.trim()">
            {{ saving ? 'Registering…' : 'Register Enclave' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.enc { padding: 2rem; max-width: 900px; }
.enc__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.enc__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.enc__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.status-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: center; gap: 1rem; margin-bottom: 1.25rem; padding: 1rem 1.25rem; }
.status-card__icon { font-size: 1.5rem; }
.status-card__body { flex: 1; }
.status-card__title { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; }
.status-card__sub   { color: var(--text-muted); font-size: 0.8rem; margin-top: 0.2rem; }
.status-dot  { font-size: 0.7rem; }
.status-label { font-size: 0.78rem; font-weight: 700; }

.info-box { background: rgba(201,168,76,.07); border: 1px solid rgba(201,168,76,.25); border-radius: 8px; display: flex; gap: 1rem; margin-bottom: 1.5rem; padding: 1.25rem; }
.info-box__icon  { color: var(--gold); font-size: 1.25rem; flex-shrink: 0; }
.info-box__title { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; margin-bottom: 0.4rem; }
.info-box__text  { color: var(--text-muted); font-size: 0.83rem; line-height: 1.6; }
.info-box__text code { background: rgba(255,255,255,.07); border-radius: 3px; font-family: var(--font-mono); font-size: 0.8rem; padding: 0.1rem 0.35rem; }

.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 0.75rem; text-transform: uppercase; }

.enclave-list { margin-bottom: 2rem; }
.enclave-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: center; gap: 1rem; margin-bottom: 0.6rem; padding: 1rem 1.25rem; transition: border-color .15s; }
.enclave-card:hover { border-color: var(--gold); }
.enclave-card__icon { font-size: 1.5rem; flex-shrink: 0; }
.enclave-card__body { flex: 1; min-width: 0; }
.enclave-card__actions { display: flex; align-items: center; gap: 0.5rem; flex-shrink: 0; }
.enclave-name { color: var(--text-primary); font-size: 0.9rem; font-weight: 600; margin-bottom: 0.25rem; }
.enclave-meta { display: flex; gap: 1rem; flex-wrap: wrap; }
.status-pill  { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.45rem; }

.env-section { }
.env-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 0.75rem; overflow: hidden; }
.env-row  { align-items: flex-start; border-bottom: 1px solid var(--border); display: flex; gap: 1.5rem; padding: 0.75rem 1.1rem; }
.env-row:last-child { border-bottom: none; }
.env-key  { background: rgba(201,168,76,.1); border-radius: 4px; color: var(--gold); font-family: var(--font-mono); font-size: 0.78rem; font-weight: 600; padding: 0.1rem 0.45rem; white-space: nowrap; }
.env-hint { margin-top: 0.4rem; }
.env-hint code { background: rgba(255,255,255,.07); border-radius: 3px; font-family: var(--font-mono); font-size: 0.78rem; padding: 0.1rem 0.35rem; }
.info-hint { line-height: 1.5; }

.btn-gold     { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover:not(:disabled) { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary:disabled { opacity: .4; cursor: not-allowed; }
.btn-secondary.sm { font-size: 0.75rem; padding: 0.35rem 0.75rem; }
.icon-btn    { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.15rem 0.3rem; }
.icon-btn.del:hover { color: #fc8181; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 520px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 0.85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }
.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; padding: 0.5rem 0.75rem; outline: none; font-family: inherit; }
.field input:focus { border-color: var(--gold); }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.mono { font-family: var(--font-mono); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
