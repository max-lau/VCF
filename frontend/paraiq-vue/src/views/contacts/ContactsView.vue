<script setup>
import { ref, computed, onMounted } from 'vue'
import client from '@/api/client'

const firmId  = () => { try { return JSON.parse(localStorage.getItem('paraiq_user')||'{}').firm_id||'default' } catch { return 'default' } }

const contacts   = ref([])
const loading    = ref(false)
const showCreate = ref(false)
const editing    = ref(null)
const saving     = ref(false)
const search     = ref('')
const filterRole = ref('')
const filterAdverse = ref('')

const ROLES = ['client','witness','expert','opposing_counsel','opposing_party','judge','mediator','paralegal','co_counsel','vendor','other']

function emptyForm() {
  return { name:'', role:'client', organization:'', email:'', phone:'', address:'', notes:'', is_adverse:false, tags:'' }
}
const form = ref(emptyForm())

async function fetchContacts() {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (filterRole.value) params.set('role', filterRole.value)
    if (search.value)     params.set('search', search.value)
    const { data } = await client.get(`/contacts/firm/${firmId()}?${params}`)
    contacts.value = data
  } catch { contacts.value = [] }
  finally { loading.value = false }
}

onMounted(fetchContacts)

let searchTimer = null
function onSearch() { clearTimeout(searchTimer); searchTimer = setTimeout(fetchContacts, 300) }

function openEdit(c) {
  editing.value = c.id
  form.value = { name: c.name, role: c.role, organization: c.organization||'', email: c.email||'', phone: c.phone||'', address: c.address||'', notes: c.notes||'', is_adverse: !!c.is_adverse, tags: c.tags||'' }
  showCreate.value = true
}

function openCreate() {
  editing.value = null
  form.value = emptyForm()
  showCreate.value = true
}

async function save() {
  if (!form.value.name.trim()) return
  saving.value = true
  try {
    if (editing.value) {
      await client.put(`/contacts/${editing.value}`, form.value)
    } else {
      await client.post('/contacts/', { ...form.value, firm_id: firmId() }, { headers: authHdr() })
    }
    showCreate.value = false
    form.value = emptyForm()
    editing.value = null
    fetchContacts()
  } catch {} finally { saving.value = false }
}

async function deleteContact(id) {
  if (!confirm('Delete this contact?')) return
  await client.delete(`/contacts/${id}`)
  fetchContacts()
}

function roleColor(r) {
  const m = { client:'#4a7cf7', witness:'#ecc94b', expert:'#9f7aea', opposing_counsel:'#fc8181', opposing_party:'#fc8181', judge:'#c9a84c', mediator:'#48bb78', paralegal:'#48bb78', co_counsel:'#4a7cf7', vendor:'#718096', other:'#718096' }
  return m[r] || '#718096'
}
function roleIcon(r) {
  return { client:'👤', witness:'👁', expert:'🔬', opposing_counsel:'⚔', opposing_party:'⚔', judge:'⚖', mediator:'🤝', paralegal:'📋', co_counsel:'🤝', vendor:'🏢', other:'◎' }[r] || '◎'
}

function initials(name) {
  return name.split(' ').map(n=>n[0]).join('').toUpperCase().slice(0,2)
}

function avatarColor(name) {
  const colors = ['#4a7cf7','#9f7aea','#48bb78','#ecc94b','#fc8181','#c9a84c']
  return colors[name.length % colors.length]
}

const filtered = computed(() => {
  let list = contacts.value
  if (filterAdverse.value === 'adverse')     list = list.filter(c => c.is_adverse)
  if (filterAdverse.value === 'friendly')    list = list.filter(c => !c.is_adverse)
  return list
})

const grouped = computed(() => {
  const groups = {}
  for (const c of filtered.value) {
    const key = c.role
    if (!groups[key]) groups[key] = []
    groups[key].push(c)
  }
  return groups
})

const counts = computed(() => ({
  total: contacts.value.length,
  adverse: contacts.value.filter(c => c.is_adverse).length,
  roles: new Set(contacts.value.map(c=>c.role)).size,
}))
</script>

<template>
  <div class="contacts">
    <!-- Header -->
    <div class="contacts__header">
      <div>
        <h1 class="contacts__title">Contacts</h1>
        <p class="contacts__sub">Clients · witnesses · counsel · experts</p>
      </div>
      <button class="btn-gold" @click="openCreate">+ New Contact</button>
    </div>

    <!-- Search & filters -->
    <div class="filter-bar">
      <input class="search-input" v-model="search" @input="onSearch" placeholder="Search name, email, organization…" />
      <select class="bar-select" v-model="filterRole" @change="fetchContacts">
        <option value="">All roles</option>
        <option v-for="r in ROLES" :key="r" :value="r">{{ r.replace(/_/g,' ') }}</option>
      </select>
      <select class="bar-select sm" v-model="filterAdverse">
        <option value="">All parties</option>
        <option value="friendly">Non-adverse</option>
        <option value="adverse">Adverse</option>
      </select>
    </div>

    <!-- Stats -->
    <div class="stats-row" v-if="contacts.length">
      <div class="stat"><span class="stat__n">{{ counts.total }}</span><span class="stat__l">Contacts</span></div>
      <div class="stat"><span class="stat__n" style="color:#fc8181">{{ counts.adverse }}</span><span class="stat__l">Adverse</span></div>
      <div class="stat"><span class="stat__n" style="color:#9f7aea">{{ counts.roles }}</span><span class="stat__l">Roles</span></div>
    </div>

    <div v-if="loading" class="state-msg">Loading…</div>

    <div v-else-if="!filtered.length" class="empty">
      <div class="empty__icon">👥</div>
      <div class="empty__title">No contacts yet</div>
      <div class="empty__sub">Add clients, witnesses, counsel, and other parties.</div>
      <button class="btn-gold mt" @click="openCreate">+ Add First Contact</button>
    </div>

    <!-- Grouped by role -->
    <div v-else>
      <div v-for="(group, role) in grouped" :key="role" class="role-group">
        <div class="role-label">
          <span class="role-icon">{{ roleIcon(role) }}</span>
          {{ role.replace(/_/g,' ') }}
          <span class="role-count">{{ group.length }}</span>
        </div>
        <div class="contact-grid">
          <div v-for="c in group" :key="c.id" class="contact-card">
            <div class="contact-card__avatar" :style="{ background: avatarColor(c.name)+'33', color: avatarColor(c.name) }">
              {{ initials(c.name) }}
            </div>
            <div class="contact-card__body">
              <div class="contact-name">
                {{ c.name }}
                <span v-if="c.is_adverse" class="adverse-badge">Adverse</span>
              </div>
              <div v-if="c.organization" class="dim sm">{{ c.organization }}</div>
              <div class="contact-links">
                <a v-if="c.email" :href="`mailto:${c.email}`" class="contact-link">✉ {{ c.email }}</a>
                <span v-if="c.phone" class="dim sm">📞 {{ c.phone }}</span>
              </div>
              <div v-if="c.notes" class="dim sm notes">{{ c.notes }}</div>
            </div>
            <div class="contact-card__actions">
              <span class="role-pill" :style="{ background: roleColor(c.role)+'22', color: roleColor(c.role) }">{{ c.role.replace(/_/g,' ') }}</span>
              <button class="icon-btn" @click="openEdit(c)" title="Edit">✏</button>
              <button class="icon-btn del" @click="deleteContact(c.id)" title="Delete">✕</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create / Edit modal -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <div class="modal__header">
          <h2>{{ editing ? 'Edit Contact' : 'New Contact' }}</h2>
          <button class="close-btn" @click="showCreate = false">✕</button>
        </div>
        <div class="modal__body">
          <div class="field-row">
            <div class="field f2"><label>Full Name *</label><input v-model="form.name" placeholder="John Smith" /></div>
            <div class="field">
              <label>Role</label>
              <select v-model="form.role">
                <option v-for="r in ROLES" :key="r" :value="r">{{ r.replace(/_/g,' ') }}</option>
              </select>
            </div>
          </div>
          <div class="field"><label>Organization</label><input v-model="form.organization" placeholder="Firm / company name" /></div>
          <div class="field-row">
            <div class="field f2"><label>Email</label><input type="email" v-model="form.email" placeholder="john@example.com" /></div>
            <div class="field"><label>Phone</label><input v-model="form.phone" placeholder="+1 (212) 555-0100" /></div>
          </div>
          <div class="field"><label>Address</label><input v-model="form.address" placeholder="Street, City, State ZIP" /></div>
          <div class="field"><label>Tags</label><input v-model="form.tags" placeholder="Comma-separated tags" /></div>
          <div class="field"><label>Notes</label><textarea v-model="form.notes" rows="3" placeholder="Additional notes…"></textarea></div>
          <label class="check-label">
            <input type="checkbox" v-model="form.is_adverse" />
            Adverse party (opposing counsel, opposing party, etc.)
          </label>
        </div>
        <div class="modal__footer">
          <button class="btn-secondary" @click="showCreate = false">Cancel</button>
          <button class="btn-gold" @click="save" :disabled="saving || !form.name.trim()">
            {{ saving ? 'Saving…' : (editing ? 'Update' : 'Create') }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.contacts { padding: 2rem; max-width: 1100px; }
.contacts__header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 1.25rem; }
.contacts__title  { font-family: var(--font-display); font-size: 1.6rem; color: var(--gold); margin: 0; }
.contacts__sub    { color: var(--text-muted); font-size: 0.85rem; margin: 0.25rem 0 0; }

.filter-bar { display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem; flex-wrap: wrap; }
.search-input { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; outline: none; padding: 0.4rem 0.75rem; flex: 1; max-width: 320px; }
.search-input:focus { border-color: var(--gold); }
.bar-select { background: var(--bg-card); border: 1px solid var(--border); border-radius: 6px; color: var(--text-primary); font-size: 0.85rem; padding: 0.4rem 0.75rem; }
.bar-select.sm { max-width: 140px; }

.stats-row { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.stat { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; padding: 0.75rem 1.25rem; display: flex; flex-direction: column; }
.stat__n { font-size: 1.4rem; font-weight: 700; color: var(--text-primary); }
.stat__l { font-size: 0.72rem; color: var(--text-muted); margin-top: 0.1rem; }

.role-group { margin-bottom: 1.5rem; }
.role-label { align-items: center; color: var(--text-muted); display: flex; font-size: 0.72rem; font-weight: 600; gap: 0.4rem; letter-spacing: .08em; margin-bottom: 0.6rem; text-transform: uppercase; }
.role-icon  { font-size: 1rem; }
.role-count { background: var(--bg-raised); border-radius: 10px; font-size: 0.68rem; padding: 0.1rem 0.4rem; }

.contact-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px,1fr)); gap: 0.6rem; }
.contact-card { background: var(--bg-card); border: 1px solid var(--border); border-radius: 8px; display: flex; align-items: flex-start; gap: 0.9rem; padding: 0.9rem 1rem; transition: border-color .15s; }
.contact-card:hover { border-color: var(--gold); }
.contact-card__avatar { align-items: center; border-radius: 50%; display: flex; font-size: 0.85rem; font-weight: 700; height: 38px; justify-content: center; flex-shrink: 0; width: 38px; }
.contact-card__body { flex: 1; min-width: 0; }
.contact-card__actions { display: flex; flex-direction: column; align-items: flex-end; gap: 0.4rem; flex-shrink: 0; }
.contact-name { font-size: 0.9rem; font-weight: 600; color: var(--text-primary); display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }
.adverse-badge { background: rgba(252,129,129,.15); border-radius: 4px; color: #fc8181; font-size: 0.65rem; font-weight: 700; padding: 0.1rem 0.35rem; text-transform: uppercase; }
.contact-links { display: flex; gap: 0.75rem; margin-top: 0.25rem; flex-wrap: wrap; }
.contact-link { color: var(--gold); font-size: 0.78rem; text-decoration: none; }
.contact-link:hover { text-decoration: underline; }
.sm { font-size: 0.78rem; }
.notes { margin-top: 0.25rem; line-height: 1.4; max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.role-pill { border-radius: 4px; font-size: 0.65rem; font-weight: 700; padding: 0.15rem 0.4rem; text-transform: capitalize; white-space: nowrap; }
.icon-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.15rem 0.3rem; border-radius: 4px; transition: color .15s; }
.icon-btn:hover { color: var(--text-primary); }
.icon-btn.del:hover { color: #fc8181; }

.check-label { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; color: var(--text-muted); cursor: pointer; }
.check-label input { accent-color: var(--gold); }

.empty { text-align: center; padding: 4rem 2rem; }
.empty__icon  { font-size: 2.5rem; opacity: .3; margin-bottom: 1rem; }
.empty__title { color: var(--text-primary); font-size: 1.1rem; font-weight: 600; }
.empty__sub   { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.4rem; }
.mt { margin-top: 1.25rem; }

.btn-gold     { background: var(--gold); border: none; border-radius: 6px; color: #0a0a14; cursor: pointer; font-size: 0.8rem; font-weight: 700; padding: 0.5rem 1.1rem; transition: opacity .15s; }
.btn-gold:hover:not(:disabled) { opacity: .85; }
.btn-gold:disabled { opacity: .45; cursor: not-allowed; }
.btn-secondary { background: transparent; border: 1px solid var(--border); border-radius: 6px; color: var(--text-muted); cursor: pointer; font-size: 0.85rem; padding: 0.5rem 1rem; transition: all .15s; }
.btn-secondary:hover { background: var(--bg-raised); color: var(--text-primary); }

.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,.65); backdrop-filter: blur(4px); z-index: 100; display: flex; align-items: center; justify-content: center; padding: 1rem; }
.modal { background: var(--bg-card); border: 1px solid var(--border); border-radius: 12px; width: 100%; max-width: 580px; max-height: 90vh; overflow-y: auto; }
.modal__header { display: flex; justify-content: space-between; align-items: center; padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border); }
.modal__header h2 { font-size: 1.1rem; color: var(--text-primary); margin: 0; }
.close-btn { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 1rem; }
.modal__body { padding: 1.25rem 1.5rem; display: flex; flex-direction: column; gap: 0.85rem; }
.modal__footer { display: flex; justify-content: flex-end; gap: 0.75rem; padding: 1rem 1.5rem; border-top: 1px solid var(--border); }

.field { display: flex; flex-direction: column; gap: 0.35rem; }
.field.f2 { flex: 2; }
.field label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: .05em; }
.field input, .field select, .field textarea {
  background: var(--bg-raised); border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-primary); font-size: 0.875rem; padding: 0.5rem 0.75rem; outline: none; font-family: inherit;
}
.field input:focus, .field select:focus, .field textarea:focus { border-color: var(--gold); }
.field textarea { resize: vertical; }
.field-row { display: flex; gap: 0.75rem; }

.state-msg { color: var(--text-muted); padding: 3rem; text-align: center; }
.dim { color: var(--text-muted); }
</style>
