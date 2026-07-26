<template>
  <div>
    <div class="piq-page-header">
      <h2 class="piq-page-title">{{ moduleName }}</h2>
      <p class="piq-page-subtitle">
        <span class="piq-badge piq-badge--amber">Not available</span>
      </p>
    </div>
    <div class="stub">
      <div class="stub__icon" aria-hidden="true">◎</div>
      <p class="stub__msg">
        This module is not part of the VCFClaimsIQ workflow.<br />
        Return to the <RouterLink to="/dashboard" class="stub__link">Dashboard</RouterLink>.
      </p>
    </div>
  </div>
</template>

<script setup>
defineProps({
  moduleName: { type: String, default: 'Module' },
  moduleKey:  { type: String, default: '' },
})
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
