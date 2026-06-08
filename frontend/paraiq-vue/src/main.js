import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/global.css'
import './assets/nlp-views.css'
import '@tabler/icons-webfont/dist/tabler-icons.min.css'

const app = createApp(App)
app.use(createPinia())
app.use(router)

// Global Vue error handler
app.config.errorHandler = (err, instance, info) => {
  console.error('[Vue global error]', err, info)
}

// Uncaught promise rejections
window.addEventListener('unhandledrejection', (event) => {
  if (event.reason?.name === 'AxiosError') return
  console.error('[Unhandled rejection]', event.reason)
})

// Offline / online detection
window.addEventListener('offline', () => {
  const ev = new CustomEvent('paraiq:offline')
  window.dispatchEvent(ev)
})

window.addEventListener('online', () => {
  const ev = new CustomEvent('paraiq:online')
  window.dispatchEvent(ev)
})

app.mount('#app')
