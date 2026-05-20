<template>
  <Teleport to="body">
    <div class="toast-stack" aria-live="polite" aria-atomic="false">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="['toast', `toast--${t.type}`]"
          role="alert"
        >
          <span class="toast__icon">{{ ICONS[t.type] }}</span>
          <span class="toast__msg">{{ t.message }}</span>
          <button class="toast__close" @click="remove(t.id)" aria-label="Dismiss">✕</button>
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup>
import { useToast } from '@/composables/useToast'

const { toasts, remove } = useToast()

const ICONS = {
  error:   '✗',
  warning: '⚠',
  success: '✓',
  info:    'ℹ',
}
</script>

<style scoped>
.toast-stack {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-width: 380px;
  pointer-events: none;
}

.toast {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-md, 6px);
  font-size: 13px;
  line-height: 1.45;
  box-shadow: 0 4px 16px rgba(0,0,0,.35);
  pointer-events: all;
  border-left: 3px solid transparent;
}

.toast--error   { background: #2a1515; border-color: var(--red, #e03131);    color: #fcc; }
.toast--warning { background: #231e0f; border-color: var(--gold, #c89b3c);   color: #f5d9a0; }
.toast--success { background: #0f2318; border-color: #2f9e44;                color: #8ce99a; }
.toast--info    { background: #0f1f2e; border-color: #1971c2;                color: #a5d8ff; }

.toast__icon { font-size: 14px; flex-shrink: 0; margin-top: 1px; }
.toast__msg  { flex: 1; }
.toast__close {
  background: none;
  border: none;
  color: inherit;
  opacity: 0.5;
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  flex-shrink: 0;
  line-height: 1;
}
.toast__close:hover { opacity: 1; }

/* TransitionGroup animations */
.toast-enter-active { transition: all 0.2s ease; }
.toast-leave-active { transition: all 0.18s ease; }
.toast-enter-from   { opacity: 0; transform: translateX(24px); }
.toast-leave-to     { opacity: 0; transform: translateX(24px); }
</style>
