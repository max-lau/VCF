<script setup>
import { ref } from 'vue'
import client from '@/api/client'
const text = ref(''); const result = ref(null); const loading = ref(false); const error = ref(null)
async function score() {
  loading.value = true; error.value = null; result.value = null
  try { const { data } = await client.post('/credibility/score', { text: text.value }); result.value = data }
  catch(e) { error.value = e.response?.data?.detail || 'Scoring failed' }
  finally { loading.value = false }
}
function pct(v) { return Math.round((v||0)*100) }
function barColor(v) { const p=pct(v); return p>=80?'#48bb78':p>=55?'#ecc94b':'#fc8181' }
</script>
<template>
  <div class="mod">
    <div class="mod__header"><h1 class="mod__title">Credibility Scorer</h1><p class="mod__sub">AI-powered testimony and document credibility analysis</p></div>
    <div class="input-card">
      <label class="field-label">Testimony or document text</label>
      <textarea v-model="text" class="piq-textarea" rows="10" placeholder="Paste testimony transcript or document…"/>
      <div class="input-actions"><button class="piq-btn-gold" :disabled="loading||!text.trim()" @click="score">{{ loading?'Scoring…':'Score Credibility' }}</button></div>
    </div>
    <div v-if="error" class="err-msg">{{ error }}</div>
    <div v-if="result" class="results">
      <div class="score-card">
        <div class="score-card__label">Overall Credibility</div>
        <div class="score-card__val" :style="{color:barColor(result.overall_score??result.score)}">{{ pct(result.overall_score??result.score) }}<span style="font-size:1.4rem">%</span></div>
        <div class="score-bar-track"><div class="score-bar-fill" :style="{width:pct(result.overall_score??result.score)+'%',background:barColor(result.overall_score??result.score)}"/></div>
      </div>
      <div v-if="result.scores||result.dimensions" class="sub-card">
        <div class="sub-card__title">Dimensions</div>
        <div class="sub-grid">
          <div v-for="(val,key) in (result.scores||result.dimensions)" :key="key" class="sub-row">
            <span class="sub-row__name">{{ key.replace(/_/g,' ') }}</span>
            <div class="sub-bar-track"><div class="sub-bar-fill" :style="{width:pct(val)+'%',background:barColor(val)}"/></div>
            <span class="sub-row__val" :style="{color:barColor(val)}">{{ pct(val) }}%</span>
          </div>
        </div>
      </div>
      <div v-if="result.flags?.length||result.concerns?.length" class="flag-card">
        <div class="flag-card__title">Credibility Flags</div>
        <div v-for="f in (result.flags||result.concerns)" :key="f" class="flag-row"><span class="flag-dot"/>{{ f }}</div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.mod{padding:2rem;max-width:900px}.mod__header{margin-bottom:1.5rem}.mod__title{font-family:var(--font-display);font-size:1.6rem;color:var(--gold);margin:0}.mod__sub{color:var(--text-muted);font-size:.85rem;margin:.25rem 0 0}.input-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.25rem;margin-bottom:1.25rem}.field-label{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;display:block;margin-bottom:.5rem}.piq-textarea{background:var(--bg-raised,#0d0d1a);border:1px solid var(--border);border-radius:6px;color:var(--text-primary);font-family:inherit;font-size:.875rem;line-height:1.6;padding:.75rem;resize:vertical;width:100%;box-sizing:border-box}.piq-textarea:focus{border-color:var(--gold);outline:none}.input-actions{display:flex;justify-content:flex-end;margin-top:.75rem}.piq-btn-gold{background:var(--gold);border:none;border-radius:6px;color:#000;cursor:pointer;font-size:.875rem;font-weight:600;padding:.55rem 1.4rem;transition:opacity .2s}.piq-btn-gold:hover:not(:disabled){opacity:.85}.piq-btn-gold:disabled{cursor:not-allowed;opacity:.4}.err-msg{color:#fc8181;font-size:.875rem;margin-bottom:1rem}.score-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.5rem;text-align:center;margin-bottom:1rem}.score-card__label{font-size:.72rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:.5rem}.score-card__val{font-size:3.5rem;font-weight:700;line-height:1;margin-bottom:.75rem}.score-bar-track{background:var(--border);border-radius:99px;height:8px;margin:0 auto;max-width:300px;overflow:hidden}.score-bar-fill{border-radius:99px;height:100%;transition:width .6s ease}.sub-card{background:var(--bg-card);border:1px solid var(--border);border-radius:8px;padding:1.1rem 1.25rem;margin-bottom:1rem}.sub-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase;margin-bottom:.85rem}.sub-grid{display:flex;flex-direction:column;gap:.5rem}.sub-row{display:flex;align-items:center;gap:.75rem;font-size:.82rem}.sub-row__name{color:var(--text-muted);min-width:130px;text-transform:capitalize}.sub-bar-track{background:var(--border);border-radius:99px;flex:1;height:5px;overflow:hidden}.sub-bar-fill{border-radius:99px;height:100%;transition:width .5s ease}.sub-row__val{font-size:.78rem;font-weight:600;min-width:36px;text-align:right}.flag-card{background:var(--bg-card);border:1px solid var(--border);border-left:3px solid #fc8181;border-radius:0 8px 8px 0;padding:1rem 1.25rem}.flag-card__title{font-size:.72rem;color:var(--text-muted);font-weight:600;letter-spacing:.05em;text-transform:uppercase;margin-bottom:.65rem}.flag-row{display:flex;align-items:flex-start;gap:.5rem;font-size:.82rem;color:var(--text-muted);margin-bottom:.35rem}.flag-dot{background:#fc8181;border-radius:50%;flex-shrink:0;height:7px;margin-top:5px;width:7px}
</style>
