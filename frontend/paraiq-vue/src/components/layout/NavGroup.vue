<!-- NavGroup.vue -->
<template>
  <div class="nav-group">
    <div class="nav-group__label">{{ label }}</div>
    <slot />
  </div>
</template>

<script setup>
defineProps({ label: String })
</script>

<style scoped>
.nav-group { margin-bottom: 4px; }
.nav-group__label {
  padding: 8px 18px 4px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .08em;
  text-transform: uppercase;
  color: var(--text-tertiary);
}
</style>
