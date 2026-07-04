<template>
  <div class="dashboard">
    <div class="piq-page-header">
      <h2 class="piq-page-title">Good {{ timeOfDay }}, {{ firstName }}</h2>
      <p class="piq-page-subtitle">{{ today }} · {{ firmId }}</p>
    </div>

    <!-- Guide link -->
    <a href="/tutorial.html" target="_blank" class="dashboard__guide">
      <i class="ti ti-book-2" aria-hidden="true"></i>
      New to ParaIQ? Read the user guide
      <i class="ti ti-arrow-right" style="font-size:11px" aria-hidden="true"></i>
    </a>

    <!-- Stats row -->
    <div class="dashboard__stats">
      <div v-for="s in stats" :key="s.label" class="stat-card">
        <div class="stat-card__value">
          <span v-if="statsLoading" class="stat-card__skeleton" />
          <span v-else>{{ s.value }}</span>
        </div>
        <div class="stat-card__label">{{ s.label }}</div>
        <div v-if="s.sub" class="stat-card__sub">{{ s.sub }}</div>
      </div>
    </div>

    <!-- Forbidden notice -->
    <div v-if="forbiddenModule" class="dashboard__forbidden">
      You don't have access to <strong>{{ forbiddenModule }}</strong>.
    </div>

    <!-- Two-column widget row -->
    <div class="dashboard__widgets">

      <!-- Upcoming Deadlines -->
      <div class="widget">
        <div class="widget__header">
          <span class="widget__title">📅 Upcoming Deadlines</span>
          <RouterLink to="/calendar" class="widget__link">View all →</RouterLink>
        </div>
        <div v-if="deadlinesLoading" class="widget__loading">Loading…</div>
        <div v-else-if="!upcomingDeadlines.length" class="widget__empty">No upcoming deadlines in the next 30 days.</div>
        <div v-else class="deadline-list">
          <div v-for="ev in upcomingDeadlines" :key="ev.id" class="deadline-item">
            <div class="deadline-dot" :class="urgencyClass(ev.due_date)"></div>
            <div class="deadline-body">
              <div class="deadline-title">{{ ev.title }}</div>
              <div class="deadline-meta">
                <span class="deadline-type">{{ ev.event_type }}</span>
                <span class="deadline-date" :class="urgencyClass(ev.due_date)">
                  {{ fmtDeadlineDate(ev.due_date) }}
                </span>
              </div>
            </div>
            <span v-if="ev.is_court_date" class="court-badge">⚖ Court</span>
          </div>
        </div>
      </div>

      <!-- Risk Heatmap -->
      <div class="widget">
        <div class="widget__header">
          <span class="widget__title">🔥 Risk Overview</span>
          <RouterLink to="/matters" class="widget__link">View matters →</RouterLink>
        </div>
        <div v-if="statsLoading" class="widget__loading">Loading…</div>
        <div v-else class="risk-heatmap">
          <div v-for="(count, level) in riskBreakdown" :key="level" class="risk-bar-row">
            <span class="risk-label">{{ level }}</span>
            <div class="risk-bar-track">
              <div class="risk-bar-fill"
                :class="`risk-bar--${level}`"
                :style="{ width: riskPct(count) + '%' }">
              </div>
            </div>
            <span class="risk-count">{{ count }}</span>
          </div>
          <div class="risk-total">{{ totalCases }} total cases</div>
          <!-- Most active cases -->
          <div class="widget__sub-title">Most Active</div>
          <div v-for="c in mostActiveCases" :key="c.case_number" class="active-case">
            <span class="active-case__num">{{ c.case_number }}</span>
            <span class="active-case__name">{{ c.client_name }}</span>
            <span class="active-case__docs">{{ c.doc_count }} docs</span>
          </div>
        </div>
      </div>

      <!-- Activity Feed -->
      <div class="widget widget--wide">
        <div class="widget__header">
          <span class="widget__title">⚡ Recent Activity</span>
          <button class="widget__link" @click="refreshActivity">↻ Refresh</button>
        </div>
        <div v-if="activityLoading" class="widget__loading">Loading…</div>
        <div v-else-if="!activityFeed.length" class="widget__empty">No recent activity.</div>
        <div v-else class="activity-feed">
          <div v-for="item in activityFeed" :key="item.id" class="activity-item">
            <span class="activity-icon">{{ item.icon }}</span>
            <div class="activity-body">
              <div class="activity-title">{{ item.title }}</div>
              <div class="activity-meta">{{ item.meta }}</div>
            </div>
            <span class="activity-time">{{ item.time }}</span>
          </div>
        </div>
      </div>

      <!-- Hermes Activity -->
      <div class="widget widget--wide">
        <div class="widget__header">
          <span class="widget__title">🤖 Hermes Activity</span>
          <span class="widget__badge">AI Agent</span>
        </div>
        <div v-if="hermesLoading" class="widget__loading">Loading…</div>
        <div v-else-if="!hermesActivity.length" class="widget__empty">No Hermes activity yet. Hermes monitors cases every 15 minutes.</div>
        <div v-else class="hermes-feed">
          <div v-for="h in hermesActivity" :key="h.id" class="hermes-item">
            <div class="hermes-item__left">
              <span class="hermes-dot"></span>
              <div>
                <div class="hermes-title">{{ h.title }}</div>
                <div class="hermes-meta">{{ h.meta }}</div>
              </div>
            </div>
            <span class="hermes-time">{{ h.time }}</span>
          </div>
        </div>
      </div>
      <!-- Automation Spec (Fable 5 corrections) -->
      <div class="widget widget--wide">
        <div class="widget__header">
          <span class="widget__title">⚙️ Automation Levels</span>
          <span class="widget__badge">Fable 5</span>
        </div>
        <div class="autospec-table">
          <div class="autospec-row autospec-row--header">
            <span class="autospec-feature">Feature</span>
            <span class="autospec-level">Level</span>
            <span class="autospec-guard">Guard / Constraint</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">📅 SoL Tracker</span>
            <span class="autospec-badge autospec-badge--assist">assist</span>
            <span class="autospec-guard">Attorney verification stamp required before any deadline is set</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">🗄️ Data Retention Purge</span>
            <span class="autospec-badge autospec-badge--semi">semi</span>
            <span class="autospec-guard">Litigation hold check gate must clear before purge executes</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">💳 Billing Cap Auto-Pause</span>
            <span class="autospec-badge autospec-badge--assist">alerts only</span>
            <span class="autospec-guard">Never pause deadline-adjacent work — alert only</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">⚖️ Conflict Check</span>
            <span class="autospec-badge autospec-badge--semi">semi</span>
            <span class="autospec-guard">No hard block — routes to waiver workflow for attorney review</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">📂 Matter Status Progression</span>
            <span class="autospec-badge autospec-badge--semi">semi</span>
            <span class="autospec-guard">One-tap confirm required with trigger evidence shown</span>
          </div>
          <div class="autospec-row">
            <span class="autospec-feature">💬 Client FAQ Auto-Responder</span>
            <span class="autospec-badge autospec-badge--assist">assist</span>
            <span class="autospec-guard">Structured data lookups only — no generated prose on merits</span>
          </div>
        </div>
      </div>

    </div>

    <!-- Quick access grid -->
    <div class="dashboard__grid">
      <RouterLink v-for="card in visibleCards" :key="card.to" :to="card.to" class="module-card">
        <span class="module-card__icon" aria-hidden="true">{{ card.icon }}</span>
        <div>
          <div class="module-card__name">{{ card.name }}</div>
          <div class="module-card__desc">{{ card.desc }}</div>
        </div>
        <span v-if="card.badge" class="piq-badge piq-badge--gold module-card__badge">{{ card.badge }}</span>
      </RouterLink>
    </div>
  </div>

        <!-- YubiKey Registration Panel -->
        <div class="mt-6 p-4 bg-blue-50 border border-blue-200 rounded-lg shadow-sm">
          <h3 class="text-lg font-medium text-blue-900">🔐 Hardware Security (Anti-USB Hack)</h3>
          <p class="text-sm text-blue-700 mt-1 mb-3">Protect against physical USB attacks. Register a YubiKey to require a physical tap during login.</p>
          <button type="button" @click="registerYubiKey" class="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500">
            Register New Security Key
          </button>
        </div>

</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import client from '@/api/client'

const auth  = useAuthStore()
const route = useRoute()
const { gates: g } = usePermissions()

const firmId    = auth.firmId
const firstName = computed(() => auth.userEmail?.split('@')[0] || 'Counselor')
const forbiddenModule = computed(() => route.query.forbidden || null)

const hour = new Date().getHours()
const timeOfDay = hour < 12 ? 'morning' : hour < 17 ? 'afternoon' : 'evening'
const today = new Intl.DateTimeFormat('en-US', { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())

// ── Stats ─────────────────────────────────────────────────────────────────
const statsLoading   = ref(true)
const riskBreakdown  = ref({})
const totalCases     = ref(0)
const mostActiveCases = ref([])
const stats = ref([
  { label: 'Active Matters',  value: '—', sub: null },
  { label: 'Depositions',     value: '—', sub: null },
  { label: 'Motions',         value: '—', sub: null },
  { label: 'Pending Reviews', value: '—', sub: null },
])

async function loadStats() {
  statsLoading.value = true
  const [cases, deps, motions, queue] = await Promise.allSettled([
    client.get('/cases/stats',       { _silent: true }),
    client.get('/depositions/stats', { _silent: true }),
    client.get('/motions/stats',     { _silent: true }),
    client.get('/feedback/queue',    { _silent: true }),
  ])
  if (cases.status === 'fulfilled') {
    const d = cases.value.data
    stats.value[0].value = d.active ?? d.total ?? '—'
    stats.value[0].sub   = d.total != null ? `${d.total} total` : null
    riskBreakdown.value  = d.by_risk || {}
    totalCases.value     = d.total || 0
    mostActiveCases.value = d.most_active_cases || []
  }
  if (deps.status === 'fulfilled') {
    const d = deps.value.data
    stats.value[1].value = d.total ?? d.count ?? '—'
    stats.value[1].sub   = d.pending != null ? `${d.pending} pending` : null
  }
  if (motions.status === 'fulfilled') {
    const d = motions.value.data
    stats.value[2].value = d.total ?? d.count ?? '—'
    stats.value[2].sub   = d.draft != null ? `${d.draft} drafts` : null
  }
  if (queue.status === 'fulfilled') {
    const d = queue.value.data
    stats.value[3].value = Array.isArray(d) ? d.length : (d.pending ?? d.count ?? d.total ?? '—')
  }
  statsLoading.value = false
}

function riskPct(count) {
  if (!totalCases.value) return 0
  return Math.round((count / totalCases.value) * 100)
}

// ── Upcoming Deadlines ────────────────────────────────────────────────────
const deadlinesLoading  = ref(true)
const upcomingDeadlines = ref([])

async function loadDeadlines() {
  deadlinesLoading.value = true
  try {
    const { data } = await client.get('/calendar/upcoming?days_ahead=30', { _silent: true })
    upcomingDeadlines.value = Array.isArray(data) ? data.slice(0, 8) : []
  } catch { upcomingDeadlines.value = [] }
  finally { deadlinesLoading.value = false }
}

function urgencyClass(due) {
  if (!due) return 'dot-normal'
  const days = Math.ceil((new Date(due) - new Date()) / 86400000)
  if (days <= 3)  return 'urgent'
  if (days <= 7)  return 'warning'
  return 'normal'
}

function fmtDeadlineDate(d) {
  if (!d) return '—'
  const dt   = new Date(d)
  const days = Math.ceil((dt - new Date()) / 86400000)
  if (days === 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  if (days <= 7)  return `In ${days} days`
  return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

// ── Activity Feed ─────────────────────────────────────────────────────────
const activityLoading = ref(true)
const activityFeed    = ref([])

async function loadActivity() {
  activityLoading.value = true
  try {
    const { data } = await client.get('/notifications?limit=10', { _silent: true })
    const items = (data.items || []).filter(n => n.type !== "hermes").map(n => ({
      id:    n.id,
      icon:  { deadline: '📅', hermes: '🤖', email: '📧', system: 'ℹ' }[n.type] || '🔔',
      title: n.title,
      meta:  n.body ? n.body.replace(/\. ID:.*$/, '').replace(/\. card \d+$/, '').slice(0, 80) : '',
      time:  fmtTime(n.created_at),
    }))
    activityFeed.value = items
  } catch { activityFeed.value = [] }
  finally { activityLoading.value = false }
}

async function refreshActivity() {
  await loadActivity()
}

// ── Hermes Activity ───────────────────────────────────────────────────────
const hermesLoading  = ref(true)
const hermesActivity = ref([])

async function loadHermes() {
  hermesLoading.value = true
  try {
    // Fetch kanban card logs where moved_by_hermes = true
    const { data } = await client.get('/voice/audit?limit=15', { _silent: true })
    const voiceLogs = (data.items || [])
      .filter(v => v.success)
      .map(v => ({
        id:    v.id,
        title: `Voice: "${(v.transcript || '').slice(0, 50)}"`,
        meta:  `${v.action || 'unknown'} · ${Math.round((v.confidence||0)*100)}% confidence · ${v.duration_ms}ms`,
        time:  fmtTime(v.created_at),
      }))

    // Also fetch hermes kanban moves from notifications
    const { data: notifs } = await client.get('/notifications?limit=20', { _silent: true })
    const hermesNotifs = (notifs.items || [])
      .filter(n => n.type === 'hermes')
      .map(n => ({
        id:    'h_' + n.id,
        title: n.title,
        meta:  (n.body || '').replace(/\. card \d+$/, '').slice(0, 80),
        time:  fmtTime(n.created_at),
      }))

    hermesActivity.value = [...hermesNotifs, ...voiceLogs].slice(0, 8)
  } catch { hermesActivity.value = [] }
  finally { hermesLoading.value = false }
}

function fmtTime(ts) {
  if (!ts) return ''
  const d    = new Date(ts)
  const now  = new Date()
  const diff = now - d
  const mins = Math.floor(diff / 60000)
  if (mins < 1)  return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24)  return `${hrs}h ago`
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

onMounted(async () => {
  await Promise.all([loadStats(), loadDeadlines(), loadActivity(), loadHermes()])
})

// ── Module cards ──────────────────────────────────────────────────────────
const ALL_CARDS = [
  { to: '/matters',        icon: '⬡', name: 'Matters',          desc: 'Active cases',           gate: 'matters'       },
  { to: '/documents',      icon: '◻', name: 'Documents',         desc: 'Upload & review',         gate: 'documents'     },
  { to: '/privilege-log',  icon: '◈', name: 'Privilege Log',     desc: 'Review & classify',       gate: 'privilege_log' },
  { to: '/timeline',       icon: '⊣', name: 'Timeline',          desc: 'Case chronology',         gate: 'timeline'      },
  { to: '/discovery',      icon: '◎', name: 'Discovery',         desc: 'Productions & requests',  gate: 'discovery'     },
  { to: '/depositions',    icon: '◷', name: 'Depositions',       desc: 'Transcripts & prep',      gate: 'depositions'   },
  { to: '/motions',        icon: '◈', name: 'Motions',           desc: 'Drafting & filing',       gate: 'motions'       },
  { to: '/contracts',      icon: '⊠', name: 'Contracts',         desc: 'Review & redline',        gate: 'contracts'     },
  { to: '/correspondence', icon: '◬', name: 'Correspondence',    desc: 'Emails & letters',        gate: 'correspondence'},
  { to: '/email-inbox',    icon: '📥', name: 'Email Intake',      desc: 'AI-filtered email feed' },
  { to: '/calendar',       icon: '◫', name: 'Calendar',          desc: 'Deadlines & hearings',    gate: 'calendar'      },
  { to: '/contacts',       icon: '◉', name: 'Contacts',          desc: 'Parties & counsel',       gate: 'contacts'      },
  { to: '/intelligence',   icon: '◈', name: 'Case Intelligence', desc: 'AI signals & deadlines',  gate: 'legal_bert'    },
  { to: '/legal-bert',     icon: '⬡', name: 'Legal-BERT',        desc: 'AI document analysis',    gate: 'legal_bert'    },
  { to: '/research',       icon: '◎', name: 'Research',          desc: 'Case law & statutes',     gate: 'legal_research'},
  { to: '/reports',        icon: '◫', name: 'Reports',           desc: 'Analytics & insights',    gate: 'reports'       },
  { to: '/exports',        icon: '◬', name: 'Exports',           desc: 'PDF & DOCX bundles',      gate: 'exports'       },
  { to: '/portal',         icon: '◉', name: 'Client Portal',     desc: 'Client-facing view',      gate: 'client_portal' },
  { to: '/admin',          icon: '⊡', name: 'Users & Roles',     desc: 'Team management',         gate: 'users_roles',  badge: 'Admin' },
  { to: '/admin/audit',    icon: '◫', name: 'Audit Log',         desc: 'Activity trail',          gate: 'audit_log'     },
  { to: '/admin/enclave',  icon: '⬡', name: 'Enclaves',          desc: 'AI enclave health',       gate: 'enclave_mgmt', badge: 'Admin' },
  { to: '/admin/billing',  icon: '◎', name: 'Billing',           desc: 'Plans & invoices',        gate: 'billing'       },
]
const visibleCards = computed(() => ALL_CARDS.filter(c => !c.gate || g.value[c.gate]))

// --- WebAuthn / YubiKey Registration ---
const registerYubiKey = async () => {
  // Safely attempt to get the logged-in username from Pinia auth store
  let user = '';
  try {
    const { useAuthStore } = await import('@/stores/auth');
    const authStore = useAuthStore();
    user = authStore.user?.username || authStore.username || '';
  } catch(e) {}
  
  // Fallback to prompt if it can't find it automatically
  if (!user) {
    user = prompt("Please enter your username to register a security key:");
  }
  if (!user) return;

  try {
    const beginRes = await fetch(`/api/webauthn/register/begin/${user}`);
    if (!beginRes.ok) throw new Error('Failed to start registration');
    const options = await beginRes.json();

    // This tells the browser to wait for the physical YubiKey tap
    const credential = await navigator.credentials.create({ publicKey: options });

    // Send the new key data to the backend to be saved
    const verifyRes = await fetch(`/api/webauthn/register/complete/${user}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        credential_id: credential.id,
        authenticator_data: btoa(String.fromCharCode(...new Uint8Array(credential.response.authenticatorData))),
        client_data_json: btoa(String.fromCharCode(...new Uint8Array(credential.response.clientDataJSON))),
        signature: btoa(String.fromCharCode(...new Uint8Array(credential.response.signature)))
      })
    });

    if (verifyRes.ok) {
      alert('✅ Security Key registered successfully! You can now use it to log in.');
    } else {
      const err = await verifyRes.json();
      throw new Error(err.detail || 'Registration failed');
    }
  } catch (error) {
    console.error('YubiKey registration error:', error);
    alert('Registration failed: ' + error.message);
  }
};

</script>

<style scoped>
/* ── Stats ──────────────────────────────────────────────────────────────── */
.dashboard__stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}
.stat-card { background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 18px 20px; }
.stat-card__value { font-family: var(--font-display); font-size: 28px; font-weight: 300; color: var(--gold); line-height: 1; margin-bottom: 6px; min-height: 32px; }
.stat-card__skeleton { display: inline-block; width: 48px; height: 28px; border-radius: 4px; background: linear-gradient(90deg, var(--bg-overlay) 25%, var(--border-subtle) 50%, var(--bg-overlay) 75%); background-size: 200% 100%; animation: shimmer 1.4s infinite; }
@keyframes shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
.stat-card__label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.07em; color: var(--text-tertiary); }
.stat-card__sub   { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; opacity: 0.7; }

/* ── Widgets ────────────────────────────────────────────────────────────── */
.dashboard__widgets {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  margin-bottom: 28px;
}
.widget {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 16px 18px;
  min-height: 200px;
}
.widget--wide { grid-column: span 2; }
.widget__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }
.widget__title  { font-size: 13px; font-weight: 600; color: var(--text-primary); }
.widget__link   { font-size: 11px; color: var(--gold); text-decoration: none; background: none; border: none; cursor: pointer; }
.widget__link:hover { opacity: 0.8; }
.widget__badge  { font-size: 10px; background: rgba(127,119,221,0.15); border: 1px solid rgba(127,119,221,0.3); border-radius: 4px; color: #AFA9EC; padding: 2px 7px; }
.widget__loading { color: var(--text-tertiary); font-size: 12px; padding: 1rem 0; }
.widget__empty  { color: var(--text-tertiary); font-size: 12px; padding: 1rem 0; }
.widget__sub-title { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-tertiary); margin: 12px 0 6px; }

/* ── Deadlines ──────────────────────────────────────────────────────────── */
.deadline-list { display: flex; flex-direction: column; gap: 8px; }
.deadline-item { display: flex; align-items: flex-start; gap: 10px; }
.deadline-dot  { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-top: 4px; }
.deadline-dot.urgent  { background: #fc8181; box-shadow: 0 0 0 3px rgba(252,129,129,0.2); }
.deadline-dot.warning { background: #ecc94b; box-shadow: 0 0 0 3px rgba(236,201,75,0.2); }
.deadline-dot.normal  { background: #718096; }
.deadline-body  { flex: 1; min-width: 0; }
.deadline-title { font-size: 12px; font-weight: 500; color: var(--text-primary); margin-bottom: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.deadline-meta  { display: flex; gap: 8px; align-items: center; }
.deadline-type  { font-size: 10px; color: var(--text-tertiary); text-transform: capitalize; }
.deadline-date  { font-size: 10px; font-weight: 600; }
.deadline-date.urgent  { color: #fc8181; }
.deadline-date.warning { color: #ecc94b; }
.deadline-date.normal  { color: var(--text-tertiary); }
.court-badge { font-size: 9px; background: rgba(74,124,247,0.12); border: 1px solid rgba(74,124,247,0.3); border-radius: 3px; color: #4a7cf7; padding: 1px 5px; flex-shrink: 0; }

/* ── Risk heatmap ───────────────────────────────────────────────────────── */
.risk-heatmap { display: flex; flex-direction: column; gap: 8px; }
.risk-bar-row  { display: flex; align-items: center; gap: 8px; }
.risk-label    { font-size: 11px; color: var(--text-tertiary); text-transform: capitalize; width: 55px; flex-shrink: 0; }
.risk-bar-track { flex: 1; height: 8px; background: var(--bg-overlay); border-radius: 4px; overflow: hidden; }
.risk-bar-fill  { height: 100%; border-radius: 4px; transition: width 0.6s ease; }
.risk-bar--high    { background: #fc8181; }
.risk-bar--medium  { background: #ecc94b; }
.risk-bar--low     { background: #48bb78; }
.risk-bar--unknown { background: #718096; }
.risk-count { font-size: 11px; color: var(--text-tertiary); width: 20px; text-align: right; }
.risk-total { font-size: 10px; color: var(--text-tertiary); margin-top: 4px; }
.active-case { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--border-subtle); }
.active-case:last-child { border-bottom: none; }
.active-case__num  { font-size: 10px; font-family: var(--font-mono); color: var(--text-tertiary); flex-shrink: 0; }
.active-case__name { font-size: 11px; color: var(--text-primary); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.active-case__docs { font-size: 10px; color: var(--text-tertiary); flex-shrink: 0; }

/* ── Activity feed ──────────────────────────────────────────────────────── */
.activity-feed { display: flex; flex-direction: column; gap: 0; }
.activity-item { display: flex; align-items: flex-start; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); }
.activity-item:last-child { border-bottom: none; }
.activity-icon  { font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.activity-body  { flex: 1; min-width: 0; }
.activity-title { font-size: 12px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.activity-meta  { font-size: 11px; color: var(--text-tertiary); margin-top: 1px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.activity-time  { font-size: 10px; color: var(--text-tertiary); flex-shrink: 0; }

/* ── Hermes feed ────────────────────────────────────────────────────────── */
.hermes-feed { display: flex; flex-direction: column; gap: 0; }
.hermes-item { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; padding: 8px 0; border-bottom: 1px solid var(--border-subtle); }
.hermes-item:last-child { border-bottom: none; }
.hermes-item__left { display: flex; align-items: flex-start; gap: 10px; flex: 1; min-width: 0; }
.hermes-dot  { width: 8px; height: 8px; border-radius: 50%; background: #AFA9EC; flex-shrink: 0; margin-top: 4px; box-shadow: 0 0 0 3px rgba(127,119,221,0.2); }
.hermes-title { font-size: 12px; font-weight: 500; color: var(--text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.hermes-meta  { font-size: 11px; color: var(--text-tertiary); margin-top: 1px; }
.hermes-time  { font-size: 10px; color: var(--text-tertiary); flex-shrink: 0; }

/* ── Forbidden ──────────────────────────────────────────────────────────── */
.dashboard__forbidden { background: rgba(240,62,62,.08); border: 1px solid rgba(240,62,62,.2); color: var(--red); padding: 10px 16px; border-radius: var(--radius-sm); font-size: 13px; margin-bottom: 24px; }

/* ── Module grid ────────────────────────────────────────────────────────── */
.dashboard__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.module-card { display: flex; align-items: center; gap: 14px; padding: 16px 18px; background: var(--bg-raised); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); text-decoration: none; color: var(--text-primary); transition: background 0.15s, border-color 0.15s, transform 0.15s; position: relative; }
.module-card:hover { background: var(--bg-overlay); border-color: var(--border-active); transform: translateY(-1px); }
.module-card__icon  { font-size: 18px; color: var(--gold); opacity: 0.7; flex-shrink: 0; width: 24px; text-align: center; }
.module-card__name  { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.module-card__desc  { font-size: 12px; color: var(--text-tertiary); margin-top: 1px; }
.module-card__badge { margin-left: auto; flex-shrink: 0; }

.dashboard__guide { display: inline-flex; align-items: center; gap: 7px; font-size: 12px; color: var(--text-tertiary); text-decoration: none; padding: 5px 14px; border: 1px solid var(--border-dim); border-radius: 20px; margin-bottom: 20px; transition: color 0.15s, border-color 0.15s; width: fit-content; }
.dashboard__guide:hover { color: var(--gold); border-color: rgba(201,168,76,.3); }

@media (max-width: 768px) {
  .dashboard__widgets { grid-template-columns: 1fr; }
  .widget--wide { grid-column: span 1; }
}

/* Automation Spec Widget */
.autospec-table       { display: flex; flex-direction: column; gap: 4px; margin-top: 4px; }
.autospec-row         { display: grid; grid-template-columns: 220px 100px 1fr; align-items: center; gap: 12px; padding: 7px 10px; border-radius: 6px; font-size: 13px; }
.autospec-row--header { font-size: 11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .04em; padding-bottom: 2px; }
.autospec-row:not(.autospec-row--header):hover { background: var(--surface-hover, rgba(255,255,255,.04)); }
.autospec-feature     { font-weight: 500; color: var(--text-primary); }
.autospec-guard       { color: var(--text-secondary); font-size: 12px; }
.autospec-badge       { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .04em; text-align: center; }
.autospec-badge--semi   { background: rgba(99,102,241,.18); color: #818cf8; }
.autospec-badge--assist { background: rgba(16,185,129,.15); color: #34d399; }

</style>
