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
app.mount('#app')
