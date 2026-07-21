<template>
  <div class="comms-view">
    <h1>Communications Log</h1>
    <p class="subtitle">All inbound and outbound communications across VCF claims.</p>

    <div class="filters">
      <select v-model="filter.party_type" @change="load">
        <option value="">All parties</option>
        <option value="client">Client</option>
        <option value="doctor">Doctor</option>
        <option value="lab">Lab</option>
        <option value="medicare">Medicare</option>
        <option value="medicaid">Medicaid</option>
        <option value="bank">Bank</option>
        <option value="vcf">VCF</option>
        <option value="office">Office</option>
      </select>
      <select v-model="filter.channel" @change="load">
        <option value="">All channels</option>
        <option value="email">Email</option>
        <option value="phone">Phone</option>
        <option value="fax">Fax</option>
        <option value="mail">Mail</option>
        <option value="sms">SMS</option>
      </select>
      <input v-model="filter.days" type="number" min="1" max="365" @change="load" />
      <span class="dim">days</span>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>
    <div v-else-if="error" class="state-msg error">{{ error }}</div>
    <div v-else-if="!communications.length" class="empty-state">No communications found.</div>

    <table v-else class="comms-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Claim</th>
          <th>Direction</th>
          <th>Channel</th>
          <th>Party</th>
          <th>Subject</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="c in communications" :key="c.id">
          <td class="dim nowrap">{{ fmtDate(c.sent_at) }}</td>
          <td><router-link :to="`/matters/${c.case_id}`" class="link">#{{ c.case_id }}</router-link></td>
          <td><span class="pill" :class="c.direction">{{ c.direction }}</span></td>
          <td class="dim">{{ c.channel }}</td>
          <td>{{ c.party_type }}{{ c.party_name ? ' / ' + c.party_name : '' }}</td>
          <td class="subject">{{ c.subject || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'

const communications = ref([])
const loading = ref(true)
const error = ref(null)
const filter = reactive({ party_type: '', channel: '', days: 30 })

const authHdr = () => ({ Authorization: 'Bearer ' + localStorage.getItem('paraiq_token') })

function fmtDate(d) {
  return d ? new Date(d).toLocaleString() : '—'
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams()
    if (filter.party_type) params.append('party_type', filter.party_type)
    if (filter.channel) params.append('channel', filter.channel)
    params.append('days', filter.days)
    const { data } = await axios.get(`/communications?${params.toString()}`, { headers: authHdr() })
    communications.value = data.communications || []
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.comms-view { padding: 24px; }
h1 { margin: 0 0 4px; }
.subtitle { color: var(--text-muted); margin: 0 0 20px; }
.filters { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; flex-wrap: wrap; }
.filters select, .filters input { background: var(--input-bg); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); padding: 8px 12px; }
.filters input { width: 70px; }
.state-msg { padding: 40px; text-align: center; color: var(--text-muted); }
.state-msg.error { color: #e07070; }
.empty-state { padding: 40px; text-align: center; color: var(--text-muted); }
.comms-table { width: 100%; border-collapse: collapse; }
.comms-table th, .comms-table td { text-align: left; padding: 12px; border-bottom: 1px solid var(--border); }
.comms-table th { color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }
.pill { font-size: 0.75rem; padding: 2px 8px; border-radius: 100px; text-transform: uppercase; }
.pill.inbound { background: rgba(72,187,120,.15); color: #48bb78; }
.pill.outbound { background: rgba(74,124,247,.15); color: #4a7cf7; }
.link { color: var(--gold); text-decoration: none; }
.link:hover { text-decoration: underline; }
.subject { max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
