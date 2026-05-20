<script setup>
import { ref, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const config  = ref({})
const loading = ref(false)
const saving  = ref(false)
const saved   = ref(false)

const MODELS = [
  'claude-opus-4-5',
  'claude-sonnet-4-5',
  'claude-haiku-4-5-20251001',
  'gpt-4o',
  'gpt-4o-mini',
]

const MODEL_SETTINGS = [
  { key: 'ai_model',            label: 'Default Model' },
  { key: 'brief_model',         label: 'Case Brief' },
  { key: 'contradiction_model', label: 'Contradictions' },
  { key: 'timeline_model',      label: 'Timeline' },
]

const FEATURE_TOGGLES = [
  { key: 'enable_legal_bert',     label: 'Legal-BERT Analysis' },
  { key: 'enable_auto_brief',     label: 'Auto Case Brief' },
  { key: 'enable_contradictions', label: 'Contradiction Engine' },
  { key: 'enable_deadline_radar', label: 'Deadline Radar' },
  { key: 'enclave_enabled',       label: 'Privilege Enclave' },
]

async function fetchConfig() {
  loading.value = true
  try {
    const { data } = await client.get('/ai-config/' + firmId())
    config.value = data
  } catch {} finally { loading.value = false }
}

async function save() {
  saving.value = true; saved.value = false
  try {
    await client.put('/ai-config/' + firmId(),  { settings: config.value })
    saved.value = true
    setTimeout(() => { saved.value = false }, 2500)
  } catch {} finally { saving.value = false }
}

async function reset() {
  if (!confirm('Reset all AI settings to defaults?')) return
  await client.post('/ai-config/' + firmId() + '/reset', null)
  fetchConfig()
}

function isEnabled(key) { return config.value[key] === 'true' }
function toggleFeature(key) { config.value[key] = isEnabled(key) ? 'false' : 'true' }

onMounted(fetchConfig)
</script>

<template>
  <div class="cfg">
    <div class="cfg__header">
      <div>
        <h1 class="cfg__title">AI Configuration</h1>
        <p class="cfg__sub">Model selection · feature toggles · inference settings</p>
      </div>
      <div class="header-actions">
        <button class="btn-secondary" @click="reset">Reset Defaults</button>
        <button class="btn-gold" @click="save" :disabled="saving">
          {{ saving ? 'Saving…' : saved ? '✓ Saved' : 'Save Settings' }}
        </button>
      </div>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else class="cfg-sections">

      <!-- Model Selection -->
      <div class="cfg-section">
        <div class="section-title">Model Selection</div>
        <div class="setting-grid">
          <div v-for="s in MODEL_SETTINGS" :key="s.key" class="setting-row">
            <div class="setting-label">{{ s.label }}</div>
            <select class="setting-select" v-model="config[s.key]">
              <option v-for="m in MODELS" :key="m" :value="m">{{ m }}</option>
            </select>
          </div>
        </div>
      </div>

      <!-- Feature Toggles -->
      <div class="cfg-section">
        <div class="section-title">Features</div>
        <div class="toggle-grid">
          <div v-for="f in FEATURE_TOGGLES" :key="f.key" class="toggle-row">
            <div class="toggle-label">{{ f.label }}</div>
            <button
              class="toggle-btn"
              :class="{ on: isEnabled(f.key) }"
              @click="toggleFeature(f.key)"
            >
              <span class="toggle-knob"></span>
            </button>
          </div>
        </div>
      </div>

      <!-- Inference Settings -->
      <div class="cfg-section">
        <div class="section-title">Inference Settings</div>
        <div class="setting-grid">
          <div class="setting-row">
            <div class="setting-label">Privilege Threshold</div>
            <div class="range-wrap">
              <input type="range" min="0.1" max="1.0" step="0.05"
                :value="config.privilege_threshold"
                @input="config.privilege_threshold = $event.target.value"
                class="range-input" />
              <span class="range-val">{{ config.privilege_threshold }}</span>
            </div>
          </div>
          <div class="setting-row">
            <div class="setting-label">Max Tokens</div>
            <select class="setting-select" v-model="config.max_tokens">
              <option v-for="v in ['1000','2000','4000','8000','16000']" :key="v" :value="v">{{ v }}</option>
            </select>
          </div>
          <div class="setting-row">
            <div class="setting-label">Temperature</div>
            <div class="range-wrap">
              <input type="range" min="0.0" max="1.0" step="0.05"
                :value="config.temperature"
                @input="config.temperature = $event.target.value"
                class="range-input" />
              <span class="range-val">{{ config.temperature }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Enclave URL (conditional) -->
      <div v-if="isEnabled('enclave_enabled')" class="cfg-section">
        <div class="section-title">Enclave URL</div>
        <input class="full-input" v-model="config.enclave_url" placeholder="https://enclave.yourdomain.com" />
      </div>

    </div>
  </div>
</template>

<style scoped>
.cfg { padding: 2rem; max-width: 720px; }
.cfg__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.5rem; gap: 1rem; flex-wrap: wrap; }
.cfg__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.cfg__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }
.header-actions { display: flex; gap: 0.75rem; flex-shrink: 0; }
.cfg-sections { display: flex; flex-direction: column; gap: 1.25rem; }
.cfg-section { background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem 1.5rem; }
.section-title { color: var(--text-muted); font-size: 0.72rem; font-weight: 600; letter-spacing: .08em; margin-bottom: 1rem; text-transform: uppercase; }

.setting-grid { display: flex; flex-direction: column; gap: 0.85rem; }
.setting-row  { align-items: center; display: flex; justify-content: space-between; gap: 1rem; }
.setting-label { color: var(--text-primary); font-size: 0.875rem; }
.setting-select { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; }
.range-wrap  { align-items: center; display: flex; gap: 0.75rem; }
.range-input { accent-color: var(--gold); width: 160px; }
.range-val   { color: var(--text-primary); font-size: 0.85rem; font-weight: 600; min-width: 36px; text-align: right; }

.toggle-grid { display: flex; flex-direction: column; gap: 0.85rem; }
.toggle-row  { align-items: center; display: flex; justify-content: space-between; }
.toggle-label { color: var(--text-primary); font-size: 0.875rem; }
.toggle-btn  { background: var(--border); border: none; border-radius: 12px; cursor: pointer; height: 24px; position: relative; transition: background .2s; width: 44px; flex-shrink: 0; }
.toggle-btn.on { background: var(--gold); }
.toggle-knob { background: #fff; border-radius: 50%; display: block; height: 18px; left: 3px; position: absolute; top: 3px; transition: transform .2s; width: 18px; }
.toggle-btn.on .toggle-knob { transform: translateX(20px); }

.full-input { background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.875rem; outline: none; padding: 0.5rem 0.75rem; width: 100%; box-sizing: border-box; }
.full-input:focus { border-color: var(--gold); }

.btn-gold { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; white-space: nowrap; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.8rem; padding: 0.5rem 1rem; transition: all .15s; white-space: nowrap; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
</style>
