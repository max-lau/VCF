<template>
  <div class="login">
    <div class="login__panel">
      <!-- Brand -->
      <div class="login__brand">
        <span class="login__logo">ParaIQ</span>
        <p class="login__tagline">Legal Intelligence Platform</p>
      </div>

      <!-- Form -->
      <form class="login__form" @submit.prevent="handleLogin" novalidate>
        <div class="field">
          <label class="field__label" for="username">Username</label>
          <input
            id="username"
            v-model="form.username"
            class="piq-input"
            type="text"
            placeholder="your.username"
            autocomplete="username"
            required
          />
        </div>

        <div class="field">
          <label class="field__label" for="password">Password</label>
          <input
            id="password"
            v-model="form.password"
            class="piq-input"
            type="password"
            placeholder="••••••••"
            autocomplete="current-password"
            required
          />
        </div>
        <div v-if="error" class="login__error" role="alert">
          {{ error }}
        </div>

        <button
          type="submit"
          class="piq-btn piq-btn--primary login__submit"
          :disabled="loading"
        >
          <span v-if="loading" class="spinner" aria-hidden="true"></span>
          {{ loading ? 'Signing in…' : 'Sign in' }}
        </button>
      </form>
    </div>

    <!-- Background decoration -->
    <div class="login__bg" aria-hidden="true">
      <div class="login__bg-grid"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth   = useAuthStore()

const form = ref({ username: '', password: '' })
const loading = ref(false)
const error   = ref(null)

onMounted(() => {
  if (auth.isAuthenticated) router.push('/dashboard')
})

async function handleLogin() {
  if (!form.value.username || !form.value.password) {
    error.value = 'Username and password are required.'
    return
  }
  loading.value = true
  error.value   = null

  const result = await auth.login(form.value.username, form.value.password)

  loading.value = false
  if (result.ok) {
    router.push('/dashboard')
  } else {
    error.value = result.error
  }
}
</script>

<style scoped>
.login {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-void);
  position: relative;
  overflow: hidden;
}

.login__panel {
  position: relative;
  z-index: 1;
  width: 360px;
  background: var(--bg-raised);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-lg);
  padding: 40px 36px;
  box-shadow: 0 24px 80px rgba(0,0,0,0.6);
}

.login__brand {
  text-align: center;
  margin-bottom: 36px;
}
.login__logo {
  display: block;
  font-family: var(--font-display);
  font-size: 32px;
  font-weight: 300;
  letter-spacing: 0.1em;
  color: var(--gold);
}
.login__tagline {
  font-size: 12px;
  color: var(--text-tertiary);
  margin-top: 4px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.login__form { display: flex; flex-direction: column; gap: 16px; }

.field__label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  margin-bottom: 6px;
  letter-spacing: 0.03em;
  text-transform: uppercase;
}



.login__error {
  background: rgba(240,62,62,.1);
  border: 1px solid rgba(240,62,62,.25);
  color: var(--red);
  font-size: 13px;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
}

.login__submit {
  width: 100%;
  justify-content: center;
  padding: 10px;
  font-size: 14px;
  margin-top: 4px;
}
.login__submit:disabled { opacity: 0.6; cursor: not-allowed; }

.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(0,0,0,0.2);
  border-top-color: var(--bg-void);
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Background grid */
.login__bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.login__bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(var(--border-dim) 1px, transparent 1px),
    linear-gradient(90deg, var(--border-dim) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse 70% 70% at 50% 50%, black 30%, transparent 100%);
}
</style>
