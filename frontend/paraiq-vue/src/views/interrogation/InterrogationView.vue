<script setup>
import { ref, computed } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref('')
const result = ref(null)
const loading = ref(false)
const error = ref(null)

const SAMPLE = `Q: Please state your name and occupation for the record.
A: My name is Robert Hayes. I am a project manager at Northbridge Construction.

Q: Where were you on the night of October 12th?
A: I was at the office working late. I left around 8 PM.

Q: Did you see Mr. Larson that evening?
A: No, I did not see Mr. Larson at all that night.

Q: Earlier in your deposition you mentioned speaking with Mr. Larson. Can you clarify?
A: I may have spoken to him briefly on the phone, but not in person.

Q: So you did have contact with him?
A: I don't recall. It was a long time ago. I'd rather not say without my notes.

Q: The security log shows you badged into the Larson building at 9:30 PM. How do you explain that?
A: That must be a mistake. Or maybe I went there to drop off documents. I don't really remember.

Q: You said you left the office at 8 PM and didn't see Mr. Larson. Now you may have visited his building?
A: I can't be certain of the timeline. These details are fuzzy.`

async function analyze() {
  if (!text.value.trim()) return
  loading.value = true
  error.value = null
  result.value = null
  try {
    const { data } = await client.post('/interrogate', { text: text.value })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Analysis failed — please try again.'
  } finally {
    loading.value = false
  }
}

function loadExample() {
  text.value = SAMPLE
  result.value = null
  error.value = null
}

function clearAll() {
  text.value = ''
  result.value = null
  error.value = null
}

const contradictionsCount = computed(() => result.value?.contradictions?.length || 0)
const evasionsCount = computed(() => result.value?.evasions?.length || 0)
const consistencyScore = computed(() => {
  if (!result.value) return null
  const v = result.value.consistency_score ?? result.value.consistency
  if (v == null) return null
  return Math.round((typeof v === 'number' && v <= 1 ? v : v / 100) * 100)
})
function scoreColor(p) {
  if (p == null) return 'var(--text-muted)'
  if (p > 70) return '#48bb78'
  if (p >= 40) return '#ecc94b'
  return '#fc8181'
}
</script>

<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Interrogation Analyzer</h1>
      <p class="nlp-mod__sub">Contradiction detection &amp; evasion analysis for deposition transcripts</p>
    </div>

    <div class="nlp-input-card">
      <label class="nlp-field-label">Deposition or interrogation transcript</label>
      <textarea
        v-model="text"
        class="nlp-textarea nlp-textarea--lg"
        rows="14"
        placeholder="Paste transcript text…  Use Q: and A: to mark questions and answers."
      />
      <div class="nlp-input-actions">
        <button class="nlp-btn nlp-btn--ghost" :disabled="!text && !result" @click="clearAll">
          Clear
        </button>
        <button class="nlp-btn nlp-btn--ghost" @click="loadExample">Load example</button>
        <button
          class="nlp-btn"
          :disabled="loading || !text.trim()"
          @click="analyze"
        >
          {{ loading ? 'Analysing…' : 'Analyze Transcript' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="nlp-progress">
      <span class="nlp-progress__bar" />
      <span class="nlp-progress__label">Analyzing transcript…</span>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <div v-if="result" class="nlp-results">
      <!-- Key findings summary -->
      <div class="nlp-summary">
        <div class="nlp-summary__title">Key Findings</div>
        <div class="nlp-summary__grid">
          <div class="nlp-stat" :class="{ 'nlp-stat--alert': contradictionsCount > 0 }">
            <div class="nlp-stat__val">{{ contradictionsCount }}</div>
            <div class="nlp-stat__label">Contradictions</div>
          </div>
          <div class="nlp-stat" :class="{ 'nlp-stat--warn': evasionsCount > 0 }">
            <div class="nlp-stat__val">{{ evasionsCount }}</div>
            <div class="nlp-stat__label">Evasions Detected</div>
          </div>
          <div class="nlp-stat" v-if="consistencyScore != null">
            <div class="nlp-stat__val" :style="{ color: scoreColor(consistencyScore) }">
              {{ consistencyScore }}<span class="nlp-stat__pct">%</span>
            </div>
            <div class="nlp-stat__label">Consistency Score</div>
          </div>
        </div>
        <div v-if="result.summary" class="nlp-summary__text">{{ result.summary }}</div>
      </div>

      <NlpResultCard :result="result" title="Contradictions &amp; Evasions" />
    </div>
  </div>
</template>

<style scoped>
.nlp-mod { padding: 2rem; max-width: 960px; }
.nlp-mod__header { margin-bottom: 1.5rem; }
.nlp-mod__title { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.nlp-mod__sub { color: var(--text-muted); font-size: .85rem; margin: .25rem 0 0; }

.nlp-input-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.25rem; }
.nlp-field-label { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; font-weight: 600; display: block; margin-bottom: .5rem; }
.nlp-textarea { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; box-sizing: border-box; color: var(--text-primary); font-family: var(--font-mono); font-size: .85rem; line-height: 1.6; padding: .75rem; resize: vertical; width: 100%; }
.nlp-textarea--lg { min-height: 220px; }
.nlp-textarea:focus { border-color: var(--gold); outline: none; }

.nlp-input-actions { display: flex; justify-content: flex-end; gap: .5rem; margin-top: .75rem; flex-wrap: wrap; }
.nlp-btn { background: var(--gold); border: none; border-radius: 6px; color: #000; cursor: pointer; font-size: .875rem; font-weight: 600; padding: .55rem 1.4rem; transition: opacity .2s; }
.nlp-btn:hover:not(:disabled) { opacity: .85; }
.nlp-btn:disabled { cursor: not-allowed; opacity: .4; }
.nlp-btn--ghost { background: transparent; border: 1px solid var(--border); color: var(--text-muted); }
.nlp-btn--ghost:hover:not(:disabled) { border-color: var(--gold); color: var(--gold); opacity: 1; }

.nlp-progress { display: flex; align-items: center; gap: .75rem; margin-bottom: 1.25rem; color: var(--text-muted); font-size: .8rem; }
.nlp-progress__bar { width: 14px; height: 14px; border: 2px solid var(--gold); border-top-color: transparent; border-radius: 50%; animation: nlp-spin .7s linear infinite; }
@keyframes nlp-spin { to { transform: rotate(360deg); } }

.nlp-err { color: #fc8181; font-size: .875rem; margin-bottom: 1rem; background: rgba(252,129,129,.07); border: 1px solid rgba(252,129,129,.25); border-radius: 6px; padding: .6rem .8rem; }

.nlp-results { display: flex; flex-direction: column; gap: 1rem; }

.nlp-summary { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; }
.nlp-summary__title { font-size: .72rem; color: var(--text-muted); font-weight: 600; letter-spacing: .06em; text-transform: uppercase; margin-bottom: 1rem; }
.nlp-summary__grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; }
.nlp-stat { background: var(--bg-raised, #0d0d1a); border: 1px solid var(--border); border-radius: 6px; padding: 1rem; text-align: center; }
.nlp-stat--alert { border-left: 3px solid #fc8181; border-radius: 0 6px 6px 0; }
.nlp-stat--warn { border-left: 3px solid #ecc94b; border-radius: 0 6px 6px 0; }
.nlp-stat__val { font-size: 2.2rem; font-weight: 700; line-height: 1; color: var(--text-primary); }
.nlp-stat__pct { font-size: 1.1rem; }
.nlp-stat__label { font-size: .72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; margin-top: .4rem; }
.nlp-summary__text { color: var(--text-primary); font-size: .875rem; line-height: 1.65; margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--border); }
</style>
