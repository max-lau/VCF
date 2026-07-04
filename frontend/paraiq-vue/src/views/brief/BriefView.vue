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
      <div v-else class="text-red-500 text-center py-8">No brief found for this case.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AttorneyReviewGate from '@/components/ui/AttorneyReviewGate.vue'

const route = useRoute()
const caseId = route.params.caseId || route.params.id

const loading = ref(true)
const brief = ref(null)

const fetchBrief = async () => {
  loading.value = true
  try {
    // Assuming you have an endpoint to fetch the brief JSON, 
    // or you can adapt this to however your app currently loads briefs.
    const res = await fetch(`/api/cases/${caseId}/brief`) 
    if (res.ok) {
      brief.value = await res.json()
    }
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
