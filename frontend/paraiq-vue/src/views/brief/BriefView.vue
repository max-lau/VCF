<template>
  <div class="container mx-auto p-6">
    <!-- 1. The Attorney Review Gate (Watermark Shield) -->
    <AttorneyReviewGate :caseId="caseId" />

    <!-- 2. The AI Document Display -->
    <div class="bg-white shadow rounded-lg p-8 mt-4 border-t-4 border-purple-600">
      <div v-if="loading" class="text-gray-500 text-center py-8">Loading AI Case Brief...</div>
      <div v-else-if="brief">
        <h1 class="text-2xl font-bold text-gray-900 mb-2">AI Case Brief</h1>
        <p class="text-sm text-gray-500 mb-6">Case: {{ brief.case_number }} | Generated: {{ brief.generated_at }}</p>
        
        <div v-for="(section, key) in brief.sections" :key="key" class="mb-6">
          <h2 class="text-lg font-semibold text-purple-800 border-b pb-1 mb-3">{{ section.title }}</h2>
          <p class="text-gray-800 whitespace-pre-line text-sm leading-relaxed">{{ section.content }}</p>
        </div>
      </div>
      <div v-else class="text-center py-8">
        <p class="text-gray-500 mb-4">No brief has been generated for this case yet.</p>
        <button @click="generateBrief" :disabled="generating"
                class="px-4 py-2 bg-purple-600 text-white rounded hover:bg-purple-700 disabled:opacity-50">
          {{ generating ? 'Generating… (this takes ~30s)' : 'Generate AI Brief' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AttorneyReviewGate from '@/components/ui/AttorneyReviewGate.vue'
import client from '@/api/client'

const route = useRoute()
const caseId = route.params.caseId || route.params.id

const loading = ref(true)
const brief = ref(null)
const generating = ref(false)

const generateBrief = async () => {
  generating.value = true
  try {
    const { data } = await client.post(`/cases/${caseId}/brief`)
    brief.value = data.brief
  } catch (error) {
    console.error('Brief generation failed:', error)
  } finally {
    generating.value = false
  }
}

const fetchBrief = async () => {
  loading.value = true
  try {
    const { data } = await client.get(`/cases/${caseId}/brief`)
    brief.value = data
  } catch (error) {
    console.error('Failed to load brief:', error)
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchBrief()
})
</script>
