<template>
  <div class="nc-root" ref="rootEl">
    <!-- Bell button -->
    <button class="nc-bell" @click="togglePanel" aria-label="Notifications">
      <i class="ti ti-bell" />
      <span v-if="unread > 0" class="nc-badge">{{ unread > 9 ? '9+' : unread }}</span>
    </button>

    <!-- Panel -->
    <Transition name="nc-panel">
      <div v-if="open" class="nc-panel">
        <div class="nc-panel__header">
          <span class="nc-panel__title">Notifications</span>
          <div class="nc-panel__actions">
            <button v-if="unread > 0" class="nc-action-btn" @click="markAllRead">
              ✓ Mark all read
            </button>
            <button v-if="items.length" class="nc-action-btn" @click="clearRead">
              🗑 Clear read
            </button>
          </div>
        </div>

        <div class="nc-panel__body" ref="bodyEl">
          <div v-if="loading" class="nc-empty">
            <span class="nc-spinner">⟳</span> Loading…
          </div>

          <div v-else-if="!items.length" class="nc-empty">
            <i class="ti ti-bell-off" style="font-size:1.5rem;opacity:0.3" />
            <span>No notifications</span>
          </div>

          <div v-else>
            <div
              v-for="item in items"
              :key="item.id"
              class="nc-item"
              :class="{ 'nc-item--unread': !item.read, [`nc-item--${item.type}`]: true }"
              @click="handleClick(item)"
            >
              <div class="nc-item__icon">{{ typeIcon(item.type) }}</div>
              <div class="nc-item__body">
                <div class="nc-item__title">{{ item.title }}</div>
                <div v-if="item.body" class="nc-item__body-text">{{ cleanBody(item.body) }}</div>
                <div class="nc-item__time">{{ fmtTime(item.created_at) }}</div>
              </div>
              <button class="nc-item__del" @click.stop="deleteItem(item.id)" title="Dismiss">✕</button>
            </div>
          </div>
        </div>

        <div class="nc-panel__footer">
          <span class="nc-footer-count">{{ items.length }} notification{{ items.length !== 1 ? 's' : '' }}</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import client from '@/api/client'

const router  = useRouter()
const open    = ref(false)
const loading = ref(false)
const items   = ref([])
const unread  = ref(0)
const rootEl  = ref(null)
let pollTimer = null

const TYPE_ICONS = {
  deadline: '📅',
  hermes:   '🤖',
  email:    '📧',
  system:   'ℹ',
}
function typeIcon(type) { return TYPE_ICONS[type] || '🔔' }

function cleanBody(body) {
  // Remove internal IDs from display
  return (body || '').replace(/\. ID: [a-z0-9-]+$/, '').replace(/\. card \d+$/, '')
}

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const now = new Date()
  const diff = now - d
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

async function fetchNotifications() {
  try {
    const { data } = await client.get('/notifications?limit=20', { _silent: true })
    items.value  = data.items || []
    unread.value = data.unread || 0
  } catch {}
}

async function markAllRead() {
  try {
    await client.patch('/notifications/read-all')
    items.value.forEach(i => { i.read = true })
    unread.value = 0
  } catch {}
}

async function clearRead() {
  try {
    await client.delete('/notifications/clear-all')
    items.value = items.value.filter(i => !i.read)
  } catch {}
}

async function deleteItem(id) {
  try {
    await client.delete(`/notifications/${id}`)
    items.value = items.value.filter(i => i.id !== id)
    unread.value = items.value.filter(i => !i.read).length
  } catch {}
}

async function handleClick(item) {
  if (!item.read) {
    await client.patch(`/notifications/${item.id}/read`, {}).catch(() => {})
    item.read = true
    unread.value = Math.max(0, unread.value - 1)
  }
  open.value = false
  if (item.link) router.push(item.link)
}

function togglePanel() {
  open.value = !open.value
  if (open.value) {
    loading.value = true
    fetchNotifications().finally(() => { loading.value = false })
  }
}

// Close on outside click
function handleOutsideClick(e) {
  if (rootEl.value && !rootEl.value.contains(e.target)) {
    open.value = false
  }
}

// Poll every 60 seconds for new notifications
onMounted(() => {
  fetchNotifications()
  pollTimer = setInterval(fetchNotifications, 60000)
  document.addEventListener('click', handleOutsideClick)
})

onUnmounted(() => {
  clearInterval(pollTimer)
  document.removeEventListener('click', handleOutsideClick)
})
</script>

<style scoped>
.nc-root { position: relative; }

/* Bell */
.nc-bell {
  position: relative;
  background: none;
  border: none;
  color: var(--text-secondary, #94a3b8);
  cursor: pointer;
  font-size: 18px;
  padding: 6px;
  border-radius: 6px;
  transition: color 0.12s, background 0.12s;
  display: flex; align-items: center; justify-content: center;
}
.nc-bell:hover { color: var(--text-primary, #e2e8f0); background: var(--bg-hover, rgba(255,255,255,0.06)); }
.nc-badge {
  position: absolute;
  top: 2px; right: 2px;
  background: #e03131;
  color: white;
  font-size: 9px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  padding: 0 3px;
  line-height: 1;
}

/* Panel */
.nc-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 340px;
  background: var(--bg-raised, #12151d);
  border: 1px solid var(--border-dim, #1e2530);
  border-radius: 10px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  z-index: 500;
  overflow: hidden;
}
.nc-panel__header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border-dim, #1e2530);
}
.nc-panel__title { font-size: 13px; font-weight: 600; color: var(--text-primary, #e2e8f0); }
.nc-panel__actions { display: flex; gap: 8px; }
.nc-action-btn {
  background: none; border: none;
  color: var(--text-tertiary, #64748b);
  cursor: pointer; font-size: 11px; padding: 2px 6px;
  border-radius: 4px; transition: color 0.12s;
}
.nc-action-btn:hover { color: var(--text-primary, #e2e8f0); }

.nc-panel__body { max-height: 380px; overflow-y: auto; }

.nc-empty {
  display: flex; flex-direction: column; align-items: center;
  gap: 8px; padding: 2rem; color: var(--text-tertiary, #64748b);
  font-size: 13px; text-align: center;
}
.nc-spinner { display: inline-block; animation: spin 1s linear infinite; font-size: 18px; }
@keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }

/* Notification items */
.nc-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-dim, #1e2530);
  cursor: pointer;
  transition: background 0.12s;
}
.nc-item:last-child { border-bottom: none; }
.nc-item:hover { background: var(--bg-hover, rgba(255,255,255,0.04)); }
.nc-item--unread { background: rgba(201,168,76,0.04); }
.nc-item--unread:hover { background: rgba(201,168,76,0.08); }

.nc-item__icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.nc-item__body { flex: 1; min-width: 0; }
.nc-item__title {
  font-size: 12px; font-weight: 500;
  color: var(--text-primary, #e2e8f0);
  line-height: 1.4; margin-bottom: 2px;
}
.nc-item--unread .nc-item__title { color: var(--gold, #c89b3c); }
.nc-item__body-text {
  font-size: 11px; color: var(--text-tertiary, #64748b);
  line-height: 1.4; margin-bottom: 3px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.nc-item__time { font-size: 10px; color: var(--text-tertiary, #64748b); }
.nc-item__del {
  background: none; border: none;
  color: var(--text-tertiary, #64748b);
  cursor: pointer; font-size: 11px; padding: 2px 4px;
  opacity: 0; transition: opacity 0.12s;
  flex-shrink: 0;
}
.nc-item:hover .nc-item__del { opacity: 1; }
.nc-item__del:hover { color: #fc8181; }

/* Type accent borders */
.nc-item--deadline { border-left: 2px solid #e03131; }
.nc-item--hermes   { border-left: 2px solid #7c3aed; }
.nc-item--email    { border-left: 2px solid #1971c2; }
.nc-item--system   { border-left: 2px solid #2f9e44; }

.nc-panel__footer {
  padding: 8px 14px;
  border-top: 1px solid var(--border-dim, #1e2530);
  font-size: 10px; color: var(--text-tertiary, #64748b);
}

/* Panel transition */
.nc-panel-enter-active, .nc-panel-leave-active { transition: all 0.18s ease; }
.nc-panel-enter-from, .nc-panel-leave-to { opacity: 0; transform: translateY(-6px) scale(0.98); }

@media (max-width: 899px) {
  .nc-panel {
    position: fixed;
    top: var(--topbar-h, 52px);
    right: 8px;
    left: 8px;
    width: auto;
  }
}
</style>
