<template>
  <div class="create-case-page">
    <div class="page-header">
      <button class="back-btn" @click="$router.back()">
        <span class="back-icon">←</span> Back
      </button>
      <div class="header-text">
        <h1>New VCF Claim</h1>
        <p class="subtitle">Create a new 9/11 Victim Compensation Fund claim</p>
      </div>
    </div>

    <!-- ── POST-CREATION SUCCESS STEP ─────────────────────────────────── -->
    <div v-if="createdClaim" class="success-card">
      <div class="success-card__icon">✓</div>
      <div class="success-card__body">
        <div class="success-card__title">Claim Created</div>
        <div class="success-card__meta">
          <span class="mono">{{ createdClaim.case_number }}</span>
          <span class="dim">·</span>
          <span>{{ createdClaim.client_name }}</span>
        </div>
        <p class="success-card__sub">
          You can now upload intake documents and track the claim through the VCF workflow.
        </p>
      </div>
      <div class="success-card__actions">
        <button class="btn-secondary" @click="goToClaim">
          Open Claim →
        </button>
      </div>
    </div>

    <!-- ── CREATION FORM ─────────────────────────────────────────────── -->
    <div v-else class="form-container">
      <form @submit.prevent="submitCase">

        <!-- CLAIM IDENTIFIERS -->
        <section class="form-section">
          <h2 class="section-title">Claim Details</h2>
          <div class="field-grid">
            <div class="field">
              <label>Claim Number <span class="required">*</span></label>
              <input
                v-model="form.case_number"
                type="text"
                placeholder="e.g. VCF-2026-00001"
                :class="{ 'error': errors.case_number }"
                @input="clearError('case_number')"
              />
              <span v-if="errors.case_number" class="field-error">{{ errors.case_number }}</span>
            </div>

            <div class="field">
              <label>Claim Stage</label>
              <select v-model="form.claim_stage">
                <option v-for="s in claimStages" :key="s" :value="s">{{ formatLabel(s) }}</option>
              </select>
            </div>

            <div class="field">
              <label>VCF Status</label>
              <select v-model="form.vcf_status">
                <option v-for="s in vcfStatuses" :key="s" :value="s">{{ formatLabel(s) }}</option>
              </select>
            </div>

            <div class="field">
              <label>Presence Proof Status</label>
              <select v-model="form.presence_proof_status">
                <option v-for="s in presenceStatuses" :key="s" :value="s">{{ formatLabel(s) }}</option>
              </select>
            </div>

            <div class="field">
              <label>Award Amount ($)</label>
              <input v-model="form.award_amount" type="number" min="0" step="0.01" placeholder="0.00" />
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
                placeholder="Full legal name"
                :class="{ 'error': errors.client_name }"
                @input="clearError('client_name')"
              />
              <span v-if="errors.client_name" class="field-error">{{ errors.client_name }}</span>
            </div>

            <div class="field">
              <label>Date of Birth</label>
              <input v-model="form.date_of_birth" type="date" />
            </div>

            <div class="field">
              <label>SSN Last 4</label>
              <input v-model="form.ssn_last4" type="text" maxlength="4" placeholder="0000" />
            </div>

            <div class="field">
              <label>Preferred Language</label>
              <input v-model="form.preferred_language" type="text" placeholder="e.g. English, Cantonese" />
            </div>
          </div>
        </section>

        <!-- EXPOSURE & ELIGIBILITY -->
        <section class="form-section">
          <h2 class="section-title">Exposure & Eligibility</h2>
          <div class="field-grid">
            <div class="field">
              <label>Exposure Location</label>
              <input v-model="form.exposure_location" type="text" placeholder="e.g. Lower Manhattan, Fresh Kills" />
            </div>

            <div class="field">
              <label>Presence Dates</label>
              <input v-model="form.presence_dates" type="text" placeholder="e.g. 09/11/2001 - 05/30/2002" />
            </div>

            <div class="field">
              <label>WTC Health Program Enrolled?</label>
              <select v-model="form.wtc_health_program">
                <option :value="true">Yes</option>
                <option :value="false">No</option>
                <option :value="null">Unknown</option>
              </select>
            </div>
          </div>
        </section>

        <!-- NOTES -->
        <section class="form-section">
          <h2 class="section-title">Notes</h2>
          <div class="field full-width">
            <label>Description / Initial Notes</label>
            <textarea
              v-model="form.description"
              rows="5"
              placeholder="Initial facts, conditions, special circumstances..."
            ></textarea>
            <span class="char-count">{{ form.description.length }} characters</span>
          </div>
        </section>

        <!-- ACTIONS -->
        <div class="form-actions">
          <button type="button" class="btn-secondary" @click="$router.back()">Cancel</button>
          <button type="submit" class="btn-primary" :disabled="submitting">
            <span v-if="submitting" class="spinner"></span>
            <span v-else>Create Claim</span>
          </button>
        </div>

        <!-- API ERROR -->
        <div v-if="apiError" class="api-error">
          <span class="error-icon">⚠</span> {{ apiError }}
        </div>

      </form>
    </div>

  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'

const router     = useRouter()
const submitting = ref(false)
const apiError   = ref('')

const createdClaim = ref(null)

function goToClaim() {
  router.push('/matters/' + createdClaim.value.id)
}

const claimStages = [
  'intake', 'eligibility_review', 'document_gathering', 'vcf_account_created',
  'claim_submitted', 'under_review', 'award_determination', 'disbursement', 'closed'
]

const vcfStatuses = [
  'pending', 'eligible', 'missing_information', 'denied', 'appealed', 'award_issued', 'paid'
]

const presenceStatuses = [
  'not_started', 'in_progress', 'sufficient', 'insufficient', 'pending_verification'
]

function formatLabel(key) {
  return key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())
}

const form = reactive({
  case_number: '',
  client_name: '',
  claim_stage: 'intake',
  vcf_status: 'pending',
  presence_proof_status: 'not_started',
  date_of_birth: '',
  ssn_last4: '',
  preferred_language: '',
  exposure_location: '',
  presence_dates: '',
  wtc_health_program: false,
  award_amount: '',
  description: '',
})

const errors = reactive({})
function clearError(field) { delete errors[field] }

function validate() {
  let valid = true
  // case_number is auto-generated by the backend when left blank
  if (!form.client_name.trim()) { errors.client_name = 'Client name is required'; valid = false }
  if (form.ssn_last4 && !/^\d{0,4}$/.test(form.ssn_last4)) {
    errors.ssn_last4 = 'SSN last 4 must be up to 4 digits'; valid = false
  }
  return valid
}

async function submitCase() {
  apiError.value = ''
  if (!validate()) return

  submitting.value = true
  const token = localStorage.getItem('paraiq_token')

  try {
    const payload = {
      case_number:   form.case_number.trim(),
      client_name:   form.client_name.trim(),
      claim_stage:   form.claim_stage,
      vcf_status:    form.vcf_status,
      presence_proof_status: form.presence_proof_status,
      date_of_birth: form.date_of_birth || '',
      ssn_last4:     form.ssn_last4 || '',
      preferred_language: form.preferred_language || '',
      exposure_location:  form.exposure_location || '',
      presence_dates:     form.presence_dates || '',
      wtc_health_program: form.wtc_health_program,
      award_amount:       form.award_amount ? parseFloat(form.award_amount) : null,
      description:        form.description.trim(),
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
    createdClaim.value = {
      id:          created.case_id,
      client_name: form.client_name.trim(),
      case_number: form.case_number.trim(),
    }

  } catch (e) {
    apiError.value = e.message || 'Failed to create claim. Please try again.'
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

.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 32px; }
.back-btn { display: flex; align-items: center; gap: 6px; background: transparent; border: 1px solid var(--border-color, #2a2a3a); color: var(--text-muted, #888); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; transition: all 0.15s; white-space: nowrap; }
.back-btn:hover { background: var(--surface-hover, #1a1a2e); color: var(--text-primary, #e0e0e0); }
.header-text h1 { font-size: 24px; font-weight: 700; color: var(--text-primary, #e0e0e0); margin: 0 0 4px; }
.subtitle { font-size: 13px; color: var(--text-muted, #888); margin: 0; }

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
