<script setup>
import { ref } from 'vue'
import client from '@/api/client'
const text = ref(''); const result = ref(null); const loading = ref(false); const error = ref(null); const mode = ref('extract')
async function run() {
  loading.value = true; error.value = null; result.value = null
  try {
    const ep = mode.value === 'extract' ? '/citations/extract' : '/citations/resolve'
    const { data } = await client.post(ep, { text: text.value })
    result.value = data
  } catch(e) { error.value = e.response?.data?.detail || 'Failed' }
  finally { loading.value = false }
}
</script>
<template>
  <div class="mod">
    <div class="mod__header"><h1 class="mod__title">Citation Resolver</h1><p class="mod__sub">Extract and resolve legal citations from documents</p></div>
    <div class="mode-bar">
      <button class="mode-btn" :class="{active:mode==='extract'}" @click="mode='extract'"><span class="mode-btn__label">Extract</span><span class="mode-btn__sub">Find citations in text</span></button>
      <button class="mode-btn" :class="{active:mode==='resolve'}" @click="mode='resolve'"><span class="mode-btn__label">Resolve</span><span class="mode-btn__sub">Resolve to full references</span></button>
    </div>
    <div class="input-card">
      <label class="field-label">Document text</label>
      <textarea v-model="text" class="piq-textarea" rows="8" placeholder="Paste text containing legal citations…"/>
      <div class="input-actions"><button class="piq-btn-gold" :disabled="loading||!text.trim()" @click="run">{{ loading?'Processing…':mode==='extract'?'Extract Citations':'Resolve Citations' }}</button></div>
    </div>
    <div v-if="error" class="err-msg">{{ error }}</div>
    <div v-if="result" class="result-card"><div class="result-card__title">Result</div><pre class="result-pre">{{ JSON.stringify(result, null, 2) }}</pre></div>
  </div>
</template>
<style scoped>
.mod{padding:2rem;max-width:900px}.mod__header{margin-bottom:1.5rem}.mod__title{font-family:var(--font-display);font-size:1.6rem;color:var(--gold);margin:0}.mod__sub{color:var(--text-muted);font-size:.85rem;margin:.25rem 0 0}.mode-bar{display:flex;gap:.75rem;margin-bottom:1.25rem}.mode-btn{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;cursor:pointer;display:flex;flex-direction:column;padding:.65rem 1.1rem;text-align:left;transition:border-color .15s}.mode-btn.active{border-color:var(--gold)}.mode-btn__label{color:var(--text-primary);font-size:.875rem;font-weight:600}.mode-btn__sub{color:var(--text-muted);font-size:.72rem;margin-top:.1rem}.input-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;margin-bottom:1.25rem}.field-label{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:.5rem}.piq-textarea{background:var(--bg-raised,#0d0d1a);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:.875rem;line-height:1.6;padding:.75rem;resize:vertical;width:100%;box-sizing:border-box}.piq-textarea:focus{border-color:var(--gold);outline:none}.input-actions{display:flex;justify-content:flex-end;margin-top:.75rem}.piq-btn-gold{background:var(--gold);border:none;border-radius:6px;color:#000;cursor:pointer;font-size:.875rem;font-weight:600;padding:.55rem 1.4rem;transition:opacity .2s}.piq-btn-gold:hover:not(:disabled){opacity:.85}.piq-btn-gold:disabled{cursor:not-allowed;opacity:.4}.err-msg{color:#fc8181;font-size:.875rem;margin-bottom:1rem}.result-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem}.result-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;margin-bottom:.75rem;text-transform:uppercase}.result-pre{background:var(--bg-raised,#0d0d1a);border-radius:6px;color:var(--text-muted);font-family:var(--font-mono);font-size:.78rem;line-height:1.6;margin:0;overflow-x:auto;padding:1rem;white-space:pre-wrap;word-break:break-word}
</style>
