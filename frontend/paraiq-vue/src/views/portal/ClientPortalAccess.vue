<template>
  <div class="min-h-screen bg-gray-50">
    <!-- Portal Header -->
    <header class="bg-blue-900 text-white shadow-md">
      <div class="container mx-auto px-6 py-4 flex justify-between items-center">
        <h1 class="text-xl font-bold">VCFClaimsIQ Client Portal</h1>
        <div v-if="portalData.access" class="text-sm text-blue-200">
          Welcome, {{ portalData.access.client_name }}
        </div>
      </div>
    </header>

    <main class="container mx-auto px-6 py-8">
      <!-- Loading State -->
      <div v-if="loading" class="text-center py-12">
        <p class="text-gray-500">Verifying your secure access link...</p>
      </div>

      <!-- Error State -->
      <div v-else-if="error" class="bg-red-50 border border-red-200 text-red-700 p-6 rounded-lg text-center">
        <p class="font-semibold">{{ error }}</p>
        <p class="text-sm mt-2">Please contact your attorney for a new access link.</p>
      </div>

      <!-- Portal Content -->
      <div v-else class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        <!-- Left Column: Case Info & Deadlines -->
        <div class="lg:col-span-1 space-y-6">
          <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-lg font-bold border-b pb-2 mb-4">Case Information</h2>
            <div v-if="portalData.matter" class="space-y-3 text-sm">
              <div class="flex justify-between">
                <span class="text-gray-500">Case Number:</span>
                <span class="font-medium">{{ portalData.matter.case_number || 'N/A' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Status:</span>
                <span class="font-medium bg-green-100 text-green-800 px-2 py-0.5 rounded">{{ portalData.matter.status || 'Pending' }}</span>
              </div>
              <div class="flex justify-between">
                <span class="text-gray-500">Client:</span>
                <span class="font-medium">{{ portalData.matter.client_name || portalData.access.client_name }}</span>
              </div>
            </div>
          </div>

          <div class="bg-white rounded-lg shadow p-6">
            <h2 class="text-lg font-bold border-b pb-2 mb-4">Upcoming Deadlines</h2>
            <div v-if="caseDetails.upcoming_deadlines && caseDetails.upcoming_deadlines.length > 0" class="space-y-3">
              <div v-for="event in caseDetails.upcoming_deadlines" :key="event.id" class="text-sm">
                <p class="font-medium text-gray-800">{{ event.title }}</p>
                <p class="text-gray-500">{{ formatDate(event.event_date) }}</p>
              </div>
            </div>
            <p v-else class="text-gray-400 text-sm">No upcoming deadlines scheduled.</p>
          </div>
        </div>

        <!-- Right Column: Tabs (Documents & Messages) -->
        <div class="lg:col-span-2">
          <div class="bg-white rounded-lg shadow">
            <div class="border-b flex">
              <button @click="activeTab = 'documents'" :class="activeTab === 'documents' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'" class="px-6 py-3 font-medium text-sm border-b-2">
                Documents
              </button>
              <button @click="activeTab = 'messages'" :class="activeTab === 'messages' ? 'border-blue-500 text-blue-600' : 'border-transparent text-gray-500'" class="px-6 py-3 font-medium text-sm border-b-2">
                Messages
              </button>
            </div>

            <!-- Documents Tab -->
            <div v-show="activeTab === 'documents'" class="p-6">
              <div class="mb-6 border-2 border-dashed border-gray-300 rounded-lg p-4 text-center">
                <input type="file" ref="fileInput" @change="handleFileUpload" class="hidden" />
                <button @click="$refs.fileInput.click()" class="text-blue-600 font-medium hover:text-blue-800">
                  + Upload New Document
                </button>
                <p v-if="uploading" class="text-gray-500 text-sm mt-2">Uploading...</p>
              </div>

              <div class="space-y-3">
                <div v-if="portalData.documents && portalData.documents.length === 0" class="text-gray-400 text-sm text-center py-4">
                  No documents available yet.
                </div>
                <div v-for="doc in portalData.documents" :key="doc.id" class="flex justify-between items-center p-3 border rounded hover:bg-gray-50">
                  <div>
                    <p class="font-medium text-sm text-gray-800">{{ doc.document_name }}</p>
                    <p class="text-xs text-gray-400">Uploaded: {{ formatDate(doc.upload_date) }}</p>
                  </div>
                  <button @click="downloadDocument(doc.id, doc.document_name)" class="text-blue-600 text-sm hover:underline">
                    View
                  </button>
                </div>
              </div>
            </div>

            <!-- Messages Tab -->
            <div v-show="activeTab === 'messages'" class="p-6">
              <div class="space-y-4 mb-6 max-h-96 overflow-y-auto">
                <div v-if="messages.length === 0" class="text-gray-400 text-sm text-center py-4">
                  No messages yet. Start the conversation below.
                </div>
                <div v-for="msg in messages" :key="msg.id" :class="msg.direction === 'inbound' ? 'text-right' : 'text-left'">
                  <div :class="msg.direction === 'inbound' ? 'bg-blue-100' : 'bg-gray-100'" class="inline-block px-4 py-2 rounded-lg max-w-md">
                    <p class="text-sm text-gray-800">{{ msg.message }}</p>
                    <p class="text-xs text-gray-400 mt-1">{{ formatDate(msg.created_at) }}</p>
                  </div>
                </div>
              </div>

              <div class="border-t pt-4">
                <textarea v-model="newMessage" rows="3" class="w-full border border-gray-300 rounded-md p-2 text-sm" placeholder="Type a message to your attorney..."></textarea>
                <div class="flex justify-end mt-2">
                  <button @click="sendMessage" :disabled="!newMessage.trim()" class="bg-blue-600 text-white px-4 py-2 rounded-md text-sm hover:bg-blue-700 disabled:opacity-50">
                    Send Message
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const token = route.params.token

const loading = ref(true)
const error = ref(null)
const activeTab = ref('documents')
const portalData = ref({})
const caseDetails = ref({})
const messages = ref([])
const newMessage = ref('')
const fileInput = ref(null)
const uploading = ref(false)

const formatDate = (dateStr) => {
  if (!dateStr) return 'N/A'
  return new Date(dateStr).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })
}

const fetchInitialData = async () => {
  loading.value = true
  try {
    // 1. Verify token & get portal data
    const viewRes = await fetch(`/api/client-portal/view/${token}`)
    if (!viewRes.ok) throw new Error('Invalid or expired portal link')
    portalData.value = await viewRes.json()

    // 2. Get case details & deadlines
    const caseRes = await fetch(`/api/client-portal/cases/${token}`)
    if (caseRes.ok) caseDetails.value = await caseRes.json()

    // 3. Get messages
    const msgRes = await fetch(`/api/client-portal/messages/${token}`)
    if (msgRes.ok) messages.value = (await msgRes.json()).messages

  } catch (err) {
    error.value = err.message
  } finally {
    loading.value = false
  }
}

const handleFileUpload = async (event) => {
  const file = event.target.files[0]
  if (!file) return
  
  uploading.value = true
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await fetch(`/api/client-portal/upload/${token}`, {
      method: 'POST',
      body: formData
    })
    if (res.ok) {
      // Refresh documents list
      const docsRes = await fetch(`/api/client-portal/documents/${token}`)
      if (docsRes.ok) {
        portalData.value.documents = (await docsRes.json()).documents
      }
    }
  } catch (err) {
    console.error('Upload failed:', err)
  } finally {
    uploading.value = false
    fileInput.value.value = '' // reset input
  }
}

const downloadDocument = async (docId, filename) => {
  try {
    const res = await fetch(`/api/client-portal/documents/${token}/${docId}`)
    const data = await res.json()
    
    // Create a blob and download
    const blob = new Blob([data.text], { type: 'text/plain' })
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    window.URL.revokeObjectURL(url)
  } catch (err) {
    console.error('Download failed:', err)
  }
}

const sendMessage = async () => {
  if (!newMessage.value.trim()) return
  try {
    const res = await fetch(`/api/client-portal/message/${token}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: newMessage.value })
    })
    if (res.ok) {
      newMessage.value = ''
      // Refresh messages
      const msgRes = await fetch(`/api/client-portal/messages/${token}`)
      if (msgRes.ok) messages.value = (await msgRes.json()).messages
    }
  } catch (err) {
    console.error('Message failed:', err)
  }
}

onMounted(() => {
  fetchInitialData()
})
</script>

python3 << 'EOF'
file_path = 'frontend/paraiq-vue/src/router/index.js'
with open(file_path, 'r') as f:
    content = f.read()

if '/client-portal/view/:token' not in content:
    if 'const routes = [' in content:
        content = content.replace(
            'const routes = [',
            "const routes = [\n  {\n    path: '/client-portal/view/:token',\n    name: 'ClientPortalAccess',\n    component: () => import('../views/portal/ClientPortalAccess.vue'),\n    meta: { requiresAuth: false, layout: 'blank' } // Public route\n  },"
        )
    elif 'routes: [' in content:
         content = content.replace(
            'routes: [',
            "routes: [\n  {\n    path: '/client-portal/view/:token',\n    name: 'ClientPortalAccess',\n    component: () => import('../views/portal/ClientPortalAccess.vue'),\n    meta: { requiresAuth: false, layout: 'blank' } // Public route\n  },"
        )
    with open(file_path, 'w') as f:
        f.write(content)
    print("Successfully patched router/index.js for Client Portal")
else:
    print("Client Portal route already exists")
