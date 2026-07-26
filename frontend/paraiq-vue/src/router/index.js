import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissionsStore } from '@/stores/permissions'

// Lazy-load all views
const LoginView       = () => import('@/views/LoginView.vue')
const AppShell        = () => import('@/components/layout/AppShell.vue')
const EmailInboxView  = () => import('@/views/email/EmailInboxView.vue')
const DashboardView   = () => import('@/views/DashboardView.vue')

// ── Core VCFClaimsIQ views ─────────────────────────────────────────────
const MattersView      = () => import('@/views/matters/MattersView.vue')
const MatterDetailView = () => import('@/views/matters/MatterDetailView.vue')
const CreateCaseView   = () => import('@/views/matters/CreateCase.vue')
const DocumentsView    = () => import('@/views/documents/DocumentsView.vue')
const DocumentInboxView = () => import('@/views/documents/DocumentInboxView.vue')
const CalendarView       = () => import('@/views/calendar/CalendarView.vue')
const ContactsView       = () => import('@/views/contacts/ContactsView.vue')
const VcfReportsView     = () => import('@/views/reports/VcfReportsView.vue')
const ExportsView        = () => import('@/views/exports/ExportsView.vue')
const AiConfigView       = () => import('@/views/ai-config/AiConfigView.vue')
const SuperAdminMonitorView = () => import('@/views/monitor/SuperAdminMonitorView.vue')
const ClientPortalView   = () => import('@/views/portal/ClientPortalView.vue')
const ClientPortalAccess = () => import('@/views/portal/ClientPortalAccess.vue')
const IntakeView         = () => import('@/views/intake/IntakeView.vue')
const BatchIntakeView    = () => import('@/views/intake/BatchIntakeView.vue')
const EsignView          = () => import('@/views/esign/EsignView.vue')
const ClientPortalManage = () => import('@/views/portal/ClientPortalManageView.vue')
const CommunicationsView = () => import('@/views/communications/CommunicationsView.vue')
const AuditLogView       = () => import('@/views/audit/AuditLogView.vue')
const UsersView          = () => import('@/views/admin/UsersView.vue')
const AdminView          = () => import('@/views/admin/AdminView.vue')

const routes = [
  {
    path: '/client-portal/view/:token',
    name: 'client_portal_access',
    component: ClientPortalAccess,
    meta: { public: true },
  },
  {
    path: '/login',
    name: 'login',
    component: LoginView,
    meta: { public: true },
  },
  {
    path: '/',
    component: AppShell,
    meta: { requiresAuth: true },
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: DashboardView,
      },

      // ── Claim Work ────────────────────────────────────────────────
      {
        path: 'matters/new',
        name: 'create_matter',
        component: CreateCaseView,
        meta: { module: 'matters' },
      },
      {
        path: 'matters/:id',
        name: 'matter_detail',
        component: MatterDetailView,
      },
      {
        path: 'matters',
        name: 'matters',
        component: MattersView,
        meta: { module: 'matters' },
      },
      {
        path: 'documents',
        name: 'documents',
        component: DocumentsView,
        meta: { module: 'documents' },
      },
      {
        path: 'document-inbox',
        name: 'document_inbox',
        component: DocumentInboxView,
        meta: { module: 'documents' },
      },
      { path: 'email-inbox', name: 'email_inbox', component: EmailInboxView },
      {
        path: 'communications',
        name: 'communications',
        component: CommunicationsView,
      },
      {
        path: 'calendar',
        name: 'calendar',
        component: CalendarView,
        meta: { module: 'calendar' },
      },
      {
        path: 'contacts',
        name: 'contacts',
        component: ContactsView,
        meta: { module: 'contacts' },
      },

      // ── VCF Workflow ──────────────────────────────────────────────
      {
        path: 'vcf-deadlines',
        name: 'vcf-deadlines',
        component: () => import('@/views/vcf/DeadlinesView.vue'),
      },
      {
        path: 'vcf-account-prep',
        name: 'vcf_account_prep',
        component: () => import('@/views/vcf/VcfAccountPrep.vue'),
      },

      // ── Documents & Intake ────────────────────────────────────────
      {
        path: 'intake',
        name: 'intake',
        component: IntakeView,
        meta: { module: 'intake' },
      },
      {
        path: 'batch-intake',
        name: 'batch_intake',
        component: BatchIntakeView,
        meta: { module: 'intake' },
      },
      {
        path: 'esign',
        name: 'esign',
        component: EsignView,
      },

      // ── Reports & Admin ───────────────────────────────────────────
      {
        path: 'vcf-reports',
        name: 'vcf_reports',
        component: VcfReportsView,
      },
      {
        path: 'exports',
        name: 'exports',
        component: ExportsView,
        meta: { module: 'exports' },
      },
      {
        path: 'ai-config',
        name: 'ai_config',
        component: AiConfigView,
        meta: { module: 'ai_config' },
      },

      // ── Client Portal ─────────────────────────────────────────────
      {
        path: 'portal',
        name: 'client_portal_manage',
        component: ClientPortalManage,
      },

      // ── Firm Admin ──────────────────────────────────────────────────
      { path: 'admin', component: AdminView },
      {
        path: 'admin/users',
        name: 'users_roles',
        component: UsersView,
        meta: { module: 'users_roles' },
      },
      {
        path: 'admin/audit',
        name: 'audit_log',
        component: AuditLogView,
        meta: { module: 'audit_log' },
      },
      {
        path: 'super-admin/monitor',
        name: 'super_monitor',
        component: SuperAdminMonitorView,
      },
    ],
  },
  // Catch-all
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// ── Navigation guard ───────────────────────────────────────────────────
router.beforeEach(async (to) => {
  const auth  = useAuthStore()
  const perms = usePermissionsStore()

  // Public routes pass through
  if (to.meta.public) return true

  // Not authenticated → login
  if (!auth.isAuthenticated) return { name: 'login' }

  // Initialise permissions if not loaded yet
  if (!perms.loaded) await auth.init()

  // Module-gated route: check read permission
  if (to.meta.module) {
    if (!perms.can(to.meta.module, 'read')) {
      return { name: 'dashboard', query: { forbidden: to.meta.module } }
    }
  }

  return true
})

export default router
