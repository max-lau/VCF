<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import { useRouter } from 'vue-router'

const router = useRouter()

const requests   = ref([])
const loading    = ref(false)
const showCreate = ref(false)
const saving     = ref(false)
const error      = ref(null)
const filterStatus = ref('')
const detailReq  = ref(null)
const detailLoading = ref(false)

const form = ref(emptyForm())
function emptyForm() {
  return {
    document_name: '',
    document_text: '',
    case_id: null,
    subject: '',
    message: '',
    signers: [{ name: '', email: '', role: 'signer' }],
    expires_days: 30,
  }
}

function addSigner() {
  form.value.signers.push({ name: '', email: '', role: 'signer' })
}
function removeSigner(i) {
  if (form.value.signers.length > 1) form.value.signers.splice(i, 1)
}

async function fetchRequests() {
  loading.value = true
  error.value = null
  try {
    const params = {}
    if (filterStatus.value) params.status = filterStatus.value
    const { data } = await client.get('/esign/requests', { params })
    requests.value = data.requests || []
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load'
  } finally {
    loading.value = false
  }
}

async function sendRequest() {
  if (!form.value.document_name.trim() || !form.value.signers[0].name) return
  saving.value = true
  error.value = null
  try {
    const { data } = await client.post('/esign/send', form.value)
    showCreate.value = false
    form.value = emptyForm()
    await fetchRequests()
    // Show result with signing URLs
    if (data.signers?.length) {
      detailReq.value = data
    }
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to send'
  } finally {
    saving.value = false
  }
}

async function viewDetail(id) {
  detailLoading.value = true
  detailReq.value = null
  try {
    const { data } = await client.get(`/esign/requests/${id}`)
    detailReq.value = data
  } catch (e) {
    error.value = 'Failed to load details'
  } finally {
    detailLoading.value = false
  }
}

async function cancelRequest(id) {
  if (!confirm('Cancel this signature request?')) return
  try {
    await client.post(`/esign/cancel/${id}`)
    await fetchRequests()
    detailReq.value = null
  } catch {}
}

function copyUrl(url) {
  navigator.clipboard.writeText(url)
}

function statusColor(s) {
  return { pending:'#ecc94b', sent:'#4a7cf7', completed:'#48bb78', cancelled:'#718096', expired:'#fc8181' }[s] || '#718096'
}
function statusIcon(s) {
  return { pending:'⏳', sent:'📤', completed:'✓', cancelled:'✕', expired:'⏰' }[s] || '○'
}
function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric', hour:'2-digit', minute:'2-digit' })
}

onMounted(fetchRequests)
</script>

<template>
  <div class="esign">
    <!-- Header -->
    <div class="esign__header">
      <div>
        <h1 class="esign__title">E-Signatures</h1>
        <p class="esign__sub">Send documents for signature · track status · manage signing workflows</p>
      </div>
      <button class="btn-gold" @click="showCreate = true; form = emptyForm()">+ New Request</button>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <select v-model="filterStatus" @change="fetchRequests" class="filter-select">
        <option value="">All statuses</option>
        <option value="pending">Pending</option>
        <option value="sent">Sent</option>
        <option value="completed">Completed</option>
        <option value="cancelled">Cancelled</option>
      </select>
      <button class="btn-secondary sm" @click="fetchRequests">↻ Refresh</button>
    </div>

    <!-- Error -->
    <div v-if="error" class="error-banner">⚠ {{ error }}</div>

    <!-- Loading -->
    <div v-if="loading" class="state-msg">Loading requests…</div>

    <!-- Empty -->
    <div v-else-if="!requests.length" class="empty-state">
      <div class="empty-icon">✍️</div>
      <div class="empty-title">No signature requests yet</div>
      <div class="empty-sub">Send documents to clients and opposing counsel for electronic signature.</div>
      <button class="btn-gold mt" @click="showCreate = true; form = emptyForm()">+ Create Request</button>
    </div>

    <!-- Request list -->
    <div v-else class="req-list">
      <div v-for="r in requests" :key="r.id" class="req-card" @click="viewDetail(r.id)">
        <div class="req-card__left">
          <span class="req-icon">{{ statusIcon(r.status) }}</span>
        </div>
        <div class="req-card__body">
          <div class="req-card__top">
            <span class="req-doc">{{ r.document_name }}</span>
            <span class="req-status" :style="{ color: statusColor(r.status) }">{{ r.status }}</span>
          </div>
          <div class="req-card__meta">
            <span class="dim">{{ r.signed_count || 0 }}/{{ r.total_signers || 0 }} signed</span>
            <span class="dim">· {{ r.provider }}</span>
            <span v-if="r.case_id" class="dim">· Case #{{ r.case_id }}</span>
            <span class="dim">· {{ fmtDate(r.created_at) }}</span>
          </div>
        </div>
        <div class="req-card__progress">
          <div class="progress-bar">
            <div class="progress-fill" :style="{ width: (r.total_signers ? ((r.signed_count || 0) / r.total_signers * 100) : 0) + '%', background: statusColor(r.status) }"></div>
          </div>
        </div>
      </div>
    </div>

    <!-- Detail panel -->
    <Teleport to="body">
      <div v-if="detailReq" class="modal-overlay" @click.self="detailReq = null">
        <div class="modal">
          <div class="modal__header">
            <h2>Signature Request #{{ detailReq.request_id || detailReq.id }}</h2>
            <button class="close-btn" @click="detailReq = null">✕</button>
          </div>
          <div class="modal__body">
            <div class="detail-section">
              <div class="detail-label">Document</div>
              <div class="detail-value">{{ detailReq.document_name }}</div>
            </div>
            <div class="detail-section">
              <div class="detail-label">Status</div>
              <div class="detail-value" :style="{ color: statusColor(detailReq.status) }">{{ statusIcon(detailReq.status) }} {{ detailReq.status }}</div>
            </div>
            <div v-if="detailReq.subject" class="detail-section">
              <div class="detail-label">Subject</div>
              <div class="detail-value">{{ detailReq.subject }}</div>
            </div>

            <!-- Signers -->
            <div class="detail-section">
              <div class="detail-label">Signers</div>
              <div v-if="detailLoading" class="dim">Loading…</div>
              <div v-else class="signer-list">
                <div v-for="s in (detailReq.signers || detailReq.signers || [])" :key="s.id || s.email" class="signer-row">
                  <div class="signer-info">
                    <span class="signer-name">{{ s.name }}</span>
                    <span class="signer-email dim">{{ s.email }}</span>
                  </div>
                  <div class="signer-actions">
                    <span class="signer-status" :style="{ color: s.status === 'signed' ? '#48bb78' : '#ecc94b' }">
                      {{ s.status === 'signed' ? '✓ Signed' : '⏳ Pending' }}
                    </span>
                    <span v-if="s.signed_at" class="dim signer-date">{{ fmtDate(s.signed_at) }}</span>
                    <button v-if="s.url && s.status !== 'signed'" class="btn-secondary sm" @click="copyUrl(s.url)">Copy Link</button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Signing URLs (email fallback) -->
            <div v-if="detailReq.signers?.length && detailReq.signers[0]?.url" class="detail-section">
              <div class="detail-label">Signing Links (Email Fallback)</div>
              <div class="url-hint">Share these URLs with each signer. Configure DocuSign for automatic email delivery.</div>
              <div v-for="s in detailReq.signers" :key="s.url" class="url-row">
                <span class="url-name">{{ s.name }} ({{ s.email }})</span>
                <input :value="s.url" readonly class="url-input" @click="$event.target.select()" />
                <button class="btn-gold sm" @click="copyUrl(s.url)">Copy</button>
              </div>
            </div>
          </div>
          <div class="modal__footer">
            <button v-if="detailReq.status === 'pending' || detailReq.status === 'sent'" class="btn-secondary" @click="cancelRequest(detailReq.request_id || detailReq.id)">Cancel Request</button>
            <button class="btn-gold" @click="detailReq = null">Close</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Create modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
        <div class="modal">
          <div class="modal__header">
            <h2>New Signature Request</h2>
            <button class="close-btn" @click="showCreate = false">✕</button>
          </div>
          <div class="modal__body">
            <div class="field"><label>Document Name *</label><input v-model="form.document_name" placeholder="Settlement Agreement.pdf" /></div>
            <div class="field"><label>Subject</label><input v-model="form.subject" placeholder="Please sign this document" /></div>
            <div class="field"><label>Message</label><textarea v-model="form.message" rows="2" placeholder="Optional message to signers…"></textarea></div>
            <div class="field"><label>Document Text (optional)</label><textarea v-model="form.document_text" rows="4" placeholder="Paste document content for email-based signing…"></textarea></div>
            <div class="field-row">
              <div class="field"><label>Case ID (optional)</label><input type="number" v-model="form.case_id" /></div>
              <div class="field"><label>Expires (days)</label><input type="number" v-model="form.expires_days" min="1" max="90" /></div>
            </div>

            <div class="signers-section">
              <div class="signers-header">
                <label>Signers</label>
                <button class="btn-secondary sm" @click="addSigner">+ Add</button>
              </div>
              <div v-for="(s, i) in form.signers" :key="i" class="signer-form-row">
                <input v-model="s.name" placeholder="Full name" class="signer-input" />
                <input v-model="s.email" type="email" placeholder="email@example.com" class="signer-input" />
                <select v-model="s.role" class="signer-select">
                  <option value="signer">Signer</option>
                  <option value="cc">CC</option>
                  <option value="approver">Approver</option>
                </select>
                <button v-if="form.signers.length > 1" class="btn-secondary sm" @click="removeSigner(i)">✕</button>
              </div>
            </div>
          </div>
          <div class="modal__footer">
            <button class="btn-secondary" @click="showCreate = false">Cancel</button>
            <button class="btn-gold" @click="sendRequest" :disabled="saving || !form.document_name.trim() || !form.signers[0].name">
              {{ saving ? 'Sending…' : 'Send for Signature' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.esign { padding: 2rem; max-width: 900px; }
.esign__header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1.25rem; }
.esign__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.esign__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.filter-bar { display: flex; gap: .75rem; margin-bottom: 1.25rem; }
.filter-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .85rem; padding: .4rem .75rem; }

.error-banner { background: rgba(252,129,129,.1); border: 1px solid rgba(252,129,129,.3); border-radius: 8px; color: #fc8181; font-size: .85rem; padding: .6rem 1rem; margin-bottom: 1rem; }
.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim { color: var(--text-muted); }

.empty-state { text-align: center; padding: 3rem 1rem; }
.empty-icon { font-size: 2.5rem; opacity: .3; margin-bottom: .75rem; }
.empty-title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty-sub { color: var(--text-muted); font-size: .85rem; margin-top: .3rem; max-width: 400px; margin-left: auto; margin-right: auto; }
.mt { margin-top: 1rem; }

.req-list { display: flex; flex-direction: column; gap: .5rem; }
.req-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: center; gap: 1rem; padding: .85rem 1rem; cursor: pointer; transition: border-color .15s; }
.req-card:hover { border-color: var(--gold); }
.req-card__left { font-size: 1.3rem; width: 32px; text-align: center; flex-shrink: 0; }
.req-card__body { flex: 1; min-width: 0; }
.req-card__top { display: flex; justify-content: space-between; align-items: center; margin-bottom: .2rem; }
.req-doc { font-size: .9rem; font-weight: 600; color: var(--text-primary); }
.req-status { font-size: .75rem; font-weight: 600; text-transform: capitalize; }
.req-card__meta { display: flex; gap: .5rem; font-size: .75rem; flex-wrap: wrap; }
.req-card__progress { width: 80px; flex-shrink: 0; }
.progress-bar { height: 5px; background: rgba(255,255,255,.07); border-radius: 3px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 3px; transition: width .3s; }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: .8rem; font-weight: 700; padding: .5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .4; cursor: not-allowed; }
.btn-gold.sm { padding: .3rem .6rem; font-size: .72rem; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: .85rem; padding: .5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }
.btn-secondary.sm { padding: .3rem .6rem; font-size: .72rem; }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 580px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: .85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: .75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }

.field { display: flex; flex-direction: column; gap: .25rem; }
.field label { font-size: .7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field textarea, .field select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .875rem; padding: .5rem .75rem; outline: none; font-family: inherit; }
.field input:focus, .field textarea:focus { border-color: var(--gold); }
.field textarea { resize: vertical; }
.field-row { display: flex; gap: .75rem; }

.detail-section { display: flex; flex-direction: column; gap: .2rem; }
.detail-label { font-size: .68rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; }
.detail-value { font-size: .9rem; color: var(--text-primary); }

.signer-list { display: flex; flex-direction: column; gap: .5rem; margin-top: .3rem; }
.signer-row { display: flex; justify-content: space-between; align-items: center; background: var(--bg-raised); border-radius: 6px; padding: .5rem .75rem; }
.signer-name { font-size: .85rem; font-weight: 600; color: var(--text-primary); }
.signer-email { font-size: .75rem; }
.signer-actions { display: flex; align-items: center; gap: .5rem; }
.signer-status { font-size: .75rem; font-weight: 600; }
.signer-date { font-size: .7rem; }

.url-hint { font-size: .72rem; color: var(--text-muted); font-style: italic; margin-bottom: .4rem; }
.url-row { display: flex; align-items: center; gap: .5rem; margin-bottom: .4rem; }
.url-name { font-size: .75rem; color: var(--text-muted); min-width: 140px; }
.url-input { flex: 1; background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); font-size: .7rem; font-family: var(--font-mono); padding: .25rem .4rem; }

.signers-section { border: 1px solid var(--border); border-radius: 8px; padding: .75rem; }
.signers-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: .5rem; }
.signers-header label { font-size: .7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.signer-form-row { display: flex; gap: .4rem; margin-bottom: .4rem; }
.signer-input { flex: 1; background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: .8rem; padding: .35rem .5rem; }
.signer-select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 4px; color: var(--text-primary); font-size: .8rem; padding: .35rem .4rem; }
</style>
