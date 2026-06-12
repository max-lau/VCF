<template>
  <div class="piq-page">
    <div class="piq-page-header">
      <h2 class="piq-page-title">✅ Approval Queue</h2>
      <p class="piq-page-subtitle">Semi-automatic actions awaiting attorney sign-off</p>
    </div>

    <div v-if="loading" class="piq-loading">Loading queue…</div>
    <div v-else-if="error" class="piq-error">{{ error }}</div>
    <div v-else-if="!items.length" class="piq-empty-state">
      <span style="font-size:32px">✅</span>
      <p>Queue is clear — no pending approvals.</p>
    </div>

    <div v-else class="aq-list">
      <div v-for="item in items" :key="item.id" class="aq-card" :class="`aq-card--${item.priority <= 1 ? 'high' : 'normal'}`">
        <div class="aq-card__top">
          <div class="aq-card__left">
            <span class="aq-type-chip">{{ item.item_type }}</span>
            <span class="aq-card__title">{{ item.title }}</span>
          </div>
          <div class="aq-card__meta">
            <span v-if="item.due_by" class="aq-due" :class="isDueSoon(item.due_by) ? 'aq-due--urgent' : ''">
              Due {{ fmtDate(item.due_by) }}
            </span>
            <span class="aq-priority" :class="`aq-priority--${item.priority <= 1 ? 'high' : 'normal'}`">
              P{{ item.priority }}
            </span>
          </div>
        </div>

        <div v-if="item.recommended" class="aq-recommended">
          💡 Recommended: {{ item.recommended }}
        </div>

        <div v-if="item.context_json" class="aq-context">
          <div v-for="(val, key) in item.context_json" :key="key" class="aq-context-row">
            <span class="aq-context-key">{{ key }}</span>
            <span class="aq-context-val">{{ val }}</span>
          </div>
        </div>

        <div class="aq-card__actions">
          <textarea v-model="notes[item.id]" class="aq-note-input" placeholder="Resolution note (optional)…" rows="2" />
          <div class="aq-btns">
            <button class="piq-btn piq-btn--success piq-btn--sm" @click="resolve(item.id, 'approved')" :disabled="resolving[item.id]">
              ✓ Approve
            </button>
            <button class="piq-btn piq-btn--danger piq-btn--sm" @click="resolve(item.id, 'rejected')" :disabled="resolving[item.id]">
              ✗ Reject
            </button>
            <button class="piq-btn piq-btn--ghost piq-btn--sm" @click="resolve(item.id, 'deferred')" :disabled="resolving[item.id]">
              ⏸ Defer
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth     = useAuthStore()
const loading  = ref(true)
const error    = ref(null)
const items    = ref([])
const notes    = ref({})
const resolving = ref({})

async function fetchQueue() {
  try {
    const res = await fetch('/approvals', {
      headers: { Authorization: `Bearer ${auth.token}` }
    })
    if (!res.ok) throw new Error(`${res.status}`)
    const data = await res.json()
    items.value = data.items || []
  } catch (e) {
    error.value = `Failed to load queue: ${e.message}`
  } finally {
    loading.value = false
  }
}

async function resolve(id, decision) {
  resolving.value[id] = true
  try {
    const res = await fetch(`/approvals/${id}/resolve`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${auth.token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, resolution_note: notes.value[id] || null })
    })
    if (!res.ok) throw new Error(`${res.status}`)
    items.value = items.value.filter(i => i.id !== id)
  } catch (e) {
    error.value = `Action failed: ${e.message}`
  } finally {
    resolving.value[id] = false
  }
}

function fmtDate(iso) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function isDueSoon(iso) {
  return (new Date(iso) - Date.now()) < 86400000 * 2
}

onMounted(fetchQueue)
</script>

<style scoped>
.aq-list              { display: flex; flex-direction: column; gap: 12px; }
.aq-card              { background: var(--surface-card); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.aq-card--high        { border-left: 3px solid #f87171; }
.aq-card__top         { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.aq-card__left        { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.aq-card__title       { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.aq-card__meta        { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.aq-type-chip         { font-size: 11px; color: var(--text-tertiary); background: var(--surface-hover); padding: 2px 8px; border-radius: 6px; white-space: nowrap; }
.aq-due               { font-size: 12px; color: var(--text-tertiary); }
.aq-due--urgent       { color: #fbbf24; font-weight: 600; }
.aq-priority          { font-size: 11px; font-weight: 700; padding: 2px 6px; border-radius: 6px; }
.aq-priority--high    { background: rgba(239,68,68,.15); color: #f87171; }
.aq-priority--normal  { background: rgba(99,102,241,.15); color: #818cf8; }
.aq-recommended       { font-size: 13px; color: var(--text-secondary); background: rgba(99,102,241,.08); border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; }
.aq-context           { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.aq-context-row       { display: flex; gap: 4px; font-size: 12px; background: var(--surface-hover); border-radius: 4px; padding: 2px 8px; }
.aq-context-key       { color: var(--text-tertiary); }
.aq-context-val       { color: var(--text-secondary); font-weight: 500; }
.aq-card__actions     { display: flex; flex-direction: column; gap: 8px; border-top: 1px solid var(--border); padding-top: 12px; margin-top: 4px; }
.aq-note-input        { width: 100%; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 13px; padding: 8px; resize: vertical; font-family: inherit; }
.aq-btns              { display: flex; gap: 8px; }
.piq-btn--success     { background: rgba(16,185,129,.15); color: #34d399; border: 1px solid rgba(16,185,129,.3); }
.piq-btn--success:hover { background: rgba(16,185,129,.25); }
.piq-btn--danger      { background: rgba(239,68,68,.12); color: #f87171; border: 1px solid rgba(239,68,68,.25); }
.piq-btn--danger:hover  { background: rgba(239,68,68,.22); }
</style>
