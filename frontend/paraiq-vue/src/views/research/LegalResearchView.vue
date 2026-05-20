<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import client from '@/api/client'

const firmId = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const matters      = ref([])
const notes        = ref([])
const selectedMatter = ref(null)
const loading      = ref(false)
const showCreate   = ref(false)
const editing      = ref(null)
const saving       = ref(false)
const filterType   = ref('')
const filterFav    = ref('')

const TYPES = ['case_law','statute','regulation','secondary','memo','brief','other']

function emptyForm() {
  return { title:'', research_type:'case_law', citation:'', jurisdiction:'', summary:'', body:'', relevance:'', url:'', tags:'', is_favorable:true }
}
const form = ref(emptyForm())

async function fetchMatters() {
  try {
    const { data } = await client.get('/cases/search?q=&firm_id=' + firmId())
    matters.value = data.cases || []
    if (matters.value.length) selectedMatter.value = matters.value[0]
  } catch {}
}

async function fetchNotes() {
  if (!selectedMatter.value) return
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filterType.value) params.set('research_type', filterType.value)
    if (filterFav.value !== '') params.set('is_favorable', filterFav.value)
    const { data } = await client.get(`/research/matter/${selectedMatter.value.id}?${params}`)
    notes.value = data
  } catch { notes.value = [] }
  finally { loading.value = false }
}

watch(selectedMatter, fetchNotes)
watch([filterType, filterFav], fetchNotes)
onMounted(() => fetchMatters().then(fetchNotes))

function openEdit(n) {
  editing.value = n.id
  form.value = { title:n.title, research_type:n.research_type, citation:n.citation||'', jurisdiction:n.jurisdiction||'', summary:n.summary||'', body:n.body||'', relevance:n.relevance||'', url:n.url||'', tags:n.tags||'', is_favorable:!!n.is_favorable }
  showCreate.value = true
}

function openCreate() {
  editing.value = null
  form.value = emptyForm()
  showCreate.value = true
}

async function save() {
  if (!form.value.title.trim()) return
  saving.value = true
  try {
    if (editing.value) {
      await client.put(`/research/${editing.value}`, form.value)
    } else {
      await client.post('/research/', { ...form.value, matter_id: selectedMatter.value?.id, firm_id: firmId() })
    }
    showCreate.value = false
    editing.value = null
    fetchNotes()
  } catch {} finally { saving.value = false }
}

async function deleteNote(id) {
  if (!confirm('Delete this research note?')) return
  await client.delete(`/research/${id}`)
  fetchNotes()
}

function typeColor(t) {
  return { case_law:'#4a7cf7', statute:'#9f7aea', regulation:'#ecc94b', secondary:'#48bb78', memo:'#c9a84c', brief:'#4a7cf7', other:'#718096' }[t] || '#718096'
}
function typeIcon(t) {
  return { case_law:'⚖', statute:'📜', regulation:'📋', secondary:'📚', memo:'📝', brief:'📄', other:'◎' }[t] || '◎'
}
function fmtDate(d) { return d ? new Date(d).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '—' }

const counts = computed(() => ({
  total: notes.value.length,
  favorable: notes.value.filter(n=>n.is_favorable).length,
  adverse: notes.value.filter(n=>!n.is_favorable).length,
}))
</script>

<template>
  <div class="res">
    <div class="res__header">
      <div><h1 class="res__title">Legal Research</h1><p class="res__sub">Case law · statutes · regulations · memos</p></div>
      <button class="btn-gold" @click="openCreate" :disabled="!selectedMatter">+ New Note</button>
    </div>

    <div class="filter-bar">
      <label class="bar-label">Matter</label>
      <select class="bar-select" v-model="selectedMatter">
        <option v-for="m in matters" :key="m.id" :value="m">{{ m.case_number }} — {{ m.client_name }}</option>
      </select>
      <label class="bar-label">Type</label>
      <select class="bar-select sm" v-model="filterType">
        <option value="">All</option>
        <option v-for="t in TYPES" :key="t" :value="t">{{ t.replace(/_/g,' ') }}</option>
      </select>
      <label class="bar-label">Stance</label>
      <select class="bar-select sm" v-model="filterFav">
        <option value="">All</option>
        <option value="true">Favorable</option>
        <option value="false">Adverse</option>
      </select>
    </div>

    <div class="stats-row" v-if="notes.length">
      <div class="stat"><span class="stat__n">{{ counts.total }}</span><span class="stat__l">Notes</span></div>
      <div class="stat"><span class="stat__n" style="color:#48bb78">{{ counts.favorable }}</span><span class="stat__l">Favorable</span></div>
      <div class="stat"><span class="stat__n" style="color:#fc8181">{{ counts.adverse }}</span><span class="stat__l">Adverse</span></div>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!notes.length" class="empty">
      <div class="empty__icon">🔬</div>
      <div class="empty__title">No research notes yet</div>
      <div class="empty__sub">Add case law, statutes, and research memos for this matter.</div>
      <button class="btn-gold mt" @click="openCreate">+ Add First Note</button>
    </div>

    <div v-else class="note-list">
      <div v-for="n in notes" :key="n.id" class="note-card">
        <div class="note-card__top">
          <span class="type-pill" :style="{ background: typeColor(n.research_type)+'22', color: typeColor(n.research_type) }">
            {{ typeIcon(n.research_type) }} {{ n.research_type.replace(/_/g,' ') }}
          </span>
          <span class="stance-pill" :class="n.is_favorable ? 'fav' : 'adv'">{{ n.is_favorable ? 'Favorable' : 'Adverse' }}</span>
          <span class="dim sm">{{ fmtDate(n.created_at) }}</span>
          <div class="note-actions">
            <button class="icon-btn" @click="openEdit(n)">✏</button>
            <button class="icon-btn del" @click="deleteNote(n.id)">✕</button>
          </div>
        </div>
        <div class="note-title">{{ n.title }}</div>
        <div v-if="n.citation" class="note-citation mono dim">{{ n.citation }}{{ n.jurisdiction ? ' · ' + n.jurisdiction : '' }}</div>
        <div v-if="n.summary" class="note-summary dim">{{ n.summary }}</div>
        <div v-if="n.relevance" class="note-relevance">
          <span class="rel-label">Relevance:</span> {{ n.relevance }}
        </div>
        <a v-if="n.url" :href="n.url" target="_blank" class="note-link">↗ Source</a>
      </div>
    </div>

    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal__header">
          <h2>{{ editing ? 'Edit Research Note' : 'New Research Note' }}</h2>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal__body">
          <div class="field-row">
            <div class="field f2"><label>Title *</label><input v-model="form.title" placeholder="e.g. McDonnell Douglas Corp. v. Green" /></div>
            <div class="field"><label>Type</label>
              <select v-model="form.research_type">
                <option v-for="t in TYPES" :key="t" :value="t">{{ t.replace(/_/g,' ') }}</option>
              </select>
            </div>
          </div>
          <div class="field-row">
            <div class="field f2"><label>Citation</label><input v-model="form.citation" placeholder="411 U.S. 792 (1973)" /></div>
            <div class="field"><label>Jurisdiction</label><input v-model="form.jurisdiction" placeholder="SDNY, SCOTUS…" /></div>
          </div>
          <div class="field"><label>Summary</label><textarea v-model="form.summary" rows="3" placeholder="Brief summary of holding or content…"></textarea></div>
          <div class="field"><label>Relevance to Matter</label><textarea v-model="form.relevance" rows="2" placeholder="How this applies to the case…"></textarea></div>
          <div class="field"><label>Full Notes</label><textarea v-model="form.body" rows="4" placeholder="Detailed notes, quotes, analysis…"></textarea></div>
          <div class="field-row">
            <div class="field f2"><label>Source URL</label><input v-model="form.url" placeholder="https://law.justia.com/…" /></div>
            <div class="field"><label>Tags</label><input v-model="form.tags" placeholder="employment, burden-shifting" /></div>
          </div>
          <label class="check-label">
            <input type="checkbox" v-model="form.is_favorable" />
            Favorable to our position
          </label>
        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showCreate = false">Cancel</button>
          <button class="btn-gold" @click="save" :disabled="saving || !form.title.trim()">{{ saving ? 'Saving…' : (editing ? 'Update' : 'Save') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.res { padding: 2rem; max-width: 1000px; }
.res__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.res__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.res__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.filter-bar  { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.bar-label   { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; letter-spacing: .05em; white-space: nowrap; }
.bar-select  { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; max-width: 300px; }
.bar-select.sm { max-width: 140px; }
.stats-row   { display: flex; gap: 1rem; margin-bottom: 1.25rem; }
.stat { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; display: flex; flex-direction: column; }
.stat__n { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.stat__l { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.1rem; }
.note-list   { display: flex; flex-direction: column; gap: 0.75rem; }
.note-card   { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem 1.25rem; transition: border-color .15s; }
.note-card:hover { border-color: var(--gold); }
.note-card__top { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.6rem; flex-wrap: wrap; }
.note-title  { color: var(--text-primary); font-size: 0.95rem; font-weight: 600; margin-bottom: 0.35rem; }
.note-citation { font-size: 0.8rem; margin-bottom: 0.35rem; }
.note-summary  { font-size: 0.85rem; line-height: 1.5; margin-bottom: 0.35rem; }
.note-relevance { font-size: 0.82rem; color: var(--text-muted); }
.rel-label   { color: var(--gold); font-weight: 600; }
.note-link   { color: var(--gold); font-size: 0.8rem; text-decoration: none; }
.note-link:hover { text-decoration: underline; }
.note-actions { display: flex; gap: 0.25rem; margin-left: auto; }
.type-pill   { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.5rem; text-transform: capitalize; }
.stance-pill { border-radius: 4px; font-size: 0.68rem; font-weight: 700; padding: 0.15rem 0.4rem; }
.stance-pill.fav { background: rgba(72,187,120,.15); color: #48bb78; }
.stance-pill.adv { background: rgba(252,129,129,.15); color: #fc8181; }
.icon-btn    { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.15rem 0.3rem; border-radius: 4px; transition: color .15s; }
.icon-btn:hover { color: var(--text-primary); }
.icon-btn.del:hover { color: #fc8181; }
.check-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-muted); cursor: pointer; }
.check-label input { accent-color: var(--gold); }
.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.mt { margin-top: 1.25rem; }
.btn-gold     { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
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
.mono { font-family: var(--font-mono); }
.sm  { font-size: 0.78rem; }
.dim { color: var(--text-muted); }
</style>
