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

    <!-- Live stats row -->
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

    <!-- Quick access grid -->
    <div class="dashboard__grid">
      <RouterLink
        v-for="card in visibleCards"
        :key="card.to"
        :to="card.to"
        class="module-card"
      >
        <span class="module-card__icon" aria-hidden="true">{{ card.icon }}</span>
        <div>
          <div class="module-card__name">{{ card.name }}</div>
          <div class="module-card__desc">{{ card.desc }}</div>
        </div>
        <span v-if="card.badge" class="piq-badge piq-badge--gold module-card__badge">
          {{ card.badge }}
        </span>
      </RouterLink>
    </div>
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
const today = new Intl.DateTimeFormat('en-US', {
  weekday: 'long', month: 'long', day: 'numeric'
}).format(new Date())

// ── Live stats ──────────────────────────────────────────────────────────────
const statsLoading = ref(true)
const stats = ref([
  { label: 'Active Matters',    value: '—', sub: null },
  { label: 'Depositions',       value: '—', sub: null },
  { label: 'Motions',           value: '—', sub: null },
  { label: 'Pending Reviews',   value: '—', sub: null },
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
    stats.value[0].sub   = d.total != null && d.active != null
      ? `${d.total} total` : null
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
    stats.value[3].value = Array.isArray(d) ? d.length : (d.count ?? d.total ?? '—')
  }

  statsLoading.value = false
}

onMounted(loadStats)

// ── Module cards ─────────────────────────────────────────────────────────────
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

const visibleCards = computed(() => ALL_CARDS.filter(c => g.value[c.gate]))
</script>

<style scoped>
/* ── Stats row ──────────────────────────────────────────────────────────── */
.dashboard__stats {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
  margin-bottom: 28px;
}
.stat-card {
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  padding: 18px 20px;
}
.stat-card__value {
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 300;
  color: var(--gold);
  line-height: 1;
  margin-bottom: 6px;
  min-height: 32px;
}
.stat-card__skeleton {
  display: inline-block;
  width: 48px;
  height: 28px;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--bg-overlay) 25%, var(--border-subtle) 50%, var(--bg-overlay) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s infinite;
}
@keyframes shimmer {
  0%   { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
.stat-card__label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text-tertiary);
}
.stat-card__sub {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  opacity: 0.7;
}

/* ── Forbidden notice ───────────────────────────────────────────────────── */
.dashboard__forbidden {
  background: rgba(240,62,62,.08);
  border: 1px solid rgba(240,62,62,.2);
  color: var(--red);
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  margin-bottom: 24px;
}
.dashboard__forbidden strong { font-weight: 600; }

/* ── Module grid ────────────────────────────────────────────────────────── */
.dashboard__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.module-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-md);
  text-decoration: none;
  color: var(--text-primary);
  transition: background 0.15s, border-color 0.15s, transform 0.15s;
  position: relative;
}
.module-card:hover {
  background: var(--bg-overlay);
  border-color: var(--border-active);
  transform: translateY(-1px);
}
.module-card__icon {
  font-size: 18px;
  color: var(--gold);
  opacity: 0.7;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
}
.module-card__name  { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.module-card__desc  { font-size: 12px; color: var(--text-tertiary); margin-top: 1px; }
.module-card__badge { margin-left: auto; flex-shrink: 0; }

.dashboard__guide {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-tertiary);
  text-decoration: none;
  padding: 5px 14px;
  border: 1px solid var(--border-dim);
  border-radius: 20px;
  margin-bottom: 20px;
  transition: color 0.15s, border-color 0.15s;
  width: fit-content;
}
.dashboard__guide:hover {
  color: var(--gold);
  border-color: rgba(201,168,76,.3);
}
</style>
