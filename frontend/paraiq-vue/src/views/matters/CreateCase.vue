<template>
  <div class="create-case-page">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="back-icon">←</span> Back
      </button>
      <div class="header-text">
        <h1>New Matter</h1>
        <p class="subtitle">Create a new client matter</p>
      </div>
    </div>

    <!-- ── POST-CREATION UPLOAD STEP ─────────────────────────────────── -->
    <div v-if="createdMatter" class="success-card">
      <div class="success-card__icon">✓</div>
      <div class="success-card__body">
        <div class="success-card__title">Matter Created</div>
        <div class="success-card__meta">
          <span class="mono">{{ createdMatter.case_number }}</span>
          <span class="dim">·</span>
          <span>{{ createdMatter.client_name }}</span>
        </div>
        <p class="success-card__sub">
          Upload initial client documents now, or skip and add them later from the matter page.
        </p>
      </div>
      <div class="success-card__actions">
        <button class="btn-upload-lg" @click="showUpload = true">
          ↑ Upload Initial Documents
        </button>
        <button class="btn-secondary" @click="goToMatter">
          Open Matter →
        </button>
      </div>
    </div>

    <!-- ── CREATION FORM (hidden once matter is created) ─────────────── -->
    <div v-else class="form-container">
      <form @submit.prevent="submitCase">

        <!-- BASIC INFO -->
        <section class="form-section">
          <h2 class="section-title">Matter Details</h2>
          <div class="field-grid">
            <div class="field full-width">
              <label>Matter Name <span class="required">*</span></label>
              <input
                v-model="form.case_name"
                type="text"
                placeholder="e.g. Smith v. Acme Corp — Wrongful Termination"
                :class="{ 'error': errors.case_name }"
                @input="clearError('case_name')"
              />
              <span v-if="errors.case_name" class="field-error">{{ errors.case_name }}</span>
            </div>

            <div class="field">
              <label>Case / Matter Number</label>
              <input v-model="form.case_number" type="text" placeholder="2025-CV-00123" />
            </div>

            <div class="field">
              <label>Case Type <span class="required">*</span></label>
              <select v-model="form.case_type" :class="{ 'error': errors.case_type }" @change="clearError('case_type')">
                <option value="">— Select type —</option>
                <option v-for="t in caseTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
              </select>
              <span v-if="errors.case_type" class="field-error">{{ errors.case_type }}</span>
            </div>

            <div class="field">
              <label>Status</label>
              <select v-model="form.status">
                <option value="active">Active</option>
                <option value="pending">Pending</option>
                <option value="closed">Closed</option>
                <option value="on_hold">On Hold</option>
              </select>
            </div>

            <div class="field">
              <label>Jurisdiction</label>
              <input v-model="form.jurisdiction" type="text" placeholder="e.g. SDNY, California Superior Court" />
            </div>

            <div class="field">
              <label>Date Filed</label>
              <input v-model="form.date_filed" type="date" />
            </div>
          </div>
        </section>

        <!-- CLIENT INFO -->
        <section class="form-section">
          <h2 class="section-title">Client Information</h2>
          <div class="field-grid">
            <div class="field">
              <label>Client Name <span class="required">*</span></label>
              <input
                v-model="form.client_name"
                type="text"
                placeholder="Full legal name or entity"
                :class="{ 'error': errors.client_name }"
                @input="clearError('client_name')"
              />
              <span v-if="errors.client_name" class="field-error">{{ errors.client_name }}</span>
            </div>

            <div class="field">
              <label>Opposing Party</label>
              <input v-model="form.opposing_party" type="text" placeholder="Defendant / Respondent name" />
            </div>

            <div class="field">
              <label>Client Email</label>
              <input v-model="form.client_email" type="email" placeholder="client@example.com" />
            </div>

            <div class="field">
              <label>Client Phone</label>
              <input v-model="form.client_phone" type="tel" placeholder="+1 (212) 555-0100" />
            </div>
          </div>
        </section>

        <!-- ATTORNEY ASSIGNMENT -->
        <section class="form-section">
          <h2 class="section-title">Assignment</h2>
          <div class="field-grid">
            <div class="field">
              <label>Lead Attorney</label>
              <input v-model="form.lead_attorney" type="text" placeholder="Attorney name" />
            </div>

            <div class="field">
              <label>Billing Rate ($/hr)</label>
              <input v-model="form.billing_rate" type="number" min="0" step="25" placeholder="350" />
            </div>

            <div class="field">
              <label>Retainer Amount ($)</label>
              <input v-model="form.retainer_amount" type="number" min="0" step="100" placeholder="5000" />
            </div>

            <div class="field">
              <label>Statute of Limitations</label>
              <input v-model="form.sol_date" type="date" />
            </div>
          </div>
        </section>

        <!-- DESCRIPTION -->
        <section class="form-section">
          <h2 class="section-title">Case Summary</h2>
          <div class="field full-width">
            <label>Description / Notes</label>
            <textarea
              v-model="form.description"
              rows="5"
              placeholder="Brief summary of the matter, key facts, and initial legal theories..."
            ></textarea>
            <span class="char-count">{{ form.description.length }} characters</span>
          </div>
        </section>

        <!-- ACTIONS -->
        <div class="form-actions">
          <button type="button" class="btn-secondary" @click="$router.back()">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="submitting">
            <span v-if="submitting" class="spinner"></span>
            <span v-else>Create Matter</span>
          </button>
        </div>

        <!-- API ERROR -->
        <div v-if="apiError" class="api-error">
          <span class="error-icon">⚠</span> {{ apiError }}
        </div>

      </form>
    </div>

    <!-- Discovery Upload — opens after matter creation, pre-scoped -->
    <DiscoveryUpload
      v-if="createdMatter"
      :show="showUpload"
      :matter-id="createdMatter.id"
      :matter-name="createdMatter.client_name"
      :case-number="createdMatter.case_number"
      @close="showUpload = false"
      @uploaded="onUploaded"
    />

  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import DiscoveryUpload from '@/components/DiscoveryUpload.vue'

const router     = useRouter()
const submitting = ref(false)
const apiError   = ref('')

// ── Post-creation state ────────────────────────────────────────────────────
const createdMatter  = ref(null)   // set after successful POST
const showUpload     = ref(false)
const uploadDone     = ref(false)

function goToMatter() {
  router.push('/matters/' + createdMatter.value.id)
}

function onUploaded() {
  uploadDone.value = true
  showUpload.value = false
  // Give user a moment to see the success state then navigate
  setTimeout(goToMatter, 1200)
}

// ── Case types ─────────────────────────────────────────────────────────────
const caseTypes = [
  { value: 'employment',       label: 'Employment Law' },
  { value: 'civil_litigation', label: 'Civil Litigation' },
  { value: 'contract_dispute', label: 'Contract Dispute' },
  { value: 'personal_injury',  label: 'Personal Injury / Tort' },
  { value: 'corporate',        label: 'Corporate / Business' },
  { value: 'real_estate',      label: 'Real Estate' },
  { value: 'family_law',       label: 'Family Law' },
  { value: 'criminal_defense', label: 'Criminal Defense' },
  { value: 'immigration',      label: 'Immigration' },
  { value: 'IP',               label: 'Intellectual Property' },
  { value: 'bankruptcy',       label: 'Bankruptcy' },
  { value: 'regulatory',       label: 'Regulatory / Compliance' },
  { value: 'other',            label: 'Other' },
]

const form = reactive({
  case_name: '', case_number: '', case_type: '', status: 'active',
  jurisdiction: '', date_filed: '', client_name: '', client_email: '',
  client_phone: '', opposing_party: '', lead_attorney: '',
  billing_rate: '', retainer_amount: '', sol_date: '', description: '',
})

const errors = reactive({})
function clearError(field) { delete errors[field] }

function validate() {
  let valid = true
  if (!form.case_name.trim())   { errors.case_name   = 'Matter name is required';  valid = false }
  if (!form.case_type)          { errors.case_type   = 'Case type is required';    valid = false }
  if (!form.client_name.trim()) { errors.client_name = 'Client name is required';  valid = false }
  return valid
}

async function submitCase() {
  apiError.value = ''
  if (!validate()) return

  submitting.value = true
  const token = localStorage.getItem('paraiq_token')

  try {
    const caseNum = form.case_number.trim() ||
      `${new Date().getFullYear()}-CV-${Math.floor(Math.random()*90000+10000)}`

    const extras = []
    if (form.case_type)       extras.push(`Type: ${form.case_type}`)
    if (form.opposing_party)  extras.push(`Opposing Party: ${form.opposing_party.trim()}`)
    if (form.lead_attorney)   extras.push(`Lead Attorney: ${form.lead_attorney.trim()}`)
    if (form.billing_rate)    extras.push(`Billing Rate: $${form.billing_rate}/hr`)
    if (form.retainer_amount) extras.push(`Retainer: $${form.retainer_amount}`)
    if (form.sol_date)        extras.push(`SOL: ${form.sol_date}`)
    if (form.client_email)    extras.push(`Email: ${form.client_email.trim()}`)
    if (form.client_phone)    extras.push(`Phone: ${form.client_phone.trim()}`)
    const fullDesc = [extras.join(' | '), form.description.trim()].filter(Boolean).join('\n')

    const payload = {
      case_number:   caseNum,
      client_name:   form.client_name.trim(),
      matter_number: form.case_name.trim(),
      status:        form.status === 'active' ? 'open' : form.status,
      court:         form.jurisdiction.trim(),
      filing_date:   form.date_filed || '',
      description:   fullDesc,
      tags:          form.case_type ? [form.case_type] : [],
    }

    const res = await fetch('/api/cases/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.detail || `Server error ${res.status}`)
    }

    const created = await res.json()
    // Show upload step instead of immediately navigating
    createdMatter.value = {
      id:           created.id,
      client_name:  form.client_name.trim(),
      case_number:  caseNum,
    }

  } catch (e) {
    apiError.value = e.message || 'Failed to create matter. Please try again.'
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.create-case-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px 20px 60px;
}

/* Page header */
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 32px; }
.back-btn { display: flex; align-items: center; gap: 6px; background: transparent; border: 1px solid var(--border-color, #2a2a3a); color: var(--text-muted, #888); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; transition: all 0.15s; white-space: nowrap; }
.back-btn:hover { background: var(--surface-hover, #1a1a2e); color: var(--text-primary, #e0e0e0); }
.header-text h1 { font-size: 24px; font-weight: 700; color: var(--text-primary, #e0e0e0); margin: 0 0 4px; }
.subtitle { font-size: 13px; color: var(--text-muted, #888); margin: 0; }

/* Success / upload step */
.success-card {
  background: var(--surface, #111122);
  border: 1px solid rgba(201,168,76,0.4);
  border-radius: 14px;
  padding: 2.5rem 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 1.25rem;
  box-shadow: 0 8px 32px rgba(201,168,76,0.08);
}
.success-card__icon  { font-size: 2.5rem; color: var(--gold, #c9a84c); line-height: 1; }
.success-card__title { font-family: var(--font-display); font-size: 1.4rem; color: var(--gold, #c9a84c); font-weight: 700; margin: 0; }
.success-card__meta  { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-primary); }
.success-card__sub   { color: var(--text-muted); font-size: 0.875rem; max-width: 420px; line-height: 1.6; margin: 0; }
.success-card__actions { display: flex; gap: 0.75rem; flex-wrap: wrap; justify-content: center; margin-top: 0.5rem; }

.btn-upload-lg {
  background: var(--gold, #c9a84c);
  border: none;
  border-radius: 8px;
  color: #0a0a14;
  cursor: pointer;
  font-size: 0.9rem;
  font-weight: 700;
  padding: 0.7rem 1.75rem;
  transition: opacity 0.15s, box-shadow 0.15s;
  white-space: nowrap;
}
.btn-upload-lg:hover { opacity: 0.88; box-shadow: 0 4px 16px rgba(201,168,76,0.35); }

/* Form */
.form-container { background: var(--surface, #111122); border: 1px solid var(--border-color, #2a2a3a); border-radius: 12px; overflow: hidden; }
.form-section { padding: 28px 32px; border-bottom: 1px solid var(--border-color, #1e1e30); }
.form-section:last-of-type { border-bottom: none; }
.section-title { font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--accent, #7b6ff0); margin: 0 0 20px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.field { display: flex; flex-direction: column; gap: 6px; position: relative; }
.field.full-width { grid-column: 1 / -1; }
label { font-size: 12px; font-weight: 500; color: var(--text-muted, #aaa); text-transform: uppercase; letter-spacing: 0.05em; }
.required { color: #e05555; margin-left: 2px; }
input, select, textarea { background: var(--input-bg, #0d0d1a); border: 1px solid var(--border-color, #2a2a3a); border-radius: 8px; color: var(--text-primary, #e0e0e0); font-size: 14px; padding: 10px 14px; outline: none; transition: border-color 0.15s, box-shadow 0.15s; font-family: inherit; width: 100%; box-sizing: border-box; }
input:focus, select:focus, textarea:focus { border-color: var(--accent, #7b6ff0); box-shadow: 0 0 0 3px rgba(123,111,240,0.12); }
input.error, select.error { border-color: #e05555; }
input::placeholder, textarea::placeholder { color: var(--text-muted, #555); }
select option { background: var(--surface, #111122); }
textarea { resize: vertical; min-height: 100px; }
.field-error { font-size: 11px; color: #e05555; }
.char-count  { font-size: 11px; color: var(--text-muted, #555); text-align: right; }

.form-actions { display: flex; align-items: center; justify-content: flex-end; gap: 12px; padding: 24px 32px; border-top: 1px solid var(--border-color, #1e1e30); }
.btn-secondary { background: transparent; border: 1px solid var(--border-color, #2a2a3a); color: var(--text-muted, #aaa); padding: 10px 24px; border-radius: 8px; font-size: 14px; cursor: pointer; transition: all 0.15s; white-space: nowrap; }
.btn-secondary:hover { background: var(--surface-hover, #1a1a2e); color: var(--text-primary, #e0e0e0); }
.btn-primary { background: var(--accent, #7b6ff0); border: none; color: #fff; padding: 10px 32px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; transition: all 0.15s; display: flex; align-items: center; gap: 8px; min-width: 140px; justify-content: center; }
.btn-primary:hover:not(:disabled) { background: #9088f5; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(123,111,240,0.35); }
.btn-primary:disabled { opacity: 0.6; cursor: not-allowed; }

.spinner { width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.api-error { margin: 0 32px 24px; background: rgba(224,85,85,0.1); border: 1px solid rgba(224,85,85,0.3); border-radius: 8px; padding: 12px 16px; color: #e07070; font-size: 13px; display: flex; align-items: center; gap: 8px; }
.error-icon { font-size: 16px; }

.dim  { color: var(--text-muted); }
.mono { font-family: var(--font-mono); font-size: 0.85rem; }

@media (max-width: 640px) {
  .field-grid { grid-template-columns: 1fr; }
  .form-section { padding: 20px 16px; }
  .form-actions { padding: 20px 16px; }
}
</style>
