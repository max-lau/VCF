<template>
  <div class="deadlines-view">
    <h1>VCF Deadlines</h1>
    <p>Upcoming deadlines for the next 30 days.</p>
    
    <div v-if="loading" class="loading">Loading deadlines...</div>
    <div v-if="error" class="error">{{ error }}</div>
    
    <table v-if="!loading && deadlines.length > 0" class="deadlines-table">
      <thead>
        <tr>
          <th>Case Number</th>
          <th>Client</th>
          <th>Deadline Type</th>
          <th>Due Date</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="d in deadlines" :key="d.id">
          <td>{{ d.case_number }}</td>
          <td>{{ d.client_name }}</td>
          <td>{{ d.deadline_type }}</td>
          <td>{{ formatDate(d.due_date) }}</td>
          <td>{{ d.status }}</td>
        </tr>
      </tbody>
    </table>
    
    <div v-if="!loading && deadlines.length === 0" class="empty-state">
      No upcoming deadlines. 
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '@/api/client'

const deadlines = ref([])
const loading = ref(true)
const error = ref(null)

const formatDate = (dateStr) => {
  return new Date(dateStr).toLocaleDateString()
}

onMounted(async () => {
  try {
    const response = await api.get('/vcf/deadlines?days_ahead=30')
    deadlines.value = response.data.deadlines
  } catch (err) {
    error.value = 'Failed to load deadlines.'
    console.error(err)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.deadlines-view {
  padding: 24px;
}
.deadlines-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 16px;
}
.deadlines-table th, .deadlines-table td {
  text-align: left;
  padding: 12px;
  border-bottom: 1px solid var(--border-dim);
}
.loading, .error, .empty-state {
  padding: 24px;
  text-align: center;
}
</style>