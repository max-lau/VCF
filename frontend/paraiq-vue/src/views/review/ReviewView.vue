<script setup>
import { ref, onMounted, computed } from 'vue'
import client from '@/api/client'

const items        = ref([])
const pending      = ref(0)
const loading      = ref(true)
const exporting    = ref(false)
const activeItem   = ref(null)
const correction   = ref('')
const submitting   = ref(false)
const search       = ref('')

async function fetchQueue() {
  loading.value = true
  try {
    const { data } = await client.get('/feedback/queue')
    items.value   = data.items || []
    pending.value = data.pending || items.value.length
  } catch { items.value = [] }
  finally { loading.value = false }
}

async function markReviewed(id) {
  await client.post('/feedback/review', { feedback_id: id })
  items.value = items.value.filter(i => i.id !== id)
  pending.value = Math.max(0, pending.value - 1)
  if (activeItem.value?.id === id) activeItem.value = null
}

async function submitCorrection(item) {
  if (!correction.value.trim()) return
  submitting.value = true
  try {
    await client.post('/feedback', {
      analysis_id:     item.analysis_id,
      text:            item.text,
      predicted:       item.predicted,
      predicted_score: item.predicted_score,
      correct_label:   correction.value.trim(),
      feedback_type:   'sentiment_correction',
    })
    await markReviewed(item.id)
    correction.value = ''
    activeItem.value = null
  } catch(e) {
    alert(e.response?.data?.detail || 'Submit failed')
  } finally { submitting.value = false }
}

async function exportRetraining() {
  exporting.value = true
  try {
    const { data } = await client.get('/feedback/retraining-data')
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href = url; a.download = 'retraining-data.json'; a.click()
    URL.revokeObjectURL(url)
  } finally { exporting.value = false }
}

function openItem(item) {
  activeItem.value = activeItem.value?.id === item.id ? null : item
  correction.value = item.predicted || ''
}

function scoreColor(s) {
  if (s >= 0.8) return '#48bb78'
  if (s >= 0.5) return '#ecc94b'
  return '#fc8181'
}

function fmtDate(d) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}

const filtered = computed(() =>
  items.value.filter(i => !search.value ||
    JSON.stringify(i).toLowerCase().includes(search.value.toLowerCase()))
)

onMounted(fetchQueue)
</script>

<template>
  <div class="mod">
    <div class="mod__header">
      <div>
        <h1 class="mod__title">Review Queue</h1>
        <p class="mod__sub">Active learning — human-in-the-loop label correction</p>
      </div>
      <div class="header-actions">
        <button class="btn-export" :disabled="exporting" @click="exportRetraining">
          {{ exporting ? 'Exporting…' : '↓ Export Retraining Data' }}
        </button>
      </div>
    </div>

    <!-- Stats -->
    <div class="stats-row">
      <div class="stat-card">
        <div class="stat-card__val" :style="{ color: pending > 0 ? '#ecc94b' : '#48bb78' }">{{ pending }}</div>
        <div class="stat-card__label">Pending review</div>
      </div>
      <div class="stat-card">
        <div class="stat-card__val">{{ items.length }}</div>
        <div class="stat-card__label">In queue</div>
      </div>
    </div>

    <!-- Search -->
    <div class="filter-row">
      <input v-model="search" class="piq-input" placeholder="Search queue…" style="max-width:280px"/>
    </div>

    <div v-if="loading" class="state-msg">Loading queue…</div>

    <div v-else-if="!filtered.length" class="empty-state">
      <div class="empty-state__icon">✓</div>
      <div class="empty-state__title">Queue is clear</div>
      <div class="empty-state__sub">No items pending review.</div>
    </div>

    <div v-else class="queue-list">
      <div v-for="item in filtered" :key="item.id" class="queue-card"
        :class="{ 'queue-card--active': activeItem?.id === item.id }">

        <div class="queue-card__row" @click="openItem(item)">
          <div class="queue-card__meta">
            <span class="dim mono">#{{ item.id }}</span>
            <span class="pred-pill"
              :style="{ background: scoreColor(item.predicted_score)+'22', color: scoreColor(item.predicted_score) }">
              {{ item.predicted }}
            </span>
            <span class="score-tag" :style="{ color: scoreColor(item.predicted_score) }">
              {{ Math.round((item.predicted_score || 0) * 100) }}%
            </span>
          </div>
          <div class="queue-card__text">{{ (item.text || '').slice(0, 160) }}{{ item.text?.length > 160 ? '…' : '' }}</div>
          <div class="queue-card__footer">
            <span class="dim" style="font-size:.75rem">{{ fmtDate(item.created_at) }}</span>
            <div class="queue-card__actions">
              <button class="action-btn" @click.stop="openItem(item)">
                {{ activeItem?.id === item.id ? 'Close' : 'Correct' }}
              </button>
              <button class="action-btn action-btn--ok" @click.stop="markReviewed(item.id)">✓ Skip</button>
            </div>
          </div>
        </div>

        <!-- Correction panel -->
        <div v-if="activeItem?.id === item.id" class="correction-panel">
          <div class="correction-panel__label">Correct label</div>
          <div class="correction-row">
            <input v-model="correction" class="piq-input" placeholder="Enter correct label…"
              @keyup.enter="submitCorrection(item)"/>
            <button class="piq-btn-gold" :disabled="submitting || !correction.trim()"
              @click="submitCorrection(item)">
              {{ submitting ? 'Saving…' : 'Submit Correction' }}
            </button>
          </div>
          <div class="full-text">
            <div class="full-text__label">Full text</div>
            <div class="full-text__body">{{ item.text }}</div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.mod { padding: 2rem; max-width: 900px; }
.mod__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; gap: 1rem; }
.mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.mod__sub   { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.header-actions { flex-shrink: 0; }

.btn-export { background: transparent; border: 1px solid var(--gold, #c9a84c); color: var(--gold, #c9a84c); border-radius: 6px; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .5rem 1rem; transition: background .15s; white-space: nowrap; }
.btn-export:hover:not(:disabled) { background: rgba(201,168,76,.1); }
.btn-export:disabled { opacity: .4; cursor: not-allowed; }

.stats-row { display: flex; gap: 1rem; margin-bottom: 1.25rem; }
.stat-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: .85rem 1.25rem; }
.stat-card__val   { font-size: 1.6rem; font-weight: 700; }
.stat-card__label { color: var(--text-muted); font-size: .72rem; margin-top: .15rem; }

.filter-row { margin-bottom: 1rem; }
.piq-input { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: .875rem; padding: .45rem .75rem; outline: none; }
.piq-input:focus { border-color: var(--gold); }

.state-msg   { color: var(--text-muted); padding: 3rem; text-align: center; }
.empty-state { padding: 4rem 2rem; text-align: center; }
.empty-state__icon  { color: #48bb78; font-size: 2.5rem; margin-bottom: 1rem; }
.empty-state__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; margin-bottom: .4rem; }
.empty-state__sub   { color: var(--text-muted); font-size: .875rem; }

.queue-list { display: flex; flex-direction: column; gap: .6rem; }
.queue-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; transition: border-color .15s; }
.queue-card--active { border-color: var(--gold); }
.queue-card__row    { cursor: pointer; padding: .9rem 1rem; }
.queue-card__meta   { display: flex; align-items: center; gap: .6rem; margin-bottom: .5rem; }
.queue-card__text   { color: var(--text-primary); font-size: .875rem; line-height: 1.5; margin-bottom: .6rem; }
.queue-card__footer { display: flex; align-items: center; justify-content: space-between; }
.queue-card__actions { display: flex; gap: .4rem; }

.pred-pill { border-radius: 4px; font-size: .72rem; font-weight: 600; padding: .2rem .5rem; text-transform: capitalize; }
.score-tag { font-size: .75rem; font-weight: 600; }

.action-btn { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--text-muted); cursor: pointer; font-size: .78rem; padding: .25rem .65rem; transition: all .2s; }
.action-btn:hover     { border-color: var(--gold); color: var(--gold); }
.action-btn--ok:hover { border-color: #48bb78 !important; color: #48bb78 !important; }

.correction-panel { border-top: 1px solid var(--border); background: rgba(201,168,76,.04); padding: 1rem; }
.correction-panel__label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .5rem; }
.correction-row { display: flex; gap: .6rem; margin-bottom: .85rem; }
.piq-btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .45rem 1rem; transition: opacity .2s; white-space: nowrap; }
.piq-btn-gold:hover:not(:disabled) { opacity: .85; }
.piq-btn-gold:disabled { cursor: not-allowed; opacity: .4; }

.full-text { margin-top: .5rem; }
.full-text__label { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-bottom: .4rem; }
.full-text__body  { background: var(--bg-raised, #0d0d1a); border-radius: 6px; color: var(--text-muted); font-size: .8rem; line-height: 1.6; max-height: 200px; overflow-y: auto; padding: .75rem; white-space: pre-wrap; }

.dim  { color: var(--text-muted); }
.mono { font-family: var(--font-mono); }
</style>
