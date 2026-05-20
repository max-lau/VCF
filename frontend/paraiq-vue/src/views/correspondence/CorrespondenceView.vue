<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import client from '@/api/client'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'

const firmId = () => {
  try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id || 'default' }
  catch { return 'default' }
}

const matters        = ref([])
const items          = ref([])
const selectedMatter = ref(null)
const loading        = ref(false)
const showCreate     = ref(false)
const saving         = ref(false)
const filterDir      = ref('')
const filterType     = ref('')
const expanded       = ref(null)

// ── Upload state ───────────────────────────────────────────────────────────
const showUpload = ref(false)

const form     = ref({ subject:'', type:'email', direction:'outbound', from_party:'', to_party:'', cc_party:'', date:'', body:'', status:'sent' })
const emptyForm = () => ({ subject:'', type:'email', direction:'outbound', from_party:'', to_party:'', cc_party:'', date:'', body:'', status:'sent' })

// ── Data fetching ──────────────────────────────────────────────────────────
async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
    if (matters.value.length) selectedMatter.value = matters.value[0]
  } catch {}
}

async function fetchItems() {
  if (!selectedMatter.value) return
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filterDir.value)  params.set('direction', filterDir.value)
    if (filterType.value) params.set('type', filterType.value)
    const { data } = await client.get(`/correspondence/${selectedMatter.value.id}?${params}`)
    items.value = data
  } catch { items.value = [] }
  finally { loading.value = false }
}

watch(selectedMatter, fetchItems)
watch([filterDir, filterType], fetchItems)
onMounted(() => fetchMatters().then(fetchItems))

// ── Save ───────────────────────────────────────────────────────────────────
async function saveItem() {
  if (!form.value.subject.trim()) return
  saving.value = true
  try {
    // client already carries auth headers via interceptor — no authHdr needed
    await client.post('/correspondence/', {
      ...form.value,
      matter_id: selectedMatter.value?.id,
      firm_id:   firmId(),
    })
    showCreate.value = false
    form.value = emptyForm()
    fetchItems()
  } catch {} finally { saving.value = false }
}

async function deleteItem(id) {
  if (!confirm('Delete this record?')) return
  await client.delete(`/correspondence/${id}`)
  fetchItems()
}

function onUploaded() {
  setTimeout(fetchItems, 1500)
}

// ── Helpers ────────────────────────────────────────────────────────────────
function typeColor(t) {
  return { email:'#4a7cf7', letter:'#9f7aea', fax:'#48bb78', memo:'#ecc94b', call:'#fc8181' }[t] || '#718096'
}
function dirColor(d) { return d === 'inbound' ? '#48bb78' : '#4a7cf7' }
function fmtDate(d)  { return d ? new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' }) : '—' }
function toggleExpand(id) { expanded.value = expanded.value === id ? null : id }

const filtered = computed(() => items.value)
const counts = computed(() => ({
  total:    items.value.length,
  inbound:  items.value.filter(i => i.direction === 'inbound').length,
  outbound: items.value.filter(i => i.direction === 'outbound').length,
}))
</script>

<template>
  <div class="corr">

    <!-- Header -->
    <div class="corr__header">
      <div>
        <h1 class="corr__title">Correspondence</h1>
        <p class="corr__sub">Emails · letters · memos · calls</p>
      </div>
      <div class="header-actions">
        <button class="btn-upload" :disabled="!selectedMatter" @click="showUpload = true">↑ Upload</button>
        <button class="btn-gold" @click="showCreate = true; form = emptyForm()" :disabled="!selectedMatter">+ New</button>
      </div>
    </div>

    <!-- Matter selector + filters -->
    <div class="matter-bar">
      <label class="bar-label">Matter</label>
      <select class="bar-select" v-model="selectedMatter">
        <option v-for="m in matters" :key="m.id" :value="m">{{ m.case_number }} — {{ m.client_name }}</option>
      </select>
      <label class="bar-label">Direction</label>
      <select class="bar-select sm" v-model="filterDir">
        <option value="">All</option>
        <option value="inbound">Inbound</option>
        <option value="outbound">Outbound</option>
      </select>
      <label class="bar-label">Type</label>
      <select class="bar-select sm" v-model="filterType">
        <option value="">All</option>
        <option v-for="t in ['email','letter','fax','memo','call']" :key="t" :value="t">{{ t }}</option>
      </select>
    </div>

    <!-- Stats -->
    <div class="stats-row" v-if="items.length">
      <div class="stat"><span class="stat__n">{{ counts.total }}</span><span class="stat__l">Total</span></div>
      <div class="stat"><span class="stat__n" style="color:#48bb78">{{ counts.inbound }}</span><span class="stat__l">Inbound</span></div>
      <div class="stat"><span class="stat__n" style="color:#4a7cf7">{{ counts.outbound }}</span><span class="stat__l">Outbound</span></div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="state-msg">Loading…</div>

    <!-- Empty -->
    <div v-else-if="!filtered.length" class="empty">
      <div class="empty__icon">✉</div>
      <div class="empty__title">No correspondence yet</div>
      <div class="empty__sub">Log emails, letters, or calls for this matter.</div>
      <button class="btn-gold mt" @click="showCreate = true; form = emptyForm()">+ Add First Record</button>
    </div>

    <!-- List -->
    <div v-else class="item-list">
      <div v-for="item in filtered" :key="item.id" class="item-card" @click="toggleExpand(item.id)">
        <div class="item-card__row">
          <span class="type-pill" :style="{ background: typeColor(item.type)+'22', color: typeColor(item.type) }">{{ item.type }}</span>
          <span class="dir-pill"  :style="{ background: dirColor(item.direction)+'22', color: dirColor(item.direction) }">{{ item.direction }}</span>
          <span class="item-subject">{{ item.subject }}</span>
          <span class="dim date-col">{{ fmtDate(item.date) }}</span>
          <button class="action-btn" @click.stop="showUpload = true">↑ Upload</button>
          <button class="del-btn" @click.stop="deleteItem(item.id)">✕</button>
        </div>
        <div class="item-card__meta">
          <span v-if="item.from_party" class="dim">From: {{ item.from_party }}</span>
          <span v-if="item.to_party"   class="dim">To: {{ item.to_party }}</span>
        </div>
        <div v-if="expanded === item.id && item.body" class="item-card__body">{{ item.body }}</div>
      </div>
    </div>

    <!-- Create modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
        <div class="modal">
          <div class="modal__header">
            <h2>New Correspondence</h2>
            <button class="close-btn" @click="showCreate = false">✕</button>
          </div>
          <div class="modal__body">
            <div class="field-row">
              <div class="field f2">
                <label>Subject *</label>
                <input v-model="form.subject" placeholder="Re: Settlement offer" />
              </div>
              <div class="field">
                <label>Date</label>
                <input type="date" v-model="form.date" />
              </div>
            </div>
            <div class="field-row">
              <div class="field">
                <label>Type</label>
                <select v-model="form.type">
                  <option v-for="t in ['email','letter','fax','memo','call']" :key="t" :value="t">{{ t }}</option>
                </select>
              </div>
              <div class="field">
                <label>Direction</label>
                <select v-model="form.direction">
                  <option value="outbound">Outbound</option>
                  <option value="inbound">Inbound</option>
                </select>
              </div>
              <div class="field">
                <label>Status</label>
                <select v-model="form.status">
                  <option value="draft">Draft</option>
                  <option value="sent">Sent</option>
                  <option value="received">Received</option>
                </select>
              </div>
            </div>
            <div class="field-row">
              <div class="field f2"><label>From</label><input v-model="form.from_party" placeholder="Sender name / email" /></div>
              <div class="field f2"><label>To</label><input v-model="form.to_party" placeholder="Recipient name / email" /></div>
            </div>
            <div class="field"><label>CC</label><input v-model="form.cc_party" placeholder="CC recipients" /></div>
            <div class="field"><label>Body / Notes</label><textarea v-model="form.body" rows="5" placeholder="Content or summary…"></textarea></div>
          </div>
          <div class="modal__footer">
            <button class="btn-secondary" @click="showCreate = false">Cancel</button>
            <button class="btn-gold" @click="saveItem" :disabled="saving || !form.subject.trim()">
              {{ saving ? 'Saving…' : 'Save' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Discovery Upload — pre-scoped to selected matter, no picker needed -->
    <DiscoveryUpload
      :show="showUpload"
      :matter-id="selectedMatter?.id || 0"
      :matter-name="selectedMatter?.client_name || ''"
      :case-number="selectedMatter?.case_number || ''"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />

  </div>
</template>

<style scoped>
.corr { padding: 2rem; max-width: 1100px; }
.corr__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; gap: 1rem; }
.corr__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.corr__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.header-actions { display: flex; gap: 0.5rem; flex-shrink: 0; align-items: flex-start; }

.btn-upload { background: transparent; border: 1px solid var(--gold, #c9a84c); color: var(--gold, #c9a84c); border-radius: 6px; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; cursor: pointer; white-space: nowrap; transition: background 0.15s; }
.btn-upload:hover:not(:disabled) { background: rgba(201,168,76,0.1); }
.btn-upload:disabled { opacity: 0.4; cursor: not-allowed; }

.matter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.bar-label  { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; white-space: nowrap; }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 320px; }
.bar-select.sm { max-width: 130px; }

.stats-row { display: flex; gap: 1rem; margin-bottom: 1.25rem; }
.stat { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; display: flex; flex-direction: column; }
.stat__n { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.stat__l { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.1rem; }

.item-list { display: flex; flex-direction: column; gap: 0.5rem; }
.item-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.9rem 1rem; cursor: pointer; transition: border-color .15s; }
.item-card:hover { border-color: var(--gold); }
.item-card__row  { display: flex; align-items: center; gap: 0.6rem; }
.item-card__meta { display: flex; gap: 1rem; margin-top: 0.4rem; font-size: 0.78rem; padding-left: 0.1rem; }
.item-card__body { margin-top: 0.75rem; padding: 0.75rem; background: rgba(255,255,255,.03); border-radius: 6px; font-size: 0.85rem; color: var(--text-muted); white-space: pre-wrap; line-height: 1.6; }
.item-subject { flex: 1; font-size: 0.9rem; color: var(--text-primary); font-weight: 500; }
.date-col { font-size: 0.78rem; white-space: nowrap; }
.type-pill, .dir-pill { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; text-transform: uppercase; white-space: nowrap; }
.action-btn { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: 0.78rem; padding: 0.3rem 0.7rem; transition: all .2s; white-space: nowrap; }
.action-btn:hover { border-color: var(--gold); color: var(--gold); }
.del-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.1rem 0.3rem; border-radius: 4px; transition: color .15s; }
.del-btn:hover { color: #fc8181; }

.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.mt { margin-top: 1.25rem; }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; white-space: nowrap; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 640px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 0.85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }

.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field.f2 { flex: 2; }
.field label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select, .field textarea { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; padding: 0.5rem 0.75rem; outline: none; font-family: inherit; }
.field input:focus, .field select:focus, .field textarea:focus { border-color: var(--gold); }
.field textarea { resize: vertical; }
.field-row { display: flex; gap: 0.75rem; }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim { color: var(--text-muted); }
</style>
