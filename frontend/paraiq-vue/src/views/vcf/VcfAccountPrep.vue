<template>
  <div class="vcf">
    <header class="vcf__head">
      <div>
        <h1 class="vcf__title">VCF Account Creation</h1>
        <p class="vcf__sub">
          Prepare a copy-paste-ready registration sheet, open the VCF portal in a
          side-by-side window, and fill the form by hand — VCF requires human entry.
        </p>
      </div>
      <button class="btn btn--gold" @click="openVcfWindow">
        Open VCF portal (left half)
      </button>
    </header>

    <p class="vcf__note">
      VCF supports only <strong>Chrome or Edge</strong>. The portal opens in a
      separate window on the left; keep this prep sheet on the right
      (Win + →&nbsp;snaps this window right).
    </p>

    <!-- STEP 1 · Intake source -->
    <section class="card">
      <h2 class="card__title">1 · Client data</h2>
      <div class="tabs">
        <button :class="['tab', mode==='paste' && 'tab--on']" @click="mode='paste'">
          From OCR / questionnaire text
        </button>
        <button :class="['tab', mode==='scan' && 'tab--on']" @click="loadScans">
          From intake scan
        </button>
        <button :class="['tab', mode==='manual' && 'tab--on']" @click="mode='manual'">
          Enter manually
        </button>
      </div>

      <div v-if="mode==='paste'">
        <textarea
          v-model="rawText"
          class="vcf__textarea"
          rows="6"
          placeholder="Paste OCR output of the intake questionnaire here (Chinese or English). It will be translated and structured into English registration fields."
        />
        <button class="btn" :disabled="busy || rawText.trim().length < 10" @click="extract">
          {{ busy === 'extract' ? 'Extracting…' : 'Extract & translate' }}
        </button>
        <div v-if="extractWarnings.length" class="warn">
          <strong>Check these before generating:</strong>
          <span>{{ extractWarnings.join(' · ') }}</span>
        </div>
      </div>

      <div v-if="mode==='scan'" class="scans">
        <p v-if="busy==='scans'" class="scans__empty">Loading recent scans…</p>
        <p v-else-if="!scans.length" class="scans__empty">
          No intake scans yet. Upload a questionnaire in OCR Intake first.
        </p>
        <div v-for="s in scans" :key="s.id" class="scans__row">
          <span class="scans__id">#{{ s.id }}</span>
          <span class="scans__file">{{ s.filename }}</span>
          <span class="scans__meta">{{ s.ocr_engine }} · {{ s.confidence }}%</span>
          <button type="button" class="crow__btn scans__use" :disabled="busy"
                  :data-scan-id="s.id"
                  @click="() => handleUseScan(s.id)"
                  @mousedown="() => onUseMouseDown(s.id)">
            {{ busy === 'scan' + s.id ? 'extracting…' : 'use' }}
          </button>
        </div>
        <div v-if="extractWarnings.length" class="warn">
          <strong>Check these before generating:</strong>
          <span>{{ extractWarnings.join(' · ') }}</span>
        </div>
      </div>

      <div class="grid">
        <label v-for="f in clientFields" :key="f.key" class="field">
          <span class="field__label">{{ f.label }}</span>
          <input v-model="client[f.key]" class="field__input" :placeholder="f.ph || ''" />
        </label>
      </div>
    </section>

    <!-- STEP 2 · Generate -->
    <section class="card">
      <h2 class="card__title">2 · Generate prep sheet</h2>
      <label class="check">
        <input type="checkbox" v-model="demoMode" />
        Demo mode — synthesize security-question answers
        <span class="check__hint">(real clients: confirm answers with the client, then uncheck)</span>
      </label>
      <button class="btn btn--gold" :disabled="busy || !client.first_name" @click="generate">
        {{ busy === 'prep' ? 'Generating…' : 'Generate prep sheet' }}
      </button>
    </section>

    <!-- STEP 3 · Copy-paste sheet -->
    <section v-if="prep" class="card card--sheet">
      <div class="sheet__head">
        <h2 class="card__title">3 · Copy into the VCF form</h2>
        <span class="progress">{{ copiedCount }} / {{ totalFields }} copied</span>
      </div>
      <div v-if="prep.demo_or_synth" class="banner">
        DEMO DATA — security answers are synthesized. Do not use for a real client account.
      </div>

      <h3 class="sheet__section">Account Information</h3>
      <CopyRow v-for="r in accountRows" :key="r.key"
               :label="r.label" :value="r.value" :hint="r.hint"
               :copied="copied.has(r.key)" @copy="copyField(r.key, r.value)" />

      <h3 class="sheet__section">Security Questions</h3>
      <template v-for="(q, i) in prep.security_questions" :key="'sq'+i">
        <div class="sq">
          <div class="sq__q">
            <span class="sq__n">Q{{ i + 1 }}</span>
            <span class="sq__text">{{ q.question || '— select with client —' }}</span>
            <span v-if="q.synthesized" class="chip">synthesized</span>
          </div>
          <CopyRow label="Answer" :value="q.answer"
                   :copied="copied.has('sq'+i)" @copy="copyField('sq'+i, q.answer)" />
        </div>
      </template>

      <div class="sheet__footer">
        <button class="btn btn--green" :disabled="busy" @click="markCreated">
          {{ busy === 'status' ? 'Saving…' : '✓ Account created on VCF.gov' }}
        </button>
        <span v-if="status" class="status">Status: {{ status }}</span>
      </div>
    </section>
  </div>
</template>

<script setup>
import { computed, h, reactive, ref } from 'vue'

/* Inline copy-row component (kept local; promote to components/ if reused) */
const CopyRow = {
  props: ['label', 'value', 'hint', 'copied'],
  emits: ['copy'],
  setup(props, { emit }) {
    return () => h('div', { class: 'crow' }, [
      h('span', { class: 'crow__label' }, props.label),
      h('code', { class: 'crow__value' }, props.value || '—'),
      props.hint ? h('span', { class: 'crow__hint' }, props.hint) : null,
      h('button', {
        class: ['crow__btn', props.copied && 'crow__btn--done'],
        onClick: () => emit('copy'),
        disabled: !props.value,
      }, props.copied ? '✓ copied' : 'copy'),
    ])
  },
}

const VCF_URL =
  'https://www.claims.vcf.gov/account/Register?class=btn%20btn-default%20btn-block%20content-group'

/* NOTE: swap this for your existing API helper (axios/fetch wrapper with JWT). */
async function api(path, opts = {}) {
  const token = localStorage.getItem('paraiq_token') || localStorage.getItem('token') || localStorage.getItem('jwt') || ''
  const apiKey = localStorage.getItem('paraiq_api_key') || ''
  const res = await fetch(path, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(apiKey ? { 'X-API-Key': apiKey } : {}),
      ...(opts.headers || {}),
    },
  })
  if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || res.statusText)
  return res.json()
}

const mode = ref('paste')
const scans = ref([])
const rawText = ref('')
const busy = ref('')
const demoMode = ref(true)
const extractWarnings = ref([])
const prep = ref(null)
const prepId = ref(null)
const status = ref('')
const copied = reactive(new Set())

const client = ref({
  first_name: '', last_name: '', email: '', phone: '',
  date_of_birth: '', address: '', ssn_last4: '', preferred_language: '', notes: '',
})
const clientFields = [
  { key: 'first_name', label: 'First name (English)' },
  { key: 'last_name', label: 'Last name (English)' },
  { key: 'email', label: 'Email' },
  { key: 'phone', label: 'Phone', ph: '000-000-0000' },
  { key: 'date_of_birth', label: 'Date of birth', ph: 'YYYY-MM-DD' },
  { key: 'address', label: 'Address' },
  { key: 'ssn_last4', label: 'SSN last 4', ph: '••••' },
  { key: 'preferred_language', label: 'Preferred language' },
  { key: 'notes', label: 'Notes' },
]

function openVcfWindow() {
  const w = Math.floor(window.screen.availWidth / 2)
  const hgt = window.screen.availHeight
  // vcf.gov blocks iframes (DOJ frame protection), so a real window is the way.
  window.open(VCF_URL, 'vcf_portal',
    `left=0,top=0,width=${w},height=${hgt},noopener,noreferrer`)
}

async function extract() {
  console.log('[VcfAccountPrep] extract clicked')
  busy.value = 'extract'
  extractWarnings.value = []
  try {
    const r = await api('/vcf/extract', {
      method: 'POST',
      body: JSON.stringify({ text: rawText.value }),
    })
    const c = r.client || {}
    console.log('[VcfAccountPrep] extract response:', r)
    client.value = {
      first_name: c.first_name ?? '',
      last_name: c.last_name ?? '',
      email: c.email ?? '',
      phone: c.phone ?? '',
      date_of_birth: c.date_of_birth ?? '',
      address: c.address ?? '',
      ssn_last4: c.ssn_last4 ?? '',
      preferred_language: c.preferred_language ?? '',
      notes: c.notes ?? '',
    }
    const warn = []
    if (c.missing_fields?.length) warn.push(`missing: ${c.missing_fields.join(', ')}`)
    if (c.ocr_uncertain?.length) warn.push(`uncertain OCR: ${c.ocr_uncertain.join(', ')}`)
    extractWarnings.value = warn
    mode.value = 'manual' // show populated fields for review
  } catch (e) {
    console.error('[VcfAccountPrep] extract failed:', e)
    extractWarnings.value = [String(e.message || e)]
    alert(`Could not extract: ${e.message || e}`)
  } finally { busy.value = '' }
}

async function loadScans() {
  mode.value = 'scan'
  busy.value = 'scans'
  try {
    const r = await api('/intake/history?limit=10')
    scans.value = r.scans || []
  } catch (e) {
    extractWarnings.value = [String(e.message || e)]
  } finally { busy.value = '' }
}

function handleUseScan(id) {
  console.log('[VcfAccountPrep] handleUseScan', id)
  useScan(id)
}

function onUseMouseDown(id) {
  console.log('[VcfAccountPrep] onUseMouseDown', id)
}

// Expose a global fallback so you can test directly from the browser console.
window.debugUseScan = (id) => {
  console.log('[GLOBAL] debugUseScan called', id)
  handleUseScan(Number(id))
}

async function useScan(id) {
  console.log('[VcfAccountPrep] useScan clicked, id=', id)
  busy.value = 'scan' + id
  extractWarnings.value = []
  try {
    console.log('[VcfAccountPrep] calling /vcf/from-scan/' + id)
    const r = await api(`/vcf/from-scan/${id}`, { method: 'POST' })
    const c = r.client || {}
    console.log('[VcfAccountPrep] from-scan response:', r)
    console.log('[VcfAccountPrep] client before assign:', JSON.parse(JSON.stringify(client.value)))
    client.value = {
      first_name: c.first_name ?? '',
      last_name: c.last_name ?? '',
      email: c.email ?? '',
      phone: c.phone ?? '',
      date_of_birth: c.date_of_birth ?? '',
      address: c.address ?? '',
      ssn_last4: c.ssn_last4 ?? '',
      preferred_language: c.preferred_language ?? '',
      notes: c.notes ?? '',
    }
    console.log('[VcfAccountPrep] client after assign:', JSON.parse(JSON.stringify(client.value)))
    const warn = [...(r.warnings || [])]
    if (c.missing_fields?.length) warn.push(`missing: ${c.missing_fields.join(', ')}`)
    if (c.ocr_uncertain?.length) warn.push(`uncertain OCR: ${c.ocr_uncertain.join(', ')}`)
    extractWarnings.value = warn
    mode.value = 'manual' // show populated fields for review
  } catch (e) {
    console.error('[VcfAccountPrep] from-scan failed:', e)
    extractWarnings.value = [String(e.message || e)]
    alert(`Could not load scan: ${e.message || e}`)
  } finally { busy.value = '' }
}

async function generate() {
  busy.value = 'prep'
  copied.clear()
  try {
    const r = await api('/vcf/prep', {
      method: 'POST',
      body: JSON.stringify({ client: { ...client.value }, demo_mode: demoMode.value }),
    })
    prepId.value = r.prep_id
    status.value = 'ready'
    prep.value = {
      account: r.prep.account_information,
      security_questions: r.prep.security_questions,
      demo_or_synth: r.demo_mode,
    }
  } catch (e) {
    alert(`Prep failed: ${e.message || e}`)
  } finally { busy.value = '' }
}

const accountRows = computed(() => {
  const a = prep.value?.account || {}
  return [
    { key: 'user_name', label: 'User Name', value: a.user_name },
    { key: 'email', label: 'Email', value: a.email },
    { key: 'confirm_email', label: 'Confirm email', value: a.confirm_email },
    { key: 'first_name', label: 'First Name', value: a.first_name },
    { key: 'last_name', label: 'Last Name', value: a.last_name },
    { key: 'password', label: 'Password', value: a.password, hint: a.password_policy },
    { key: 'confirm_password', label: 'Confirm password', value: a.confirm_password },
  ]
})
const totalFields = computed(() =>
  accountRows.value.length + (prep.value?.security_questions?.length || 0))
const copiedCount = computed(() => copied.size)

async function copyField(key, value) {
  try {
    await navigator.clipboard.writeText(value || '')
    copied.add(key)
  } catch { /* clipboard blocked; user can select manually */ }
}

async function markCreated() {
  if (!prepId.value) return
  busy.value = 'status'
  try {
    await api(`/vcf/prep/${prepId.value}/status`, {
      method: 'PATCH',
      body: JSON.stringify({
        status: 'account_created',
        vcf_username: prep.value?.account?.user_name || null,
      }),
    })
    status.value = 'account_created'
  } catch (e) {
    alert(`Status update failed: ${e.message || e}`)
  } finally { busy.value = '' }
}
</script>

<style scoped>
.vcf { padding: 24px; max-width: 860px; }
.vcf__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; }
.vcf__title { font-family: var(--font-display); font-weight: 300; letter-spacing: .06em;
  color: var(--gold); font-size: 24px; margin: 0; }
.vcf__sub { color: var(--text-secondary); font-size: 13px; margin: 6px 0 0; max-width: 520px; }
.vcf__note { font-size: 12px; color: var(--text-tertiary); margin: 12px 0 20px; }
.vcf__textarea { width: 100%; background: var(--bg-void); border: 1px solid var(--border-dim);
  color: var(--text-primary, #eee); border-radius: 8px; padding: 10px 12px; font-size: 13px;
  margin-bottom: 10px; resize: vertical; }

.card { background: var(--bg-overlay, rgba(255,255,255,.02)); border: 1px solid var(--border-dim);
  border-radius: 12px; padding: 18px 20px; margin-bottom: 18px; }
.card__title { font-size: 14px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--text-secondary); margin: 0 0 14px; }

.tabs { display: flex; gap: 8px; margin-bottom: 12px; }
.tab { background: none; border: 1px solid var(--border-dim); color: var(--text-secondary);
  border-radius: 100px; padding: 4px 14px; font-size: 12px; cursor: pointer; }
.tab--on { border-color: var(--gold); color: var(--gold); background: var(--gold-glow, rgba(212,175,55,.08)); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px 14px; margin-top: 14px; }
.field__label { display: block; font-size: 11px; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: .05em; margin-bottom: 3px; }
.field__input { width: 100%; background: var(--bg-void); border: 1px solid var(--border-dim);
  color: var(--text-primary, #eee); border-radius: 6px; padding: 7px 10px; font-size: 13px; }

.check { display: block; font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; }
.check__hint { color: var(--text-tertiary); font-size: 11px; margin-left: 6px; }

.btn { background: var(--bg-void); border: 1px solid var(--border-dim); color: var(--text-secondary);
  border-radius: 8px; padding: 8px 16px; font-size: 13px; cursor: pointer; }
.btn:disabled { opacity: .45; cursor: default; }
.btn--gold { border-color: var(--gold); color: var(--gold); }
.btn--green { border-color: var(--green, #3ecf8e); color: var(--green, #3ecf8e); }

.warn { margin-top: 10px; font-size: 12px; color: #e6b25a; border: 1px solid rgba(230,178,90,.35);
  border-radius: 8px; padding: 8px 12px; display: flex; gap: 8px; flex-wrap: wrap; }
.banner { border: 1px solid rgba(230,90,90,.5); color: #e67a7a; font-size: 12px;
  border-radius: 8px; padding: 8px 12px; margin-bottom: 14px; letter-spacing: .04em; }

.sheet__head { display: flex; justify-content: space-between; align-items: baseline; }
.progress { font-size: 12px; color: var(--gold); }
.sheet__section { font-size: 12px; text-transform: uppercase; letter-spacing: .08em;
  color: var(--gold); margin: 18px 0 8px; }

:deep(.crow) { display: grid; grid-template-columns: 140px 1fr auto; align-items: center;
  gap: 10px; padding: 7px 0; border-bottom: 1px solid var(--border-dim); }
:deep(.crow__label) { font-size: 12px; color: var(--text-tertiary); }
:deep(.crow__value) { font-size: 13px; color: var(--text-primary, #eee);
  background: var(--bg-void); border-radius: 6px; padding: 5px 10px; overflow-wrap: anywhere; }
:deep(.crow__hint) { grid-column: 2; font-size: 10px; color: var(--text-tertiary); }
:deep(.crow__btn) { background: none; border: 1px solid var(--border-dim);
  color: var(--text-secondary); border-radius: 100px; padding: 3px 12px; font-size: 11px; cursor: pointer; }
:deep(.crow__btn--done) { border-color: var(--green, #3ecf8e); color: var(--green, #3ecf8e); }

.sq { margin-bottom: 10px; }
.sq__q { display: flex; align-items: center; gap: 8px; font-size: 13px; margin-bottom: 2px; }
.sq__n { color: var(--gold); font-size: 11px; }
.sq__text { color: var(--text-primary, #eee); }
.chip { font-size: 10px; border: 1px solid var(--border-dim); color: var(--text-tertiary);
  border-radius: 100px; padding: 1px 8px; }

.scans { margin-bottom: 12px; }
.scans__empty { font-size: 12px; color: var(--text-tertiary); }
.scans__row { display: grid; grid-template-columns: 48px 1fr auto auto; align-items: center;
  gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--border-dim); font-size: 13px; }
.scans__id { color: var(--gold); font-size: 11px; }
.scans__file { color: var(--text-primary, #eee); overflow-wrap: anywhere; }
.scans__meta { color: var(--text-tertiary); font-size: 11px; }
.scans__use { pointer-events: auto; position: relative; z-index: 1; }

.sheet__footer { display: flex; align-items: center; gap: 14px; margin-top: 18px; }
.status { font-size: 12px; color: var(--text-secondary); }
</style>
