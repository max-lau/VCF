<script setup>
import { ref, computed } from 'vue'
import client from '@/api/client'

const docA    = ref('')
const docB    = ref('')
const mode    = ref('compare')              // 'compare' | 'lease-diff'
const result  = ref(null)
const loading = ref(false)
const error   = ref(null)

const modes = [
  { key: 'compare',   label: 'Document Compare', sub: 'Side-by-side diff' },
  { key: 'lease-diff', label: 'Lease Diff',       sub: 'Clause-level changes' },
]

async function run() {
  if (!docA.value.trim() || !docB.value.trim()) return
  loading.value = true
  error.value   = null
  result.value  = null
  try {
    const { data } = await client.post('/documents/compare', {
      doc_a: docA.value,
      doc_b: docB.value,
      mode:  mode.value,
    })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Comparison failed'
  } finally {
    loading.value = false
  }
}

const similarity = computed(() => {
  const s = result.value?.similarity ?? result.value?.similarity_score ?? result.value?.score
  return s == null ? null : typeof s === 'number' ? s : parseFloat(s)
})

const entitiesBoth  = computed(() => result.value?.entities_in_both  || result.value?.common_entities  || [])
const entitiesOnlyA = computed(() => result.value?.entities_only_a  || result.value?.entities_in_a_only || [])
const entitiesOnlyB = computed(() => result.value?.entities_only_b  || result.value?.entities_in_b_only || [])

const diffSegments = computed(() => {
  const d = result.value?.diff || result.value?.diff_segments || result.value?.segments
  if (Array.isArray(d)) return d
  if (d?.added || d?.removed) {
    const out = []
    if (Array.isArray(d.removed)) d.removed.forEach(t => out.push({ type: 'removed', text: t }))
    if (Array.isArray(d.added))   d.added.forEach(t   => out.push({ type: 'added',   text: t }))
    return out
  }
  return []
})

function gaugeColor(v) {
  if (v >= 0.8) return '#4caf79'
  if (v >= 0.5) return '#ffb74d'
  return '#ff7070'
}
function entityKey(e, i) { return (e?.text || e?.name || e || '') + '-' + i }
function entityText(e) { return typeof e === 'string' ? e : (e.text || e.name || e.value || '—') }
</script>

<template>
  <div class="nlp-mod" style="max-width:1150px">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Document Compare</h1>
      <p class="nlp-mod__sub">Side-by-side comparison and clause-level diff</p>
    </div>

    <!-- Mode selector -->
    <div class="cmp-mode-bar">
      <button v-for="m in modes" :key="m.key"
        class="cmp-mode-btn" :class="{ active: mode === m.key }"
        @click="mode = m.key">
        <span class="cmp-mode-btn__label">{{ m.label }}</span>
        <span class="cmp-mode-btn__sub">{{ m.sub }}</span>
      </button>
    </div>

    <!-- Two-column input -->
    <div class="cmp-two-col">
      <div class="cmp-field-block">
        <label class="nlp-field-label">Document A</label>
        <textarea v-model="docA" class="nlp-textarea" rows="12" placeholder="Paste first document…" />
      </div>
      <div class="cmp-field-block">
        <label class="nlp-field-label">Document B</label>
        <textarea v-model="docB" class="nlp-textarea" rows="12" placeholder="Paste second document…" />
      </div>
    </div>

    <div class="nlp-input-actions">
      <button class="nlp-btn" :disabled="loading || !docA.trim() || !docB.trim()" @click="run">
        {{ loading ? 'Comparing…' : 'Compare Documents' }}
      </button>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <!-- Results -->
    <div v-if="result" class="cmp-results">
      <!-- Similarity gauge -->
      <div class="cmp-gauge-card">
        <div class="cmp-gauge-card__label">Similarity Score</div>
        <div class="cmp-gauge">
          <svg class="cmp-gauge__svg" viewBox="0 0 120 70" width="160" height="90">
            <path d="M10,65 A50,50 0 0,1 110,65" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="8" stroke-linecap="round" />
            <path d="M10,65 A50,50 0 0,1 110,65" fill="none"
              :stroke="gaugeColor(similarity || 0)"
              stroke-width="8" stroke-linecap="round"
              :stroke-dasharray="`${(similarity || 0) * 157} 157`" />
          </svg>
          <div class="cmp-gauge__val" :style="{ color: gaugeColor(similarity || 0) }">
            {{ similarity == null ? '—' : Math.round(similarity * 100) + '%' }}
          </div>
        </div>
      </div>

      <!-- Entity overlap -->
      <div class="cmp-entity-card">
        <div class="cmp-entity-card__title">Entity Overlap</div>
        <div class="cmp-entity-grid">
          <div class="cmp-entity-col cmp-entity-col--both">
            <div class="cmp-entity-col__head">In Both <span class="cmp-count">{{ entitiesBoth.length }}</span></div>
            <div v-if="!entitiesBoth.length" class="cmp-entity-empty">—</div>
            <div v-for="(e, i) in entitiesBoth" :key="entityKey(e, i)" class="cmp-entity-pill cmp-entity-pill--both">
              {{ entityText(e) }}
            </div>
          </div>
          <div class="cmp-entity-col cmp-entity-col--a">
            <div class="cmp-entity-col__head">Only A <span class="cmp-count">{{ entitiesOnlyA.length }}</span></div>
            <div v-if="!entitiesOnlyA.length" class="cmp-entity-empty">—</div>
            <div v-for="(e, i) in entitiesOnlyA" :key="entityKey(e, i)" class="cmp-entity-pill cmp-entity-pill--a">
              {{ entityText(e) }}
            </div>
          </div>
          <div class="cmp-entity-col cmp-entity-col--b">
            <div class="cmp-entity-col__head">Only B <span class="cmp-count">{{ entitiesOnlyB.length }}</span></div>
            <div v-if="!entitiesOnlyB.length" class="cmp-entity-empty">—</div>
            <div v-for="(e, i) in entitiesOnlyB" :key="entityKey(e, i)" class="cmp-entity-pill cmp-entity-pill--b">
              {{ entityText(e) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Visual diff -->
      <div v-if="diffSegments.length" class="cmp-diff-card">
        <div class="cmp-diff-card__title">Visual Diff</div>
        <div class="cmp-diff-body">
          <span v-for="(seg, i) in diffSegments" :key="i"
            :class="['cmp-diff-seg', `cmp-diff-seg--${seg.type || 'unchanged'}`]">
            {{ seg.text || seg.content || '' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cmp-mode-bar { display: flex; gap: .75rem; margin-bottom: 1.25rem; }
.cmp-mode-btn {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  cursor: pointer; display: flex; flex-direction: column; padding: .65rem 1.1rem;
  text-align: left; transition: border-color .15s;
}
.cmp-mode-btn.active { border-color: var(--gold); }
.cmp-mode-btn__label { color: var(--text-primary); font-size: .875rem; font-weight: 600; }
.cmp-mode-btn__sub   { color: var(--text-muted); font-size: .72rem; margin-top: .1rem; }

.cmp-two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin-bottom: .5rem; }
.cmp-field-block { display: flex; flex-direction: column; gap: .4rem; }

.cmp-results { display: flex; flex-direction: column; gap: 1rem; margin-top: 1.5rem; }

/* Gauge */
.cmp-gauge-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.25rem; display: flex; flex-direction: column;
  align-items: center; gap: .5rem;
}
.cmp-gauge-card__label {
  font-size: .72rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase;
}
.cmp-gauge { position: relative; display: flex; align-items: center; justify-content: center; }
.cmp-gauge__svg { display: block; }
.cmp-gauge__val {
  position: absolute; bottom: .1rem; font-family: var(--font-display);
  font-size: 1.4rem; font-weight: 700;
}

/* Entity overlap */
.cmp-entity-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.1rem 1.25rem;
}
.cmp-entity-card__title {
  font-size: .72rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase; margin-bottom: .75rem;
}
.cmp-entity-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 1rem; }
.cmp-entity-col__head {
  font-size: .76rem; color: var(--text-primary); font-weight: 600;
  margin-bottom: .5rem; display: flex; align-items: center; gap: .35rem;
}
.cmp-count { color: var(--text-muted); font-weight: 400; font-size: .7rem; }
.cmp-entity-empty { color: var(--text-muted); font-size: .78rem; opacity: .5; }
.cmp-entity-pill {
  display: inline-block; border: 1px solid; border-radius: 4px;
  font-size: .74rem; font-weight: 500; margin: .15rem .2rem .15rem 0;
  padding: .15rem .5rem;
}
.cmp-entity-pill--both { border-color: #4caf79; color: #4caf79; background: rgba(76,175,121,.1); }
.cmp-entity-pill--a    { border-color: #4a9eff; color: #4a9eff; background: rgba(74,158,255,.1); }
.cmp-entity-pill--b    { border-color: #b377ff; color: #b377ff; background: rgba(179,119,255,.1); }

/* Diff */
.cmp-diff-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.1rem 1.25rem;
}
.cmp-diff-card__title {
  font-size: .72rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase; margin-bottom: .75rem;
}
.cmp-diff-body {
  background: var(--bg-raised, #0d0d1a); border-radius: 6px;
  font-family: var(--font-mono); font-size: .8rem; line-height: 1.7;
  padding: .75rem; white-space: pre-wrap; word-break: break-word;
}
.cmp-diff-seg--added     { background: rgba(76,175,121,.18); color: #6ee7a8; }
.cmp-diff-seg--removed   { background: rgba(224,49,49,.18);  color: #ff9090; text-decoration: line-through; }
.cmp-diff-seg--unchanged { color: var(--text-primary); }
</style>
