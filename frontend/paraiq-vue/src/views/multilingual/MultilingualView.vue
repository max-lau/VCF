<script setup>
import { ref } from 'vue'
import client from '@/api/client'
import NlpResultCard from '@/components/ui/NlpResultCard.vue'

const text = ref(''), lang = ref('auto'), result = ref(null)
const loading = ref(false), error = ref(null), tab = ref('text')
const audioFile = ref(null), audioInput = ref(null)
const langs = ['auto','en','es','fr','de','zh','ar','ja','pt','ru','it']

async function analyzeText() {
  loading.value = true; error.value = null; result.value = null
  try   { const { data } = await client.post('/analyze/multilingual', { text: text.value, language: lang.value }); result.value = data }
  catch (e) { error.value = e.response?.data?.detail || 'Analysis failed' }
  finally   { loading.value = false }
}
async function transcribeAudio() {
  if (!audioFile.value) return
  loading.value = true; error.value = null; result.value = null
  try {
    const fd = new FormData(); fd.append('file', audioFile.value)
    const { data } = await client.post(`/intake/audio?lang=${lang.value}`, fd)
    result.value = data
  } catch (e) { error.value = e.response?.data?.detail || 'Transcription failed' }
  finally     { loading.value = false }
}
</script>
<template>
  <div class="nlp-mod">
    <div class="nlp-mod__header">
      <h1 class="nlp-mod__title">Multilingual Analysis</h1>
      <p class="nlp-mod__sub">Cross-language NLP and audio transcription</p>
    </div>

    <div class="nlp-top-bar">
      <div class="nlp-tab-bar">
        <button class="nlp-tab-btn" :class="{active:tab==='text'}"  @click="tab='text'">Text</button>
        <button class="nlp-tab-btn" :class="{active:tab==='audio'}" @click="tab='audio'">Audio</button>
      </div>
      <div class="nlp-lang-selector">
        <label class="nlp-field-label" style="margin:0">Language</label>
        <select v-model="lang" class="nlp-select">
          <option v-for="l in langs" :key="l" :value="l">{{ l==='auto'?'Auto-detect':l.toUpperCase() }}</option>
        </select>
      </div>
    </div>

    <div v-if="error" class="nlp-err">{{ error }}</div>

    <div v-if="tab==='text'" class="nlp-input-card">
      <label class="nlp-field-label">Document text</label>
      <textarea v-model="text" class="nlp-textarea" rows="10" placeholder="Paste text in any language…"/>
      <div class="nlp-input-actions">
        <button class="nlp-btn" :disabled="loading||!text.trim()" @click="analyzeText">{{ loading?'Analysing…':'Analyze' }}</button>
      </div>
    </div>

    <div v-if="tab==='audio'">
      <div class="nlp-drop-zone" :class="{'has-file':audioFile}"
        @dragover.prevent @drop.prevent="e=>audioFile=e.dataTransfer.files[0]" @click="audioInput.click()">
        <input ref="audioInput" type="file" accept="audio/*" style="display:none" @change="e=>audioFile=e.target.files[0]"/>
        <div class="nlp-drop-zone__icon">↑</div>
        <div class="nlp-drop-zone__title">{{ audioFile?audioFile.name:'Drop audio file or click to upload' }}</div>
        <div class="nlp-drop-zone__sub">MP3 · WAV · M4A · OGG</div>
      </div>
      <div class="nlp-submit-row">
        <button class="nlp-btn" :disabled="loading||!audioFile" @click="transcribeAudio">{{ loading?'Transcribing…':'Transcribe' }}</button>
      </div>
    </div>

    <NlpResultCard v-if="result" :result="result" title="Result"/>
  </div>
</template>
