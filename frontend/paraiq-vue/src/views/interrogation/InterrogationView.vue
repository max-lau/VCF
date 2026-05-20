<script setup>
import { ref } from 'vue'
import client from '@/api/client'
const text = ref(''); const result = ref(null); const loading = ref(false); const error = ref(null)
async function analyze() {
  loading.value = true; error.value = null; result.value = null
  try { const { data } = await client.post('/interrogate', { text: text.value }); result.value = data }
  catch(e) { error.value = e.response?.data?.detail || 'Analysis failed' }
  finally { loading.value = false }
}
async function exportPdf() {
  try {
    const resp = await client.post('/interrogate/export-pdf', { text: text.value }, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'interrogation-report.pdf'; a.click()
    URL.revokeObjectURL(url)
  } catch(e) { error.value = 'Export failed' }
}
</script>
<template>
  <div class="mod">
    <div class="mod__header">
      <div><h1 class="mod__title">Interrogation Analyzer</h1><p class="mod__sub">Contradiction detection and evasion analysis in transcripts</p></div>
      <button v-if="result" class="btn-export" @click="exportPdf">↓ Export PDF</button>
    </div>
    <div class="input-card">
      <label class="field-label">Deposition or interrogation transcript</label>
      <textarea v-model="text" class="piq-textarea" rows="12" placeholder="Paste transcript text…"/>
      <div class="input-actions"><button class="piq-btn-gold" :disabled="loading||!text.trim()" @click="analyze">{{ loading?'Analysing…':'Analyze Transcript' }}</button></div>
    </div>
    <div v-if="error" class="err-msg">{{ error }}</div>
    <div v-if="result" class="results">
      <div v-if="result.contradictions?.length" class="section-card section-card--red">
        <div class="section-title">Contradictions ({{ result.contradictions.length }})</div>
        <div v-for="(c,i) in result.contradictions" :key="i" class="finding-row">
          <div class="finding-row__head">{{ c.statement_a || c.claim }}</div>
          <div class="finding-row__sub">{{ c.statement_b || c.explanation }}</div>
        </div>
      </div>
      <div v-if="result.evasions?.length" class="section-card section-card--amber">
        <div class="section-title">Evasions ({{ result.evasions.length }})</div>
        <div v-for="(e,i) in result.evasions" :key="i" class="finding-row">
          <div class="finding-row__head">{{ e.question || e.evasion }}</div>
          <div class="finding-row__sub">{{ e.explanation || e.context }}</div>
        </div>
      </div>
      <div v-if="!result.contradictions?.length && !result.evasions?.length" class="clean-msg">✓ No contradictions or evasions detected</div>
      <div v-if="result.summary" class="summary-card"><div class="summary-card__title">Summary</div><p class="summary-text">{{ result.summary }}</p></div>
    </div>
  </div>
</template>
<style scoped>
.mod{padding:2rem;max-width:950px}.mod__header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:1.5rem;gap:1rem}.mod__title{font-family:var(--font-display);font-size:1.6rem;color:var(--gold);margin:0}.mod__sub{color:var(--text-muted);font-size:.85rem;margin:.25rem 0 0}.btn-export{background:transparent;border:1px solid var(--gold,#c9a84c);color:var(--gold,#c9a84c);border-radius:6px;cursor:pointer;font-size:.875rem;font-weight:600;padding:.5rem 1rem;transition:background .15s;white-space:nowrap;flex-shrink:0}.btn-export:hover{background:rgba(201,168,76,.1)}.input-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;margin-bottom:1.25rem}.field-label{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:.5rem}.piq-textarea{background:var(--bg-raised,#0d0d1a);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:.875rem;line-height:1.6;padding:.75rem;resize:vertical;width:100%;box-sizing:border-box}.piq-textarea:focus{border-color:var(--gold);outline:none}.input-actions{display:flex;justify-content:flex-end;margin-top:.75rem}.piq-btn-gold{background:var(--gold);border:none;border-radius:6px;color:#000;cursor:pointer;font-size:.875rem;font-weight:600;padding:.55rem 1.4rem;transition:opacity .2s}.piq-btn-gold:hover:not(:disabled){opacity:.85}.piq-btn-gold:disabled{cursor:not-allowed;opacity:.4}.err-msg{color:#fc8181;font-size:.875rem;margin-bottom:1rem}.results{display:flex;flex-direction:column;gap:1rem}.section-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.1rem 1.25rem}.section-card--red{border-left:3px solid #fc8181;border-radius:0 8px 8px 0}.section-card--amber{border-left:3px solid #ecc94b;border-radius:0 8px 8px 0}.section-title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase;margin-bottom:.85rem}.finding-row{border-bottom:1px solid var(--border);padding:.65rem 0}.finding-row:last-child{border-bottom:none}.finding-row__head{color:var(--text-primary);font-size:.875rem;font-weight:500;margin-bottom:.25rem}.finding-row__sub{color:var(--text-muted);font-size:.8rem;line-height:1.5}.clean-msg{color:#48bb78;font-size:.875rem;padding:1.5rem;text-align:center;background:var(--bg-card);border:1px solid var(--border);border-radius:8px}.summary-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.1rem 1.25rem}.summary-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase;margin-bottom:.6rem}.summary-text{color:var(--text-primary);font-size:.875rem;line-height:1.7;margin:0}
</style>
