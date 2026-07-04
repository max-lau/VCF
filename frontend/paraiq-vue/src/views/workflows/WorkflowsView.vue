<template>
  <div class="container mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Automated Workflows</h1>
    <p class="text-gray-600 mb-6">Create trigger-action rules to automate your firm's repetitive tasks.</p>

    <div class="bg-white shadow rounded-lg p-6 mb-8">
      <h2 class="text-lg font-semibold mb-4">Create New Workflow</h2>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label class="block text-sm font-medium text-gray-700">Workflow Name</label>
          <input v-model="newWorkflow.name" type="text" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2" placeholder="e.g., Notify client on case file">
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Trigger Event</label>
          <select v-model="newWorkflow.trigger_event" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2">
            <option value="case_status_change">Case Status Change</option>
            <option value="document_uploaded">Document Uploaded</option>
            <option value="invoice_paid">Invoice Paid</option>
          </select>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Condition Key (Optional)</label>
          <input v-model="newWorkflow.condition_key" type="text" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2" placeholder="e.g., status">
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Condition Value (Optional)</label>
          <input v-model="newWorkflow.condition_value" type="text" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2" placeholder="e.g., Filed">
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-700">Action Type</label>
          <select v-model="newWorkflow.action_type" class="mt-1 block w-full border border-gray-300 rounded-md shadow-sm p-2">
            <option value="send_email">Send Email</option>
            <option value="create_task">Create Task</option>
            <option value="generate_document">Generate Document</option>
          </select>
        </div>
        <div class="flex items-end">
          <button @click="createWorkflow" class="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700">Save Workflow</button>
        </div>
      </div>
    </div>

    <div class="bg-white shadow rounded-lg p-6">
      <h2 class="text-lg font-semibold mb-4">Active Workflows</h2>
      <div v-if="loading" class="text-gray-500">Loading workflows...</div>
      <div v-else-if="workflows.length === 0" class="text-gray-500">No workflows configured yet.</div>
      <ul v-else class="divide-y divide-gray-200">
        <li v-for="wf in workflows" :key="wf.id" class="py-4 flex justify-between items-center">
          <div>
            <p class="font-medium text-gray-900">{{ wf.name }}</p>
            <p class="text-sm text-gray-500">
              Trigger: {{ wf.trigger_event }} 
              <span v-if="wf.trigger_conditions && Object.keys(wf.trigger_conditions).length > 0">
                (When {{ Object.keys(wf.trigger_conditions)[0] }} = {{ Object.values(wf.trigger_conditions)[0] }})
              </span>
              &nbsp;| Action: {{ wf.action_type }}
            </p>
          </div>
          <button @click="deleteWorkflow(wf.id)" class="text-red-600 hover:text-red-800 text-sm">Delete</button>
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const FIRM_ID = 'default' 

const workflows = ref([])
const loading = ref(true)

const newWorkflow = ref({
  name: '',
  trigger_event: 'case_status_change',
  condition_key: '',
  condition_value: '',
  action_type: 'send_email'
})

const fetchWorkflows = async () => {
  loading.value = true
  try {
    const response = await fetch('/api/workflows/', {
      headers: { 'X-Firm-Id': FIRM_ID }
    })
    if (response.ok) {
      workflows.value = await response.json()
    }
  } catch (error) {
    console.error('Failed to fetch workflows:', error)
  } finally {
    loading.value = false
  }
}

const createWorkflow = async () => {
  const conditions = {}
  if (newWorkflow.value.condition_key && newWorkflow.value.condition_value) {
    conditions[newWorkflow.value.condition_key] = newWorkflow.value.condition_value
  }

  const payload = {
    name: newWorkflow.value.name,
    trigger_event: newWorkflow.value.trigger_event,
    trigger_conditions: conditions,
    action_type: newWorkflow.value.action_type,
    action_payload: { template: 'default_template' }
  }

  try {
    const response = await fetch('/api/workflows/', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-Firm-Id': FIRM_ID 
      },
      body: JSON.stringify(payload)
    })
    if (response.ok) {
      newWorkflow.value = { name: '', trigger_event: 'case_status_change', condition_key: '', condition_value: '', action_type: 'send_email' }
      await fetchWorkflows()
    }
  } catch (error) {
    console.error('Failed to create workflow:', error)
  }
}

const deleteWorkflow = async (id) => {
  try {
    const response = await fetch(`/api/workflows/${id}`, {
      method: 'DELETE',
      headers: { 'X-Firm-Id': FIRM_ID }
    })
    if (response.ok) {
      await fetchWorkflows()
    }
  } catch (error) {
    console.error('Failed to delete workflow:', error)
  }
}

onMounted(() => {
  fetchWorkflows()
})
</script>
