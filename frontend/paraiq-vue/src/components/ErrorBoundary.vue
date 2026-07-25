<template>
  <div v-if="!error" style="display: contents">
    <slot />
  </div>
  <div v-else class="eb-fallback">
    <div class="eb-icon">⚠</div>
    <div class="eb-title">Something went wrong</div>
    <div class="eb-message">{{ errorMessage }}</div>
    <div class="eb-actions">
      <button class="eb-btn eb-btn--primary" @click="reset">↺ Try again</button>
      <button class="eb-btn eb-btn--secondary" @click="goHome">← Dashboard</button>
    </div>
    <details v-if="isDev" class="eb-details">
      <summary>Developer info</summary>
      <pre class="eb-stack">{{ errorStack }}</pre>
    </details>
  </div>
</template>

<script setup>
import { ref, onErrorCaptured } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  context: { type: String, default: '' },
})

const router     = useRouter()
const error      = ref(null)
const errorStack = ref('')
const isDev      = import.meta.env.DEV

const errorMessage = ref('An unexpected error occurred in this section.')

onErrorCaptured((err, instance, info) => {
  error.value      = err
  errorStack.value = err?.stack || String(err)
  errorMessage.value = err?.message || 'An unexpected error occurred.'
  console.error(`[ErrorBoundary${props.context ? ':' + props.context : ''}]`, err, info)
  return false // prevent propagation
})

function reset() {
  error.value = null
  // If reset still fails (error persists), force a full reload
  setTimeout(() => {
    if (error.value) window.location.reload()
  }, 100)
}

function goHome() {
  error.value = null
  if (router.currentRoute.value.path === '/dashboard') {
    window.location.reload()
  } else {
    router.push('/dashboard')
  }
}
</script>

<style scoped>
.eb-fallback {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 0.75rem;
  padding: 4rem 2rem;
  text-align: center;
  min-height: 300px;
}
.eb-icon    { font-size: 2.5rem; color: var(--gold, #c89b3c); opacity: 0.6; }
.eb-title   { font-size: 1.1rem; font-weight: 600; color: var(--color-text-primary, #e2e8f0); }
.eb-message { font-size: 0.875rem; color: var(--color-text-secondary, #64748b); max-width: 400px; line-height: 1.5; }
.eb-actions { display: flex; gap: 0.75rem; margin-top: 0.5rem; }
.eb-btn { border-radius: 6px; cursor: pointer; font-size: 0.82rem; padding: 0.45rem 1rem; transition: opacity .15s; }
.eb-btn--primary   { background: var(--gold, #c89b3c); border: none; color: #0a0a14; font-weight: 600; }
.eb-btn--secondary { background: transparent; border: 1px solid var(--color-border-secondary, #1e2530); color: var(--color-text-secondary, #64748b); }
.eb-btn:hover { opacity: 0.8; }
.eb-details { margin-top: 1rem; width: 100%; max-width: 600px; text-align: left; }
.eb-details summary { color: var(--color-text-secondary, #64748b); cursor: pointer; font-size: 0.75rem; }
.eb-stack { background: #0d1117; border: 1px solid #1e2530; border-radius: 6px; color: #fc8181; font-size: 0.72rem; margin-top: 0.5rem; overflow-x: auto; padding: 1rem; white-space: pre-wrap; word-break: break-all; }
</style>
