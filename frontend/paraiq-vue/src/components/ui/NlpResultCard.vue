<template>
  <div class="rc">
    <div class="rc__header">
      <div class="rc__title">{{ title }}</div>
      <button class="rc__toggle" @click="showRaw = !showRaw">
        {{ showRaw ? 'Structured' : 'Raw JSON' }}
      </button>
    </div>

    <pre v-if="showRaw" class="rc__pre">{{ JSON.stringify(result, null, 2) }}</pre>

    <div v-else class="rc__body">

      <!-- Classification -->
      <div v-if="result.label != null && result.confidence != null" class="rc__section">
        <div class="rc__slabel">Classification</div>
        <div class="rc__row">
          <span class="rc__class-name">{{ result.label }}</span>
          <div class="rc__bar-wrap"><div class="rc__bar rc__bar--gold" :style="{ width: pct(result.confidence) }"></div></div>
          <span class="rc__pct">{{ Math.round(result.confidence * 100) }}%</span>
        </div>
        <div v-if="result.scores" class="rc__scores">
          <div v-for="(score, key) in sortedScores" :key="key" class="rc__row rc__row--sm">
            <span class="rc__score-key">{{ key }}</span>
            <div class="rc__bar-wrap"><div class="rc__bar rc__bar--dim" :style="{ width: pct(score) }"></div></div>
            <span class="rc__pct rc__pct--sm">{{ Math.round(score * 100) }}%</span>
          </div>
        </div>
      </div>

      <!-- Sentiment -->
      <div v-if="result.sentiment" class="rc__section">
        <div class="rc__slabel">Sentiment</div>
        <div class="rc__row">
          <span class="rc__sent-label" :style="{ color: sentimentColor }">{{ sentimentLabel }}</span>
          <div class="rc__bar-wrap"><div class="rc__bar" :style="{ width: pct(sentimentScore), background: sentimentColor }"></div></div>
          <span class="rc__pct">{{ Math.round(sentimentScore * 100) }}%</span>
        </div>
      </div>

      <!-- Entities -->
      <div v-if="result.entities?.length" class="rc__section">
        <div class="rc__slabel">Entities <span class="rc__count">({{ result.entities.length }})</span></div>
        <div class="rc__pills">
          <span
            v-for="(e, i) in result.entities" :key="i"
            class="rc__pill" :title="e.label || e.type"
            :style="entityStyle(e.label || e.type)"
          >{{ e.text }}</span>
        </div>
      </div>

      <!-- Clauses -->
      <div v-if="result.clauses?.length" class="rc__section">
        <div class="rc__slabel">Clauses <span class="rc__count">({{ result.clauses.length }})</span></div>
        <details v-for="(clause, i) in result.clauses" :key="i" class="rc__clause">
          <summary class="rc__clause-summary">Clause {{ i + 1 }}</summary>
          <p class="rc__clause-text">{{ typeof clause === 'string' ? clause : clause.text }}</p>
        </details>
      </div>

      <!-- Coreference -->
      <div v-if="result.clusters?.length" class="rc__section">
        <div class="rc__slabel">Coreference Clusters</div>
        <div v-for="(cl, i) in result.clusters" :key="i" class="rc__cluster">
          <span class="rc__cluster-rep">{{ cl.representative || cl.main || `Cluster ${i+1}` }}</span>
          <div class="rc__mentions">
            <span v-for="m in (cl.mentions || [])" :key="m" class="rc__mention">{{ m }}</span>
          </div>
        </div>
      </div>

      <!-- Resolved text -->
      <div v-if="result.resolved_text" class="rc__section">
        <div class="rc__slabel">Resolved Text</div>
        <p class="rc__prose">{{ result.resolved_text }}</p>
      </div>

      <!-- Contradictions -->
      <div v-if="result.contradictions?.length" class="rc__section">
        <div class="rc__slabel">Contradictions <span class="rc__count">({{ result.contradictions.length }})</span></div>
        <div v-for="(c, i) in result.contradictions" :key="i" class="rc__contra">
          <span :class="['rc__sev', `rc__sev--${(c.severity||'low').toLowerCase()}`]">{{ c.severity }}</span>
          <div class="rc__contra-body">
            <div class="rc__stmt">{{ c.statement_a }}</div>
            <div class="rc__stmt-vs">vs.</div>
            <div class="rc__stmt">{{ c.statement_b }}</div>
          </div>
        </div>
      </div>

      <!-- Translation -->
      <div v-if="result.translation" class="rc__section">
        <div class="rc__slabel">Translation</div>
        <p class="rc__prose">{{ result.translation }}</p>
      </div>

      <!-- Meta -->
      <div v-if="result.language || result.word_count" class="rc__meta">
        <span v-if="result.language">Language: <strong>{{ result.language.toUpperCase() }}</strong></span>
        <span v-if="result.word_count"> · {{ Number(result.word_count).toLocaleString() }} words</span>
      </div>

      <!-- Unknown key fallback -->
      <div v-if="unknownKeys.length" class="rc__section">
        <div v-if="hasKnownContent" class="rc__slabel">Other</div>
        <div v-for="key in unknownKeys" :key="key" class="rc__kv">
          <span class="rc__kv-key">{{ key }}</span>
          <span class="rc__kv-val">{{ fmtVal(result[key]) }}</span>
        </div>
      </div>

      <div v-if="!hasKnownContent && !unknownKeys.length" class="rc__empty">
        No structured data — <button class="rc__toggle" @click="showRaw = true">view raw JSON</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  result: { type: Object, required: true },
  title:  { type: String, default: 'Result' },
})

const showRaw = ref(false)
const pct = v => `${Math.round((v ?? 0) * 100)}%`

// ── Known keys (excluded from fallback) ──────────────────────────────────────
const KNOWN = new Set([
  'entities','sentiment','clauses','clusters','resolved_text',
  'label','confidence','scores','contradictions','translation',
  'language','word_count','text','status',
])
const unknownKeys = computed(() =>
  Object.keys(props.result).filter(k => !KNOWN.has(k) && props.result[k] != null)
)
const hasKnownContent = computed(() =>
  props.result.entities?.length ||
  props.result.sentiment ||
  props.result.clauses?.length ||
  props.result.clusters?.length ||
  props.result.resolved_text ||
  (props.result.label != null && props.result.confidence != null) ||
  props.result.contradictions?.length ||
  props.result.translation
)
const fmtVal = v =>
  v === null || v === undefined ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)

// ── Entity pills ──────────────────────────────────────────────────────────────
const ENTITY_COLORS = {
  PERSON:       { bg:'rgba(74,158,255,.16)',  color:'#4a9eff' },
  ORG:          { bg:'rgba(179,119,255,.16)', color:'#b377ff' },
  ORGANIZATION: { bg:'rgba(179,119,255,.16)', color:'#b377ff' },
  LOC:          { bg:'rgba(76,175,121,.16)',  color:'#4caf79' },
  LOCATION:     { bg:'rgba(76,175,121,.16)',  color:'#4caf79' },
  GPE:          { bg:'rgba(76,175,121,.16)',  color:'#4caf79' },
  DATE:         { bg:'rgba(255,183,77,.16)',  color:'#ffb74d' },
  TIME:         { bg:'rgba(255,183,77,.16)',  color:'#ffb74d' },
  MONEY:        { bg:'rgba(201,168,76,.16)',  color:'#c9a84c' },
  PERCENT:      { bg:'rgba(201,168,76,.16)',  color:'#c9a84c' },
  LAW:          { bg:'rgba(224,49,49,.16)',   color:'#ff7070' },
  STATUTE:      { bg:'rgba(224,49,49,.16)',   color:'#ff7070' },
}
const entityStyle = label => {
  const c = ENTITY_COLORS[label?.toUpperCase()] || { bg:'rgba(136,136,136,.14)', color:'#999' }
  return { background: c.bg, color: c.color, borderColor: c.color + '55' }
}

// ── Sentiment ─────────────────────────────────────────────────────────────────
const SENT_COLORS = { POSITIVE:'#4caf79', NEGATIVE:'#e03131', NEUTRAL:'#888', MIXED:'#ffb74d' }
const sentimentLabel = computed(() => {
  const s = props.result.sentiment
  return s?.label || s?.sentiment || 'Unknown'
})
const sentimentScore = computed(() => {
  const s = props.result.sentiment
  return s?.score ?? s?.confidence ?? 0
})
const sentimentColor = computed(() =>
  SENT_COLORS[sentimentLabel.value?.toUpperCase()] || '#888'
)

// ── Scores ────────────────────────────────────────────────────────────────────
const sortedScores = computed(() => {
  if (!props.result.scores) return {}
  return Object.fromEntries(
    Object.entries(props.result.scores).sort(([,a],[,b]) => b - a)
  )
})
</script>

<style scoped>
.rc { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }

.rc__header {
  display: flex; align-items: center; justify-content: space-between;
  padding: .65rem 1.1rem; border-bottom: 1px solid var(--border);
}
.rc__title {
  font-size: .68rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .06em; text-transform: uppercase;
}
.rc__toggle {
  background: none; border: 1px solid var(--border); border-radius: 4px;
  color: var(--text-muted); cursor: pointer; font-size: .68rem; padding: .18rem .5rem;
  transition: border-color .15s, color .15s;
}
.rc__toggle:hover { border-color: var(--gold); color: var(--gold); }

/* Raw */
.rc__pre {
  background: var(--bg-raised, #0d0d1a); color: var(--text-muted);
  font-family: var(--font-mono); font-size: .78rem; line-height: 1.6;
  margin: 0; overflow-x: auto; padding: 1rem 1.1rem;
  white-space: pre-wrap; word-break: break-word;
}

/* Body */
.rc__body { padding: .9rem 1.1rem; display: flex; flex-direction: column; gap: .9rem; }
.rc__section { display: flex; flex-direction: column; gap: .45rem; }
.rc__slabel {
  font-size: .66rem; color: var(--text-muted); text-transform: uppercase;
  letter-spacing: .07em; font-weight: 600;
}
.rc__count { font-weight: 400; opacity: .65; }

/* Bar rows */
.rc__row { display: flex; align-items: center; gap: .7rem; }
.rc__row--sm { opacity: .8; }
.rc__bar-wrap { flex: 1; height: 5px; background: rgba(255,255,255,.07); border-radius: 3px; overflow: hidden; }
.rc__bar      { height: 100%; border-radius: 3px; transition: width .35s ease; }
.rc__bar--gold { background: var(--gold); }
.rc__bar--dim  { background: rgba(201,168,76,.45); }
.rc__pct    { font-size: .78rem; color: var(--text-muted); min-width: 30px; text-align: right; }
.rc__pct--sm { font-size: .72rem; }
.rc__class-name { color: var(--gold); font-weight: 600; font-size: .88rem; min-width: 88px; }
.rc__sent-label { font-weight: 600; font-size: .88rem; min-width: 76px; }
.rc__scores { display: flex; flex-direction: column; gap: .25rem; padding-left: .4rem; }
.rc__score-key { font-size: .76rem; color: var(--text-muted); min-width: 88px; }

/* Entity pills */
.rc__pills { display: flex; flex-wrap: wrap; gap: .35rem; }
.rc__pill  { border: 1px solid; border-radius: 4px; font-size: .74rem; font-weight: 500; padding: .18rem .5rem; }

/* Clauses */
.rc__clause { border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.rc__clause-summary {
  cursor: pointer; font-size: .79rem; color: var(--text-muted);
  padding: .4rem .7rem; background: rgba(255,255,255,.025);
  user-select: none; list-style: none;
}
.rc__clause-summary::-webkit-details-marker { display: none; }
.rc__clause-summary::before { content: '▶  '; font-size: .58rem; opacity: .55; }
details[open] .rc__clause-summary::before { content: '▼  '; }
.rc__clause-text { margin: 0; padding: .55rem .7rem; font-size: .82rem; color: var(--text-primary); line-height: 1.6; border-top: 1px solid var(--border); }

/* Coreference */
.rc__cluster { display: flex; align-items: flex-start; gap: .7rem; padding: .35rem 0; border-bottom: 1px solid var(--border); }
.rc__cluster:last-child { border-bottom: none; }
.rc__cluster-rep { color: var(--gold); font-weight: 600; font-size: .8rem; min-width: 90px; flex-shrink: 0; }
.rc__mentions    { display: flex; flex-wrap: wrap; gap: .3rem; }
.rc__mention     { background: rgba(255,255,255,.06); border-radius: 4px; font-size: .73rem; padding: .12rem .4rem; color: var(--text-muted); }

/* Contradictions */
.rc__contra { display: flex; gap: .7rem; padding: .45rem 0; border-bottom: 1px solid var(--border); align-items: flex-start; }
.rc__contra:last-child { border-bottom: none; }
.rc__sev { font-size: .66rem; font-weight: 700; text-transform: uppercase; border-radius: 4px; padding: .18rem .42rem; flex-shrink: 0; }
.rc__sev--high   { background: rgba(224,49,49,.18);   color: #ff7070; }
.rc__sev--medium { background: rgba(255,183,77,.18);  color: #ffb74d; }
.rc__sev--low    { background: rgba(136,136,136,.14); color: #999; }
.rc__contra-body { display: flex; flex-direction: column; gap: .22rem; font-size: .81rem; }
.rc__stmt    { color: var(--text-primary); line-height: 1.5; }
.rc__stmt-vs { color: var(--text-muted); font-style: italic; font-size: .73rem; }

/* Prose */
.rc__prose { color: var(--text-primary); font-size: .84rem; line-height: 1.65; margin: 0; }

/* Meta */
.rc__meta { font-size: .73rem; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: .7rem; }

/* KV fallback */
.rc__kv { display: flex; justify-content: space-between; font-size: .81rem; padding: .28rem 0; border-bottom: 1px solid var(--border); }
.rc__kv:last-child { border-bottom: none; }
.rc__kv-key { color: var(--text-muted); text-transform: capitalize; }
.rc__kv-val { color: var(--text-primary); font-weight: 500; max-width: 58%; text-align: right; word-break: break-word; }

.rc__empty { color: var(--text-muted); font-size: .84rem; text-align: center; padding: .75rem 0; }
</style>
