<template>
  <ErrorBoundary context="app">
    <RouterView />
  </ErrorBoundary>
  <UiToast />
  <ChatWidget />
  <div v-if="offline" class="offline-banner">
    ⚠ No internet connection — changes may not be saved
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterView } from 'vue-router'
import UiToast      from '@/components/ui/UiToast.vue'
import ChatWidget   from '@/components/ChatWidget.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'

const offline = ref(!navigator.onLine)

function handleOffline() { offline.value = true }
function handleOnline()  { offline.value = false }

onMounted(() => {
  window.addEventListener('paraiq:offline', handleOffline)
  window.addEventListener('paraiq:online',  handleOnline)
})
onUnmounted(() => {
  window.removeEventListener('paraiq:offline', handleOffline)
  window.removeEventListener('paraiq:online',  handleOnline)
})
</script>

<style scoped>
.offline-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  background: #231e0f;
  border-bottom: 1px solid var(--gold, #c89b3c);
  color: #f5d9a0;
  font-size: 12px;
  padding: 6px 16px;
  text-align: center;
  z-index: 10000;
}
</style>
