<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import client from '@/api/client'

const props = defineProps({
  docId: { type: Number, required: true },
})

const emit = defineEmits(['close'])

const loading    = ref(false)
const error      = ref(null)
const docData    = ref(null)
const activeFilter = ref(null)  // null = all, or a type string
const hoveredAnn = ref(null)

const ANNOTATION_META = {
  person:       { label: 'Person',       icon: '👤', color: '#4a9eff' },
  organization: { label: 'Organization', icon: '🏢', color: '#b377ff' },
  date:         { label: 'Date',         icon: '📅', color: '#ffb74d' },
  deadline:     { label: 'Deadline',     icon: '⏰', color: '#ff7070' },
  money:        { label: 'Money',        icon: '💰', color: '#c9a84c' },
  citation:     { label: 'Citation',     icon: '⚖', color: '#ff7070' },
  jurisdiction: { label: 'Jurisdiction', icon: '🏛', color: '#4caf79' },
  pii:          { label: 'PII',          icon: '🔒', color: '#e03131' },
  privileged:   { label: 'Privileged',   icon: '🛡', color: '#9f7aea' },
  obligation:   { label: 'Obligation',   icon: '📝', color: '#48bb78' },
}

async function fetchAnnotated() {
  loading.value = true
  error.value = null
  try {
    const { data } = await client.get(`/documents/${props.docId}/annotated`)
    docData.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Failed to load annotations'
  } finally {
    loading.value = false
  }
}

async function reAnnotate() {
  loading.value = true
  error.value = null
  try {
    const { data } = await client.post(`/documents/${props.docId}/annotate`)
    docData.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Re-annotation failed'
  } finally {
    loading.value = false
  }
}

onMounted(fetchAnnotated)
watch(() => props.docId, fetchAnnotated)

// Build highlighted text segments
const segments = computed(() => {
  if (!docData.value?.text) return []

  const text = docData.value.text
  const anns = docData.value.annotations || []

  // Filter by active type
  const filtered = activeFilter.value
    ? anns.filter(a => a.type === activeFilter.value)
    : anns

  if (!filtered.length) return [{ text, ann: null }]

  // Sort by position
  const sorted = [...filtered].sort((a, b) => a.start - b.start)

  const result = []
  let pos = 0

  for (const ann of sorted) {
    // Text before annotation
    if (ann.start > pos) {
      result.push({ text: text.slice(pos, ann.start), ann: null })
    }
    // The annotated text
    result.push({ text: text.slice(ann.start, ann.end), ann })
    pos = ann.end
  }
  // Remaining text
  if (pos < text.length) {
    result.push({ text: text.slice(pos), ann: null })
  }

  return result
})

const stats = computed(() => {
  if (!docData.value?.annotations) return {}
  const counts = {}
  for (const ann of docData.value.annotations) {
    counts[ann.type] = (counts[ann.type] || 0) + 1
  }
  return counts
})

const filterTypes = computed(() => {
  return Object.keys(stats.value).sort()
})
</script>

<template>
  <div class="doc-viewer">
    <!-- Header -->
    <div class="dv-header">
      <div class="dv-header__info">
        <h2 class="dv-title">{{ docData?.document_name || `Document #${docId}` }}</h2>
        <div class="dv-meta">
          <span v-if="docData?.case_id" class="dv-meta-tag">Case #{{ docData.case_id }}</span>
          <span v-if="docData?.source" class="dv-meta-tag">📂 {{ docData.source }}</span>
          <span v-if="docData?.risk_level" class="dv-meta-tag" :style="{ color: {low:'#48bb78',medium:'#ecc94b',high:'#fc8181'}[docData.risk_level] || '#718096' }">
            ● {{ docData.risk_level }} risk
          </span>
          <span v-if="docData?.privilege?.privileged" class="dv-meta-tag dv-meta-tag--priv">
            🛡 Privileged ({{ Math.round((docData.privilege.confidence || 0) * 100) }}%)
          </span>
        </div>
      </div>
      <div class="dv-header__actions">
        <button class="dv-btn" @click="reAnnotate" :disabled="loading">🔄 Re-annotate</button>
        <button class="dv-btn dv-btn--close" @click="emit('close')">✕</button>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="dv-loading">
      <div class="dv-spinner"></div>
      Analyzing document…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="dv-error">⚠ {{ error }}</div>

    <!-- No text -->
    <div v-else-if="docData && !docData.text" class="dv-empty">
      <div class="dv-empty__icon">📄</div>
      <div class="dv-empty__title">No extractable text</div>
      <div class="dv-empty__sub">{{ docData.message || 'Run OCR on this document first.' }}</div>
    </div>

    <!-- Content -->
    <div v-else-if="docData" class="dv-body">

      <!-- Filter bar -->
      <div class="dv-filters" v-if="filterTypes.length">
        <button
          class="dv-filter-chip"
          :class="{ 'dv-filter-chip--active': !activeFilter }"
          @click="activeFilter = null"
        >
          All ({{ docData.annotations.length }})
        </button>
        <button
          v-for="type in filterTypes"
          :key="type"
          class="dv-filter-chip"
          :class="{ 'dv-filter-chip--active': activeFilter === type }"
          :style="activeFilter === type ? { borderColor: ANNOTATION_META[type]?.color, color: ANNOTATION_META[type]?.color } : {}"
          @click="activeFilter = activeFilter === type ? null : type"
        >
          {{ ANNOTATION_META[type]?.icon || '●' }} {{ ANNOTATION_META[type]?.label || type }}
          ({{ stats[type] }})
        </button>
      </div>

      <!-- Document text with highlights -->
      <div class="dv-text-container">
        <div class="dv-text" @mouseleave="hoveredAnn = null">
          <template v-for="(seg, i) in segments" :key="i">
            <span
              v-if="seg.ann"
              class="dv-highlight"
              :style="{ background: (ANNOTATION_META[seg.ann.type]?.color || '#888') + '22', borderBottom: '2px solid ' + (ANNOTATION_META[seg.ann.type]?.color || '#888') + '88', color: ANNOTATION_META[seg.ann.type]?.color || '#888' }"
              @mouseenter="hoveredAnn = seg.ann"
            >
              {{ seg.text }}
              <span class="dv-highlight__icon">{{ ANNOTATION_META[seg.ann.type]?.icon || '●' }}</span>

              <!-- Tooltip -->
              <div v-if="hoveredAnn === seg.ann" class="dv-tooltip" @click.stop>
                <div class="dv-tooltip__header">
                  <span class="dv-tooltip__icon">{{ ANNOTATION_META[seg.ann.type]?.icon }}</span>
                  <span class="dv-tooltip__type">{{ ANNOTATION_META[seg.ann.type]?.label || seg.ann.type }}</span>
                </div>
                <div class="dv-tooltip__text">"{{ seg.ann.text }}"</div>
                <div v-if="seg.ann.metadata" class="dv-tooltip__meta">
                  <template v-if="seg.ann.type === 'person' && seg.ann.metadata.role">
                    <div>Role: {{ seg.ann.metadata.role }}</div>
                    <div v-if="seg.ann.metadata.organization">Org: {{ seg.ann.metadata.organization }}</div>
                  </template>
                  <template v-else-if="seg.ann.type === 'pii'">
                    <div>Type: {{ seg.ann.metadata.pii_type }}</div>
                  </template>
                  <template v-else-if="seg.ann.type === 'citation'">
                    <div>Type: {{ seg.ann.metadata.citation_type }}</div>
                  </template>
                  <template v-else-if="seg.ann.type === 'privileged'">
                    <div>Keyword: {{ seg.ann.metadata.keyword }}</div>
                    <div v-if="seg.ann.metadata.confidence">Confidence: {{ Math.round(seg.ann.metadata.confidence * 100) }}%</div>
                  </template>
                  <template v-else-if="seg.ann.type === 'obligation'">
                    <div>Obligation: {{ seg.ann.metadata.obligation }}</div>
                    <div v-if="seg.ann.metadata.deadline">Deadline: {{ seg.ann.metadata.deadline }}</div>
                  </template>
                  <template v-else-if="seg.ann.type === 'deadline'">
                    <div>⚠ Potential deadline — verify against court rules</div>
                  </template>
                </div>
              </div>
            </span>
            <span v-else>{{ seg.text }}</span>
          </template>
        </div>
      </div>

      <!-- Legend -->
      <div class="dv-legend" v-if="filterTypes.length">
        <span class="dv-legend__title">Legend:</span>
        <span v-for="type in filterTypes" :key="type" class="dv-legend__item">
          <span class="dv-legend__dot" :style="{ background: ANNOTATION_META[type]?.color || '#888' }"></span>
          {{ ANNOTATION_META[type]?.label || type }}
        </span>
      </div>

    </div>
  </div>
</template>

<style scoped>
.doc-viewer { display: flex; flex-direction: column; height: 100%; background: var(--bg-card, #0f0f1a); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }

.dv-header { display: flex; justify-content: space-between; align-items: flex-start; padding: 1rem 1.25rem; border-bottom: 1px solid var(--border); }
.dv-title { font-size: 1rem; font-weight: 600; color: var(--text-primary); margin: 0; }
.dv-meta { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-top: 0.35rem; }
.dv-meta-tag { font-size: 0.72rem; color: var(--text-muted); background: rgba(255,255,255,.04); border-radius: 4px; padding: 0.12rem 0.4rem; }
.dv-meta-tag--priv { background: rgba(159,122,234,.15); color: #9f7aea; font-weight: 600; }
.dv-header__actions { display: flex; gap: 0.4rem; }
.dv-btn { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.75rem; padding: 0.35rem 0.6rem; transition: all .15s; }
.dv-btn:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); }
.dv-btn:disabled { opacity: .4; cursor: not-allowed; }
.dv-btn--close:hover { border-color: #fc8181; color: #fc8181; }

.dv-loading { display: flex; align-items: center; gap: 0.6rem; color: var(--text-muted); padding: 3rem; justify-content: center; }
.dv-spinner { width: 16px; height: 16px; border: 2px solid var(--border); border-top-color: var(--gold); border-radius: 50%; animation: dvspin .8s linear infinite; }
@keyframes dvspin { to { transform: rotate(360deg); } }

.dv-error { color: #fc8181; padding: 1rem 1.25rem; font-size: 0.85rem; }
.dv-empty { text-align: center; padding: 3rem 1rem; }
.dv-empty__icon { font-size: 2rem; opacity: .4; margin-bottom: 0.5rem; }
.dv-empty__title { color: var(--text-primary); font-size: 1rem; font-weight: 600; }
.dv-empty__sub { color: var(--text-muted); font-size: 0.8rem; margin-top: 0.3rem; }

.dv-body { display: flex; flex-direction: column; flex: 1; overflow: hidden; }

.dv-filters { display: flex; gap: 0.35rem; flex-wrap: wrap; padding: 0.6rem 1.25rem; border-bottom: 1px solid var(--border); }
.dv-filter-chip { background: rgba(255,255,255,.03); border: 1px solid var(--border); border-radius: 16px; color: var(--text-muted); cursor: pointer; font-size: 0.72rem; padding: 0.2rem 0.6rem; transition: all .15s; }
.dv-filter-chip:hover { border-color: var(--text-muted); color: var(--text-primary); }
.dv-filter-chip--active { background: rgba(201,168,76,.15); border-color: var(--gold); color: var(--gold); }

.dv-text-container { flex: 1; overflow-y: auto; padding: 1.25rem; }
.dv-text { font-size: 0.85rem; line-height: 1.8; color: var(--text-primary); white-space: pre-wrap; word-break: break-word; font-family: Georgia, 'Times New Roman', serif; }

.dv-highlight { position: relative; cursor: pointer; border-radius: 2px; padding: 0 1px; transition: background .15s; }
.dv-highlight:hover { filter: brightness(1.3); }
.dv-highlight__icon { font-size: 0.6rem; margin-left: 1px; opacity: 0.7; }

.dv-tooltip { position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%); background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 8px; padding: 0.6rem 0.75rem; min-width: 200px; max-width: 320px; z-index: 50; box-shadow: 0 8px 24px rgba(0,0,0,.4); font-family: -apple-system, sans-serif; }
.dv-tooltip__header { display: flex; align-items: center; gap: 0.35rem; margin-bottom: 0.35rem; }
.dv-tooltip__icon { font-size: 0.85rem; }
.dv-tooltip__type { font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; color: var(--text-muted); }
.dv-tooltip__text { font-size: 0.78rem; color: var(--text-primary); font-style: italic; margin-bottom: 0.3rem; }
.dv-tooltip__meta { font-size: 0.72rem; color: var(--text-muted); display: flex; flex-direction: column; gap: 0.15rem; }

.dv-legend { display: flex; gap: 0.75rem; flex-wrap: wrap; align-items: center; padding: 0.5rem 1.25rem; border-top: 1px solid var(--border); }
.dv-legend__title { font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .04em; }
.dv-legend__item { display: flex; align-items: center; gap: 0.25rem; font-size: 0.72rem; color: var(--text-muted); }
.dv-legend__dot { width: 8px; height: 8px; border-radius: 50%; }
</style>
