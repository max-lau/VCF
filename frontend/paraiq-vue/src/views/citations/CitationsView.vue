<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const text     = ref('')
const mode     = ref('extract')            // 'extract' | 'resolve'
const result   = ref(null)                 // { citations: [...] }
const loading  = ref(false)
const error    = ref(null)
const patterns = ref(null)                 // GET /citations/patterns
const copied   = ref(false)

const modes = [
  { key: 'extract', label: 'Extract', sub: 'Find citations in text' },
  { key: 'resolve', label: 'Resolve', sub: 'Resolve to full references' },
]

const citations = computed(() => result.value?.citations || [])

async function run() {
  if (!text.value.trim()) return
  loading.value = true
  error.value   = null
  result.value  = null
  try {
    const ep = mode.value === 'extract' ? '/citations/extract' : '/citations/resolve'
    const { data } = await client.post(ep, { text: text.value })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Citation processing failed'
  } finally {
    loading.value = false
  }
}

async function fetchPatterns() {
  try {
    const { data } = await client.get('/citations/patterns')
    patterns.value = data?.patterns || data || null
  } catch { patterns.value = null }
}

async function copyCitations() {
  const lines = citations.value.map(c => {
    const parts = [c.text || c.citation || c.match || '']
    if (c.type)  parts.push(`[${c.type}]`)
    if (mode.value === 'resolve' && (c.reference || c.resolved)) {
      parts.push(`→ ${c.reference || c.resolved}`)
    }
    return parts.join(' ')
  })
  try {
    await navigator.clipboard.writeText(lines.join('\n'))
    copied.value = true
    setTimeout(() => (copied.value = false), 1800)
  } catch { /* clipboard unavailable */ }
}

function typeColor(t) {
  return ({
    statute:    '#ff7070',
    case:       '#4a9eff',
    regulation: '#b377ff',
    rule:       '#ffb74d',
    other:      '#999',
  })[(t || '').toLowerCase()] || '#999'
}

onMounted(fetchPatterns)
</script>

<template>
  <div class="nlp-mod" style="max-width:1000px">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Citation Resolver</h1>
      <p class="nlp-mod__sub">Extract and resolve legal citations from documents</p>
    </div>

    <!-- Mode selector -->
    <div class="cit-mode-bar">
      <button v-for="m in modes" :key="m.key"
        class="cit-mode-btn" :class="{ active: mode === m.key }"
        @click="mode = m.key">
        <span class="cit-mode-btn__label">{{ m.label }}</span>
        <span class="cit-mode-btn__sub">{{ m.sub }}</span>
      </button>
    </div>

    <!-- Input -->
    <div class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="8"
        placeholder="Paste text containing legal citations (e.g. 42 U.S.C. § 1983, Brown v. Board, 28 CFR § 43.4)…" />
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading || !text.trim()" @click="run">
          {{ loading ? 'Processing…' : mode === 'extract' ? 'Extract Citations' : 'Resolve Citations' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <!-- Results -->
    <div v-if="result" class="cit-results">
      <div class="cit-results__head">
        <div class="cit-results__title">
          Citations
          <span class="cit-badge">{{ citations.length }}</span>
        </div>
        <button v-if="citations.length" class="nlp-btn--outline" @click="copyCitations">
          {{ copied ? '✓ Copied' : 'Copy Citations' }}
        </button>
      </div>

      <div v-if="!citations.length" class="cit-empty">No citations detected.</div>

      <div v-else class="cit-table-wrap">
        <table class="cit-table">
          <thead>
            <tr>
              <th style="width:48px">#</th>
              <th style="width:110px">Type</th>
              <th>Citation</th>
              <th v-if="mode === 'resolve'">Resolved Reference</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(c, i) in citations" :key="i">
              <td class="cit-cell-num">{{ i + 1 }}</td>
              <td>
                <span class="cit-type-pill"
                  :style="{ background: typeColor(c.type) + '22', color: typeColor(c.type) }">
                  {{ c.type || 'other' }}
                </span>
              </td>
              <td class="cit-cell-text">{{ c.text || c.citation || c.match || '—' }}</td>
              <td v-if="mode === 'resolve'" class="cit-cell-ref">
                {{ c.reference || c.resolved || c.canonical || '—' }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- Patterns info panel -->
    <details class="cit-patterns" :open="!!patterns">
      <summary class="cit-patterns__summary">Recognized Patterns</summary>
      <div v-if="!patterns" class="cit-patterns__empty">Loading patterns…</div>
      <div v-else class="cit-patterns__grid">
        <div v-for="(p, i) in (Array.isArray(patterns) ? patterns : Object.entries(patterns))" :key="i" class="cit-pattern-card">
          <div class="cit-pattern-card__name">
            {{ Array.isArray(patterns) ? (p.name || p.type || `Pattern ${i+1}`) : p[0] }}
          </div>
          <code class="cit-pattern-card__regex">{{ Array.isArray(patterns) ? (p.pattern || p.regex || '') : p[1] }}</code>
          <div v-if="p.description || p.example" class="cit-pattern-card__desc">
            {{ p.description || p.example }}
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped>
.cit-mode-bar { display: flex; gap: .75rem; margin-bottom: 1.25rem; }
.cit-mode-btn {
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px;
  cursor: pointer; display: flex; flex-direction: column; padding: .65rem 1.1rem;
  text-align: left; transition: border-color .15s;
}
.cit-mode-btn.active { border-color: var(--gold); }
.cit-mode-btn__label { color: var(--text-primary); font-size: .875rem; font-weight: 600; }
.cit-mode-btn__sub   { color: var(--text-muted); font-size: .72rem; margin-top: .1rem; }

.cit-results { margin-top: 1rem; }
.cit-results__head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: .75rem;
}
.cit-results__title {
  font-size: .72rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase;
  display: flex; align-items: center; gap: .5rem;
}
.cit-badge {
  background: var(--gold); color: #000; border-radius: 10px;
  font-size: .68rem; font-weight: 700; padding: .1rem .5rem; min-width: 22px; text-align: center;
}
.cit-empty {
  color: var(--text-muted); font-size: .875rem; padding: 1.5rem; text-align: center;
  border: 1px dashed var(--border); border-radius: 8px;
}
.cit-table-wrap { border: 1px solid var(--border); border-radius: 8px; overflow-x: auto; }
.cit-table { border-collapse: collapse; font-size: .875rem; width: 100%; }
.cit-table th {
  background: var(--bg-card); border-bottom: 1px solid var(--border);
  color: var(--text-muted); font-size: .68rem; font-weight: 600;
  letter-spacing: .05em; padding: .6rem .75rem; text-align: left; text-transform: uppercase;
}
.cit-table td { border-bottom: 1px solid var(--border); padding: .6rem .75rem; vertical-align: top; }
.cit-table tr:last-child td { border-bottom: none; }
.cit-cell-num  { color: var(--text-muted); font-family: var(--font-mono); font-size: .78rem; }
.cit-cell-text { color: var(--text-primary); font-family: var(--font-mono); font-size: .82rem; word-break: break-word; }
.cit-cell-ref  { color: var(--text-muted); font-size: .82rem; word-break: break-word; }
.cit-type-pill {
  border-radius: 4px; font-size: .68rem; font-weight: 600;
  padding: .15rem .5rem; text-transform: uppercase; letter-spacing: .03em;
}

.cit-patterns {
  margin-top: 1.5rem; background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; overflow: hidden;
}
.cit-patterns__summary {
  cursor: pointer; font-size: .78rem; color: var(--text-muted); font-weight: 600;
  padding: .7rem 1rem; user-select: none; list-style: none; text-transform: uppercase;
  letter-spacing: .05em;
}
.cit-patterns__summary::-webkit-details-marker { display: none; }
.cit-patterns__summary::before { content: '▶  '; font-size: .6rem; opacity: .55; }
details[open] .cit-patterns__summary::before { content: '▼  '; }
.cit-patterns__empty { color: var(--text-muted); font-size: .82rem; padding: 0 1rem 1rem; }
.cit-patterns__grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: .6rem; padding: 0 1rem 1rem;
}
.cit-pattern-card {
  background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border);
  border-radius: 6px; padding: .6rem .7rem;
}
.cit-pattern-card__name {
  color: var(--gold); font-size: .76rem; font-weight: 600; margin-bottom: .35rem;
}
.cit-pattern-card__regex {
  font-family: var(--font-mono); font-size: .72rem; color: var(--text-primary);
  word-break: break-all; display: block;
}
.cit-pattern-card__desc {
  color: var(--text-muted); font-size: .72rem; margin-top: .3rem;
}
</style>
