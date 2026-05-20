<template>
  <RouterView />
  <UiToast />
  <ChatWidget />
</template>

<script setup>
import { onErrorCaptured } from 'vue'
import { RouterView } from 'vue-router'
import UiToast    from '@/components/ui/UiToast.vue'
import ChatWidget from '@/components/ChatWidget.vue'
import { useToast } from '@/composables/useToast'

const { toast } = useToast()

onErrorCaptured((err) => {
  toast.error(err?.message || 'An unexpected error occurred.')
  return false
})
</script>
