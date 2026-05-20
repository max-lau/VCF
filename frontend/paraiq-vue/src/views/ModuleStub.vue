<template>
  <div>
    <div class="piq-page-header">
      <h2 class="piq-page-title">{{ moduleName }}</h2>
      <p class="piq-page-subtitle">
        <span class="piq-badge piq-badge--amber">In development</span>
      </p>
    </div>
    <div class="stub">
      <div class="stub__icon" aria-hidden="true">◎</div>
      <p class="stub__msg">
        This module is being migrated to the Vue frontend.<br />
        The existing HTML version remains accessible at
        <a :href="`/frontend/demo1/${legacyPage}`" target="_blank" class="stub__link">
          /frontend/demo1/{{ legacyPage }}
        </a>
      </p>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  moduleName: { type: String, default: 'Module' },
  moduleKey:  { type: String, default: '' },
})

// Maps module key → existing HTML file for reference during migration
const LEGACY_MAP = {
  matters:        'cases.html',
  documents:      'analyzer.html',
  privilege_log:  'privilege_review.html',
  timeline:       'timeline.html',
  discovery:      'discovery.html',
  depositions:    'deposition.html',
  motions:        'review.html',
  contracts:      'compare.html',
  correspondence: 'intake.html',
  calendar:       'dashboard.html',
  contacts:       'dashboard.html',
  legal_bert:     'analyzer.html',
  legal_research: 'citations.html',
  ai_config:      'model.html',
  exports:        'batch.html',
  reports:        'insights.html',
  client_portal:  'dashboard.html',
  users_roles:    'admin.html',
  audit_log:      'audit.html',
  enclave_mgmt:   'admin.html',
  billing:        'admin.html',
}

const legacyPage = computed(() => LEGACY_MAP[props.moduleKey] || 'index.html')
</script>

<style scoped>
.stub {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 80px 40px;
  background: var(--bg-raised);
  border: 1px solid var(--border-dim);
  border-radius: var(--radius-md);
  text-align: center;
  gap: 20px;
}
.stub__icon {
  font-size: 48px;
  color: var(--text-tertiary);
  opacity: 0.4;
}
.stub__msg {
  font-size: 14px;
  color: var(--text-secondary);
  line-height: 1.8;
  max-width: 420px;
}
.stub__link {
  color: var(--gold);
  text-decoration: none;
  font-family: var(--font-mono);
  font-size: 13px;
}
.stub__link:hover { text-decoration: underline; }
</style>
