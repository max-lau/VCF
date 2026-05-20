<template>
  <RouterLink
    :to="to"
    class="nav-item"
    :class="{ 'nav-item--active': isActive }"
    @click="close"
  >
    <i :class="`ti ti-${icon}`" class="nav-item__icon" aria-hidden="true"></i>
    <span class="nav-item__label">{{ label }}</span>
    <span v-if="badge" class="nav-item__badge" :class="`nav-item__badge--${badgeVariant}`">
      {{ badge }}
    </span>
  </RouterLink>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { useSidebar } from '@/composables/useSidebar'

const props = defineProps({
  to:           String,
  icon:         String,
  label:        String,
  badge:        String,
  badgeVariant: { type: String, default: 'dim' },
})

const route     = useRoute()
const { close } = useSidebar()

const isActive = computed(() =>
  route.path === props.to || route.path.startsWith(props.to + '/')
)
</script>

<style scoped>
.nav-item {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 6px 18px;
  font-size: 13px;
  color: var(--text-secondary);
  text-decoration: none;
  transition: color 0.12s, background 0.12s;
  position: relative;
  cursor: pointer;
  white-space: nowrap;
}
.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.nav-item--active {
  color: var(--gold);
  background: var(--gold-glow);
}
.nav-item--active::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 2px;
  background: var(--gold);
  border-radius: 0 2px 2px 0;
}
.nav-item__icon {
  font-size: 15px;
  width: 16px;
  text-align: center;
  opacity: 0.55;
  flex-shrink: 0;
  line-height: 1;
}
.nav-item--active .nav-item__icon { opacity: 1; }
.nav-item__label { flex: 1; }

.nav-item__badge {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: .05em;
  text-transform: uppercase;
  padding: 1px 5px;
  border-radius: 3px;
}
.nav-item__badge--gold { background: var(--gold-glow);  color: var(--gold); }
.nav-item__badge--dim  { background: var(--bg-overlay); color: var(--text-tertiary); }
.nav-item__badge--blue { background: var(--blue-dim);   color: var(--blue-bright); }
</style>
