<template>
  <div class="shell">
    <Sidebar />

    <!-- Mobile backdrop — click to close -->
    <Transition name="backdrop">
      <div
        v-if="isOpen"
        class="shell__backdrop"
        aria-hidden="true"
        @click="close"
      />
    </Transition>

    <div class="shell__body">
      <TopBar />
      <main class="shell__main">
        <RouterView v-slot="{ Component }">
          <Transition name="fade" mode="out-in">
            <component :is="Component" :key="route.fullPath" />
          </Transition>
        </RouterView>
      </main>
    </div>
  </div>
</template>

<script setup>
import { useRoute } from 'vue-router'
import Sidebar from './Sidebar.vue'
import TopBar  from './TopBar.vue'
import { useSidebar } from '@/composables/useSidebar'

const route = useRoute()
const { isOpen, close } = useSidebar()
</script>

<style scoped>
.shell {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.shell__body {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--bg-base);
}

.shell__main {
  flex: 1;
  overflow-y: auto;
  padding: 32px 36px;
}

/* Backdrop — only rendered on mobile (v-if guards it) */
.shell__backdrop {
  position: fixed;
  inset: 0;
  z-index: 199;
  background: rgba(0, 0, 0, 0.55);
}

/* Backdrop transition */
.backdrop-enter-active,
.backdrop-leave-active { transition: opacity 0.22s ease; }
.backdrop-enter-from,
.backdrop-leave-to      { opacity: 0; }

/* Route transition */
.fade-enter-active,
.fade-leave-active { transition: opacity 0.18s ease; }
.fade-enter-from,
.fade-leave-to     { opacity: 0; }

/* Mobile: body fills full width, backdrop is relevant */
@media (max-width: 899px) {
  .shell__main {
    padding: 20px 18px;
  }
}
</style>
