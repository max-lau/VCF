<template>
  <nav
    class="sidebar"
    :class="{ 'sidebar--open': isOpen }"
    aria-label="Main navigation"
  >
    <div class="sidebar__brand">
      <span class="sidebar__logo">VCFClaimsIQ</span>
      <span class="sidebar__firm">{{ firmId }}</span>
    </div>

    <div class="sidebar__scroll">
      <NavItem to="/dashboard" icon="layout-dashboard" label="Dashboard" />

      <NavGroup label="Claim Work">
        <NavItem to="/matters"        icon="briefcase"        label="Claims" />
        <NavItem to="/documents"      icon="file-text"        label="Documents" />
        <NavItem to="/communications" icon="mail"             label="Communications" />
        <NavItem to="/email-inbox"    icon="inbox"            label="Email Intake" />
        <NavItem to="/redaction"      icon="eraser"           label="Redaction" />
        <NavItem to="/calendar"       icon="calendar"         label="Calendar" />
        <NavItem to="/contacts"       icon="address-book"     label="Contacts" />
      </NavGroup>

      <NavGroup label="VCF Workflow">
        <NavItem to="/vcf-deadlines" icon="alarm-clock" label="Deadlines" />
        <NavItem to="/vcf-account-prep" icon="user-check" label="VCF Account Prep" />
      </NavGroup>

      <NavGroup label="Documents & Intake">
        <NavItem to="/intake"    icon="scan"        label="OCR Intake" />
        <NavItem to="/document-inbox" icon="inbox"  label="Document Inbox" />
        <NavItem to="/batch-intake" icon="stack-2" label="Batch Intake" />
        <NavItem to="/esign"     icon="pen-tool"    label="E-Signatures" />
      </NavGroup>

      <NavGroup label="Reports">
        <NavItem to="/vcf-reports" icon="report"    label="VCF Reports" />
        <NavItem to="/exports"      icon="download"  label="Exports" />
      </NavGroup>

      <NavGroup label="AI Tools">
        <NavItem to="/medical-nlp" icon="stethoscope" label="Medical NLP" />
      </NavGroup>

      <NavGroup label="Client Portal">
        <NavItem to="/portal" icon="users" label="Client Portal" />
      </NavGroup>

      <NavGroup v-if="isFirmAdmin" label="Firm Admin">
        <NavItem v-if="g.users_roles"  to="/admin"         icon="users"       label="Users & Roles" />
        <NavItem v-if="g.audit_log"    to="/admin/audit"   icon="list-check"  label="Audit Log" />
      </NavGroup>

      <NavGroup v-if="role === 'paraiq_super'" label="Super Admin">
        <NavItem to="/super-admin/monitor" icon="activity" label="System Monitor" />
        <NavItem to="/ai-config" icon="settings" label="AI Config" />
      </NavGroup>
    </div>

    <div class="sidebar__footer">
      <span class="role-chip" :class="`role-chip--${roleTier}`">{{ roleLabel }}</span>
      <span v-if="isScoped" class="scoped-indicator">assigned claims only</span>
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
  acpvcf_super:    'Super Admin',
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