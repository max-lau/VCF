<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text     = ref('')
const lang     = ref('auto')
const result   = ref(null)
const loading  = ref(false)
const error   = ref(null)
const langs    = ref([{ code: 'auto', name: 'Auto-detect' }])

const detectedLang = computed(() => result.value?.language || result.value?.detected_language || null)
const translation  = computed(() => result.value?.translation || result.value?.translated_text || null)

async function analyze() {
  if (!text.value.trim()) return
  loading.value = true
  error.value   = null
  result.value  = null
  try {
    const { data } = await client.post('/multilingual/analyze', {
      text: text.value,
      lang: lang.value === 'auto' ? undefined : lang.value,
    })
    result.value = data
  } catch (e) {
    error.value = e.response?.data?.detail || 'Multilingual analysis failed'
  } finally {
    loading.value = false
  }
}

async function fetchLanguages() {
  try {
    const { data } = await client.get('/multilingual/languages')
    const list = data?.languages || data || []
    const normalized = Array.isArray(list)
      ? list.map(l => typeof l === 'string' ? { code: l, name: l.toUpperCase() } : l)
      : Object.entries(list).map(([code, name]) => ({ code, name }))
    langs.value = [{ code: 'auto', name: 'Auto-detect' }, ...normalized]
  } catch {
    langs.value = [
      { code: 'auto', name: 'Auto-detect' },
      { code: 'en', name: 'English' },
      { code: 'es', name: 'Spanish' },
      { code: 'fr', name: 'French' },
      { code: 'de', name: 'German' },
      { code: 'zh', name: 'Chinese' },
    ]
  }
}

onMounted(fetchLanguages)
</script>

<template>
  <div class="nlp-mod" style="max-width:950px">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Multilingual Analysis</h1>
      <p class="nlp-mod__sub">Cross-language NLP — auto-detect or specify a language</p>
    </div>

    <div class="nlp-top-bar">
      <div class="ml-lang-selector">
        <label class="nlp-field-label" style="margin:0">Language</label>
        <select v-model="lang" class="nlp-select">
          <option v-for="l in langs" :key="l.code" :value="l.code">
            {{ l.name === 'Auto-detect' ? 'Auto-detect' : (l.name + (l.code !== l.name ? ' (' + l.code.toUpperCase() + ')' : '')) }}
          </option>
        </select>
      </div>
      <div v-if="detectedLang" class="ml-lang-badge">
        Detected: <strong>{{ detectedLang.toUpperCase() }}</strong>
      </div>
    </div>

    <div class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="10"
        placeholder="Paste text in any language…" />
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading || !text.trim()" @click="analyze">
          {{ loading ? 'Analysing…' : 'Analyze' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <template v-if="result">
      <NlpResultCard :result="result" title="Analysis Result" />

      <!-- Translation section -->
      <div v-if="translation" class="ml-translation-card">
        <div class="ml-translation-card__head">
          <span class="ml-translation-card__title">Translation</span>
          <span v-if="result.target_language || result.translation_target"
            class="ml-translation-card__target">
            → {{ (result.target_language || result.translation_target || 'en').toUpperCase() }}
          </span>
        </div>
        <p class="ml-translation-card__body">{{ translation }}</p>
      </div>
    </template>
  </div>
</template>

<style scoped>
.ml-lang-selector { display: flex; align-items: center; gap: .6rem; }
.ml-lang-badge {
  background: var(--bg-card); border: 1px solid var(--gold, #c9a84c);
  border-radius: 6px; color: var(--gold, #c9a84c); font-size: .78rem;
  font-weight: 600; padding: .35rem .7rem;
}

.ml-translation-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 1.1rem 1.25rem; margin-top: 1rem;
}
.ml-translation-card__head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: .6rem;
}
.ml-translation-card__title {
  font-size: .72rem; color: var(--text-muted); font-weight: 600;
  letter-spacing: .05em; text-transform: uppercase;
}
.ml-translation-card__target {
  font-size: .72rem; color: var(--gold, #c9a84c); font-weight: 600;
}
.ml-translation-card__body {
  color: var(--text-primary); font-size: .875rem; line-height: 1.65; margin: 0;
  white-space: pre-wrap; word-break: break-word;
}
</style>
