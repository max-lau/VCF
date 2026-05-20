<template>
  <header class="topbar">
    <div class="topbar__left">
      <!-- Hamburger — only visible on mobile -->
      <button
        class="topbar__hamburger"
        aria-label="Toggle navigation"
        @click="toggle"
      >
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
          <rect y="2.5"  width="18" height="1.5" rx="0.75" fill="currentColor"/>
          <rect y="8.25" width="18" height="1.5" rx="0.75" fill="currentColor"/>
          <rect y="14"   width="18" height="1.5" rx="0.75" fill="currentColor"/>
        </svg>
      </button>
      <h1 class="topbar__page-title">{{ pageTitle }}</h1>
    </div>

    <div class="topbar__right">
      <span v-if="auth.firmId" class="topbar__firm">{{ auth.firmId }}</span>
      <span class="topbar__email">{{ auth.userEmail }}</span>
      <span v-if="roleBadge" :class="['piq-badge', roleBadge.cls]">{{ roleBadge.label }}</span>
      <button class="piq-btn piq-btn--ghost topbar__logout" @click="handleLogout">
        Sign out
      </button>
    </div>
  </header>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useSidebar } from '@/composables/useSidebar'

const auth   = useAuthStore()
const route  = useRoute()
const router = useRouter()
const { toggle } = useSidebar()

const PAGE_TITLES = {
  dashboard:      'Dashboard',
  matters:        'Matters',
  documents:      'Documents',
  privilege_log:  'Privilege Log',
  timeline:       'Timeline',
  discovery:      'Discovery',
  depositions:    'Depositions',
  motions:        'Motions',
  contracts:      'Contracts',
  correspondence: 'Correspondence',
  calendar:       'Calendar',
  contacts:       'Contacts',
  legal_bert:     'Legal-BERT Analysis',
  legal_research: 'Legal Research',
  ai_config:      'AI Configuration',
  exports:        'Exports',
  reports:        'Reports',
  client_portal:  'Client Portal',
  users_roles:    'Users & Roles',
  audit_log:      'Audit Log',
  enclave_mgmt:   'Enclave Management',
  billing:        'Billing',
}
const pageTitle = computed(() => PAGE_TITLES[route.name] || 'ParaIQ')

const ROLE_BADGES = {
  paraiq_super: { label: 'Super',     cls: 'piq-badge--red'  },
  admin:        { label: 'Admin',     cls: 'piq-badge--gold' },
  partner:      { label: 'Partner',   cls: 'piq-badge--gold' },
  associate:    { label: 'Associate', cls: 'piq-badge--dim'  },
  paralegal:    { label: 'Paralegal', cls: 'piq-badge--dim'  },
  client:       { label: 'Client',    cls: 'piq-badge--dim'  },
}
const roleBadge = computed(() => ROLE_BADGES[auth.role] || null)

async function handleLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.topbar {
  height: var(--topbar-h);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 36px;
  border-bottom: 1px solid var(--border-dim);
  background: var(--bg-base);
  flex-shrink: 0;
}

.topbar__left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar__hamburger {
  display: none; /* hidden on desktop */
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  padding: 5px;
  color: var(--text-secondary);
  border-radius: 4px;
  flex-shrink: 0;
  transition: background 0.12s, color 0.12s;
}
.topbar__hamburger:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.topbar__page-title {
  font-family: var(--font-display);
  font-size: 16px;
  font-weight: 300;
  color: var(--text-primary);
  letter-spacing: 0.01em;
}

.topbar__right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.topbar__firm {
  font-size: 11px;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  border-right: 1px solid var(--border-dim);
  padding-right: 12px;
}

.topbar__email {
  font-size: 12px;
  color: var(--text-tertiary);
}

.topbar__logout {
  font-size: 12px;
  padding: 4px 10px;
}

/* Fallback badge classes */
.piq-badge--dim { background: rgba(255,255,255,.06); color: var(--text-secondary); }
.piq-badge--red { background: rgba(224,49,49,.15);   color: #ff8787; }

/* Mobile */
@media (max-width: 899px) {
  .topbar {
    padding: 0 16px;
  }
  .topbar__hamburger {
    display: flex;
  }
  .topbar__firm,
  .topbar__email {
    display: none;
  }
}
</style>
