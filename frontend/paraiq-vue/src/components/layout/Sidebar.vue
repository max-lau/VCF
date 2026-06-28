<template>
  <nav
    class="sidebar"
    :class="{ 'sidebar--open': isOpen }"
    aria-label="Main navigation"
  >
    <div class="sidebar__brand">
      <span class="sidebar__logo">ParaIQ</span>
      <span class="sidebar__firm">{{ firmId }}</span>
    </div>

    <div class="sidebar__scroll">
      <NavItem to="/dashboard" icon="layout-dashboard" label="Dashboard" />
      <NavItem to="/search" icon="search" label="Semantic Search" />
      <NavItem to="/esign" icon="pen-tool" label="E-Signatures" />
      <NavItem to="/portal" icon="users" label="Client Portal" />

      <NavGroup label="Case Work">
        <NavItem v-if="g.matters"        to="/matters"        icon="briefcase"        label="Matters" />
        <NavItem v-if="g.documents"      to="/documents"      icon="file-text"        label="Documents" />
        <NavItem v-if="g.privilege_log"  to="/privilege-log"  icon="shield-lock"      label="Privilege Log" />
        <NavItem v-if="g.timeline"       to="/timeline"       icon="timeline"         label="Timeline" />
        <NavItem v-if="g.matters"        to="/case-wall"      icon="layout-board"     label="Case Wall" />
        <NavItem v-if="g.discovery"      to="/discovery"      icon="search"           label="Discovery" />
        <NavItem v-if="g.depositions"    to="/depositions"    icon="microphone"       label="Depositions" />
        <NavItem v-if="g.motions"        to="/motions"        icon="file-certificate" label="Motions" />
        <NavItem v-if="g.contracts"      to="/contracts"      icon="writing"          label="Contracts" />
        <NavItem v-if="g.correspondence" to="/correspondence" icon="mail"             label="Correspondence" />
        <NavItem                          to="/email-inbox"    icon="inbox"            label="Email Intake" />
        <NavItem v-if="g.calendar"       to="/calendar"       icon="calendar"         label="Calendar" />
        <NavItem v-if="g.contacts"       to="/contacts"       icon="address-book"     label="Contacts" />
      </NavGroup>

      <NavGroup label="AI & Analysis">
        <NavItem                          to="/intelligence" icon="brain"             label="Case Intelligence" />
        <NavItem v-if="g.legal_bert"     to="/legal-bert"   icon="robot"             label="Legal-BERT" />
        <NavItem v-if="g.legal_research" to="/research"     icon="book"              label="Research" />
        <NavItem v-if="g.risk"           to="/risk"         icon="alert-triangle"    label="Risk Scoring" />
        <NavItem v-if="g.credibility"    to="/credibility"  icon="scale"             label="Credibility" />
        <NavItem v-if="g.scorer"         to="/scorer"       icon="chart-bar"         label="Summary Scorer" />
        <NavItem v-if="g.insights"       to="/insights"     icon="bulb"              label="Insights" />
        <NavItem v-if="g.reports"        to="/reports"      icon="report"            label="Reports" />
        <NavItem                          to="/morning-brief" icon="sun"               label="Morning Brief" />
        <NavItem v-if="g.exports"        to="/exports"      icon="download"          label="Exports" />
        <NavItem v-if="g.ai_config"      to="/ai-config"    icon="settings"          label="AI Config"
          badge="Admin" badge-variant="gold" />
      </NavGroup>

      <NavGroup label="NLP Tools">
        <NavItem v-if="g.analyzer"      to="/analyzer"      icon="microscope"        label="Analyzer" />
        <NavItem v-if="g.batch"         to="/batch"         icon="stack-2"           label="Batch Analyzer" />
        <NavItem v-if="g.citations"     to="/citations"     icon="quote"             label="Citations" />
        <NavItem v-if="g.compare"       to="/compare"       icon="arrows-diff"       label="Compare" />
        <NavItem v-if="g.interrogation" to="/interrogation" icon="message-question"  label="Interrogation" />
        <NavItem v-if="g.multilingual"  to="/multilingual"  icon="world"             label="Multilingual" />
      </NavGroup>

      <NavGroup label="Document Processing">
        <NavItem v-if="g.intake"    to="/intake"    icon="scan"        label="OCR Intake" />
        <NavItem v-if="g.redaction" to="/redaction" icon="eraser"      label="Redaction" />
        <NavItem v-if="g.media"     to="/media"     icon="player-play" label="Media" />
        <NavItem v-if="g.review"    to="/review"    icon="eye"         label="Review Queue" />
        <NavItem v-if="g.model"     to="/model"     icon="cpu"         label="Fine-Tuned Model" />
      </NavGroup>

      <NavGroup v-if="g.client_portal" label="Client Portal">
        <NavItem to="/portal" icon="door-enter" label="Portal View" />
      </NavGroup>

      <NavGroup label="Workflow">
        <NavItem to="/approvals"      icon="checks"      label="Approval Queue" />
        <NavItem to="/time-capture"   icon="clock"       label="Time Capture" />
        <NavItem to="/client-billing" icon="credit-card" label="Client Billing" />
      </NavGroup>

      <NavGroup label="Voice">
        <NavItem to="/voice-shortcuts" icon="microphone-2" label="Voice Shortcuts" />
      </NavGroup>

      <NavGroup v-if="isFirmAdmin" label="Firm Admin">
        <NavItem v-if="g.users_roles"  to="/admin"         icon="users"       label="Users & Roles" />
        <NavItem v-if="g.audit_log"    to="/admin/audit"   icon="list-check"  label="Audit Log" />
        <NavItem v-if="g.enclave_mgmt" to="/admin/enclave" icon="server"      label="Enclaves" />
        <NavItem v-if="g.billing"      to="/admin/billing" icon="credit-card" label="Billing" />
      </NavGroup>


      <NavGroup v-if="!isFirmAdmin && g.billing" label="Account">
        <NavItem to="/admin/billing" icon="credit-card" label="SaaS Billing" />
      </NavGroup>

      <NavGroup v-if="role === 'paraiq_super'" label="Super Admin">
        <NavItem to="/super-admin/monitor" icon="activity" label="System Monitor" />
      </NavGroup>
    </div>

    <div class="sidebar__footer">
      <span class="role-chip" :class="`role-chip--${roleTier}`">{{ roleLabel }}</span>
      <span v-if="isScoped" class="scoped-indicator">assigned matters only</span>
    </div>
  </nav>
</template>

<script setup>
import { computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissions } from '@/composables/usePermissions'
import { useSidebar } from '@/composables/useSidebar'
import NavGroup from './NavGroup.vue'
import NavItem  from './NavItem.vue'

const auth = useAuthStore()
const { gates: g, role, isFirmAdmin, isScoped, isTier } = usePermissions()
const { isOpen, close } = useSidebar()
const route = useRoute()

const firmId = auth.firmName || auth.firmId

const ROLE_LABELS = {
  paraiq_super:    'Super Admin',
  firm_admin:      'Firm Admin',
  senior_attorney: 'Sr. Attorney',
  associate:       'Associate',
  paralegal:       'Paralegal',
  client_viewer:   'Client Viewer',
  billing_contact: 'Billing',
}
const roleLabel = computed(() => ROLE_LABELS[role.value] || role.value || '—')
const roleTier  = computed(() => {
  if (isTier(1)) return 'admin'
  if (isTier(3)) return 'attorney'
  if (isTier(4)) return 'staff'
  return 'client'
})

watch(() => route.path, () => close())
</script>

<style scoped>
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  background: var(--bg-void);
  border-right: 1px solid var(--border-dim);
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}
.sidebar__brand {
  padding: 20px 18px 16px;
  border-bottom: 1px solid var(--border-dim);
  flex-shrink: 0;
}
.sidebar__logo {
  display: block;
  font-family: var(--font-display);
  font-size: 20px;
  font-weight: 300;
  letter-spacing: 0.08em;
  color: var(--gold);
}
.sidebar__firm {
  display: block;
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.sidebar__scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 0 16px;
}
.sidebar__footer {
  padding: 12px 18px;
  border-top: 1px solid var(--border-dim);
  flex-shrink: 0;
}
.role-chip {
  display: inline-block;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 100px;
  font-weight: 500;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.role-chip--admin    { background: var(--gold-glow);    color: var(--gold); }
.role-chip--attorney { background: var(--blue-dim);     color: var(--blue-bright); }
.role-chip--staff    { background: rgba(62,207,142,.1); color: var(--green); }
.role-chip--client   { background: var(--bg-overlay);  color: var(--text-secondary); }
.scoped-indicator {
  display: block;
  font-size: 10px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

@media (max-width: 899px) {
  .sidebar {
    position: fixed;
    left: 0; top: 0;
    z-index: 200;
    height: 100dvh;
    transform: translateX(calc(-1 * var(--sidebar-w)));
    transition: transform 0.24s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.24s ease;
    box-shadow: none;
  }
  .sidebar--open {
    transform: translateX(0);
    box-shadow: 6px 0 32px rgba(0, 0, 0, 0.5);
  }
}
</style>
