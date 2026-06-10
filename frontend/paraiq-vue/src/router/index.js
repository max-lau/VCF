import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { usePermissionsStore } from '@/stores/permissions'

// Lazy-load all views
const LoginView       = () => import('@/views/LoginView.vue')
const AppShell        = () => import('@/components/layout/AppShell.vue')
const EmailInboxView  = () => import('@/views/email/EmailInboxView.vue')
const DashboardView   = () => import('@/views/DashboardView.vue')
const ModuleStub      = () => import('@/views/ModuleStub.vue')

// ── Module views (stubbed — replace with real components as you build) ─
const MattersView      = () => import('@/views/matters/MattersView.vue')
const MatterDetailView = () => import('@/views/matters/MatterDetailView.vue')
const CreateCaseView  = () => import('@/views/matters/CreateCase.vue')
const PrivilegeView   = () => import('@/views/privilege/PrivilegeLogView.vue')
const DocumentsView   = () => import('@/views/documents/DocumentsView.vue')
const DiscoveryView   = () => import('@/views/discovery/DiscoveryView.vue')
const IntelligenceView = () => import('@/views/intelligence/CaseIntelligenceFeedView.vue')
const TimelineView     = () => import('@/views/timeline/TimelineView.vue')
const CaseWallView     = () => import('@/views/casewall/CaseWallView.vue')
const DepositionsView  = () => import('@/views/depositions/DepositionsView.vue')
const MotionsView      = () => import('@/views/motions/MotionsView.vue')
const ContractsView    = () => import('@/views/contracts/ContractsView.vue')
const CorrespondenceView = () => import('@/views/correspondence/CorrespondenceView.vue')
const CalendarView       = () => import('@/views/calendar/CalendarView.vue')
const ContactsView       = () => import('@/views/contacts/ContactsView.vue')
const ReportsView        = () => import('@/views/reports/ReportsView.vue')
const ExportsView        = () => import('@/views/exports/ExportsView.vue')
const LegalBertView      = () => import('@/views/legal-bert/LegalBertView.vue')
const AiConfigView       = () => import('@/views/ai-config/AiConfigView.vue')
const SuperAdminMonitorView = () => import('@/views/monitor/SuperAdminMonitorView.vue')
const ClientPortalView   = () => import('@/views/portal/ClientPortalView.vue')
const VoiceShortcutsView  = () => import('@/views/voice/VoiceShortcutsView.vue')
const ClientPortalAccess  = () => import('@/views/portal/ClientPortalAccess.vue')
const LegalResearchView  = () => import('@/views/research/LegalResearchView.vue')
const RiskView           = () => import('@/views/risk/RiskView.vue')
const IntakeView         = () => import('@/views/intake/IntakeView.vue')
const RedactionView      = () => import('@/views/redaction/RedactionView.vue')
const ReviewView         = () => import('@/views/review/ReviewView.vue')
const ScorerView         = () => import('@/views/scorer/ScorerView.vue')
const AnalyzerView     = () => import('@/views/analyzer/AnalyzerView.vue')
const BatchView        = () => import('@/views/batch/BatchView.vue')
const CitationsView    = () => import('@/views/citations/CitationsView.vue')
const CompareView      = () => import('@/views/compare/CompareView.vue')
const CredibilityView  = () => import('@/views/credibility/CredibilityView.vue')
const InterrogationView= () => import('@/views/interrogation/InterrogationView.vue')
const MediaView        = () => import('@/views/media/MediaView.vue')
const ModelView        = () => import('@/views/model/ModelView.vue')
const MultilingualView = () => import('@/views/multilingual/MultilingualView.vue')
const InsightsView     = () => import('@/views/insights/InsightsView.vue')
const AuditLogView       = () => import('@/views/audit/AuditLogView.vue')
const EnclaveView        = () => import('@/views/enclave/EnclaveManagementView.vue')
const UsersView       = () => import('@/views/admin/UsersView.vue')
const AdminView       = () => import('@/views/admin/AdminView.vue')
const BillingView     = () => import('@/views/admin/BillingView.vue')

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

      // ── Case Work ─────────────────────────────────────────────────
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
        path: 'privilege-log',
        name: 'privilege_log',
        component: PrivilegeView,
        meta: { module: 'privilege_log' },
      },
      {
        path: 'timeline',
        name: 'timeline',
        component: TimelineView,
        meta: { module: 'timeline' },
      },
      {
        path: 'case-wall',
        name: 'case_wall',
        component: CaseWallView,
        meta: { module: 'matters' },
      },
      {
        path: 'discovery',
        name: 'discovery',
        component: DiscoveryView,
        meta: { module: 'discovery' },
      },
      {
        path: 'depositions',
        name: 'depositions',
        component: DepositionsView,
        meta: { module: 'depositions' },
      },
      {
        path: 'motions',
        name: 'motions',
        component: MotionsView,
        meta: { module: 'motions' },
      },
      {
        path: 'contracts',
        name: 'contracts',
        component: ContractsView,
        meta: { module: 'contracts' },
      },
      { path: 'email-inbox', name: 'email_inbox', component: EmailInboxView },
      {
        path: 'correspondence',
        name: 'correspondence',
        component: CorrespondenceView,
        meta: { module: 'correspondence' },
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

      // ── AI & Analysis ─────────────────────────────────────────────
      {
        path: 'intelligence',
        name: 'intelligence',
        component: IntelligenceView,
        meta: { module: 'legal_bert' },
      },
      {
        path: 'legal-bert',
        name: 'legal_bert',
        component: LegalBertView,
        meta: { module: 'legal_bert' },
      },
      {
        path: 'research',
        name: 'legal_research',
        component: LegalResearchView,
        meta: { module: 'legal_research' },
      },
      { path: 'risk',      name: 'risk',      component: RiskView,      meta: { module: 'risk' } },
      { path: 'intake',    name: 'intake',    component: IntakeView,    meta: { module: 'intake' } },
      { path: 'redaction', name: 'redaction', component: RedactionView, meta: { module: 'redaction' } },
      { path: 'review',    name: 'review',    component: ReviewView,    meta: { module: 'review' } },
      { path: 'scorer',    name: 'scorer',    component: ScorerView,    meta: { module: 'scorer' } },
      { path: 'analyzer',     name: 'analyzer',     component: AnalyzerView },
      { path: 'batch',        name: 'batch',        component: BatchView },
      { path: 'citations',    name: 'citations',    component: CitationsView },
      { path: 'compare',      name: 'compare',      component: CompareView },
      { path: 'credibility',  name: 'credibility',  component: CredibilityView },
      { path: 'interrogation',name: 'interrogation',component: InterrogationView },
      { path: 'media',        name: 'media',        component: MediaView },
      { path: 'model',        name: 'model',        component: ModelView },
      { path: 'multilingual', name: 'multilingual', component: MultilingualView },
      { path: 'insights',     name: 'insights',     component: InsightsView },
      {
        path: 'ai-config',
        name: 'ai_config',
        component: AiConfigView,
        meta: { module: 'ai_config' },
      },
      {
        path: 'exports',
        name: 'exports',
        component: ExportsView,
        meta: { module: 'exports' },
      },
      {
        path: 'reports',
        name: 'reports',
        component: ReportsView,
        meta: { module: 'reports' },
      },

      // ── Client Portal ─────────────────────────────────────────────
      {
        path: 'portal',
        name: 'client_portal',
        component: ClientPortalView,
        meta: { module: 'client_portal' },
      },

      {
        path: 'voice-shortcuts',
        name: 'voice_shortcuts',
        component: VoiceShortcutsView,
      },
      // ── Firm Admin ────────────────────────────────────────────────
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
        path: 'admin/enclave',
        name: 'enclave_mgmt',
        component: EnclaveView,
        meta: { module: 'enclave_mgmt' },
      },
      {
        path: 'admin/billing',
        name: 'billing',
        component: BillingView,
        meta: { module: 'billing' },
      },
      {
        path: 'super-admin/monitor',
        name: 'super_monitor',
        component: SuperAdminMonitorView,
        meta: {},
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
      // Redirect to dashboard with a forbidden flag
      return { name: 'dashboard', query: { forbidden: to.meta.module } }
    }
  }

  return true
})

export default router
