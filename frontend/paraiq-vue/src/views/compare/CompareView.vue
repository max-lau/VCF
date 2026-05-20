<script setup>
import { ref } from 'vue'
import client from '@/api/client'
const docA = ref(''); const docB = ref(''); const mode = ref('compare')
const result = ref(null); const loading = ref(false); const error = ref(null)
const modes = [{ key:'compare', label:'Document Compare', sub:'Side-by-side diff' }, { key:'lease-diff', label:'Lease Diff', sub:'Clause-level changes' }]
async function run() {
  loading.value = true; error.value = null; result.value = null
  try {
    const { data } = await client.post(`/documents/${mode.value}`, { doc_a: docA.value, doc_b: docB.value })
    result.value = data
  } catch(e) { error.value = e.response?.data?.detail || 'Comparison failed' }
  finally { loading.value = false }
}
</script>
<template>
  <div class="mod">
    <div class="mod__header"><h1 class="mod__title">Document Compare</h1><p class="mod__sub">Side-by-side comparison and clause-level diff</p></div>
    <div class="mode-bar">
      <button v-for="m in modes" :key="m.key" class="mode-btn" :class="{active:mode===m.key}" @click="mode=m.key">
        <span class="mode-btn__label">{{ m.label }}</span><span class="mode-btn__sub">{{ m.sub }}</span>
      </button>
    </div>
    <div class="two-col">
      <div class="field-block"><label class="field-label">Document A</label><textarea v-model="docA" class="piq-textarea" rows="12" placeholder="Paste first document…"/></div>
      <div class="field-block"><label class="field-label">Document B</label><textarea v-model="docB" class="piq-textarea" rows="12" placeholder="Paste second document…"/></div>
    </div>
    <div class="submit-row"><button class="piq-btn-gold" :disabled="loading||!docA.trim()||!docB.trim()" @click="run">{{ loading?'Comparing…':'Compare Documents' }}</button></div>
    <div v-if="error" class="err-msg">{{ error }}</div>
    <div v-if="result" class="result-card"><div class="result-card__title">Comparison Result</div><pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre></div>
  </div>
</template>
<style scoped>
.mod{padding:2rem;max-width:1100px}.mod__header{margin-bottom:1.5rem}.mod__title{font-family:var(--font-display);font-size:1.6rem;color:var(--gold);margin:0}.mod__sub{color:var(--text-muted);font-size:.85rem;margin:.25rem 0 0}.mode-bar{display:flex;gap:.75rem;margin-bottom:1.25rem}.mode-btn{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;display:flex;flex-direction:column;padding:.65rem 1.1rem;text-align:left;transition:border-color .15s}.mode-btn.active{border-color:var(--gold)}.mode-btn__label{color:var(--text-primary);font-size:.875rem;font-weight:600}.mode-btn__sub{color:var(--text-muted);font-size:.72rem;margin-top:.1rem}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:.75rem}.field-block{display:flex;flex-direction:column;gap:.4rem}.field-label{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase}.piq-textarea{background:var(--bg-raised,#0d0d1a);border:1px solid var(--border);border-radius:6px;box-sizing:border-box;color:var(--text-primary);font-family:inherit;font-size:.875rem;line-height:1.6;padding:.75rem;resize:vertical;width:100%}.piq-textarea:focus{border-color:var(--gold);outline:none}.submit-row{display:flex;justify-content:flex-end;margin-bottom:1.25rem}.piq-btn-gold{background:var(--gold);border:none;border-radius:6px;color:#000;cursor:pointer;font-size:.875rem;font-weight:600;padding:.55rem 1.4rem;transition:opacity .2s}.piq-btn-gold:hover:not(:disabled){opacity:.85}.piq-btn-gold:disabled{cursor:not-allowed;opacity:.4}.err-msg{color:#fc8181;font-size:.875rem;margin-bottom:1rem}.result-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem}.result-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;margin-bottom:.75rem;text-transform:uppercase}.result-pre{background:var(--bg-raised,#0d0d1a);border-radius:6px;color:var(--text-muted);font-family:var(--font-mono);font-size:.78rem;line-height:1.6;margin:0;overflow-x:auto;padding:1rem;white-space:pre-wrap;word-break:break-word}
</style>
