import { ref } from 'vue'

// Module-level ref — shared across every caller (singleton pattern)
const toasts = ref([])
let _id = 0

export function useToast() {
  function add(message, type = 'error', duration = 4500) {
    const id = ++_id
    toasts.value.push({ id, message, type })
    setTimeout(() => remove(id), duration)
  }

  function remove(id) {
    toasts.value = toasts.value.filter(t => t.id !== id)
  }

  // Convenience wrappers
  const toast = {
    error:   (msg, ms) => add(msg, 'error',   ms),
    warning: (msg, ms) => add(msg, 'warning', ms),
    success: (msg, ms) => add(msg, 'success', ms),
    info:    (msg, ms) => add(msg, 'info',    ms),
  }

  return { toasts, add, remove, toast }
}
