<template>
  <button class="cw-bubble" :class="{ 'cw-bubble--open': open }"
    :aria-label="open ? 'Close assistant' : 'Open ParaIQ Assistant'" @click="toggleOpen">
    <i :class="open ? 'ti ti-x' : 'ti ti-message-circle'" aria-hidden="true"></i>
  </button>
  <Transition name="cw-slide">
    <div v-if="open" class="cw-panel" role="dialog" aria-label="ParaIQ Assistant">
      <div class="cw-header">
        <div class="cw-header__info">
          <div class="cw-header__dot"></div>
          <div>
            <div class="cw-header__title">ParaIQ Assistant</div>
            <div class="cw-header__sub">AI-powered app help</div>
          </div>
        </div>
        <button class="cw-close" aria-label="Close" @click="open = false">
          <i class="ti ti-x" aria-hidden="true"></i>
        </button>
      </div>
      <div class="cw-messages" ref="msgList">
        <div class="cw-msg cw-msg--bot">
          <div class="cw-msg__bubble">Hi! I can help you navigate ParaIQ, understand AI results, or walk through any workflow. What do you need?</div>
        </div>
        <template v-for="(msg, i) in history" :key="i">
          <div :class="['cw-msg', msg.role === 'user' ? 'cw-msg--user' : 'cw-msg--bot']">
            <div class="cw-msg__bubble" v-html="formatMsg(msg.content)"></div>
          </div>
        </template>
        <div v-if="loading" class="cw-msg cw-msg--bot">
          <div class="cw-msg__bubble cw-msg__bubble--typing"><span></span><span></span><span></span></div>
        </div>
        <div v-if="showEscalate" class="cw-escalate">
          <div class="cw-escalate__text">Need to speak with someone?</div>
          <a :href="`mailto:${supportEmail}`" class="cw-escalate__btn">
            <i class="ti ti-mail" aria-hidden="true"></i> Email support
          </a>
        </div>
      </div>
      <div class="cw-input-row">
        <input ref="inputRef" v-model="draft" class="cw-input"
          placeholder="Ask anything about ParaIQ…" :disabled="loading"
          @keydown.enter.prevent="send" />
        <button class="cw-send" :disabled="loading || !draft.trim()" aria-label="Send" @click="send">
          <i class="ti ti-send" aria-hidden="true"></i>
        </button>
      </div>
      <div class="cw-footer">
        <button class="cw-footer__escalate" @click="showEscalate = !showEscalate">
          <i class="ti ti-headset" aria-hidden="true"></i> Talk to a human
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import client from '@/api/client'

const open         = ref(false)
const draft        = ref('')
const loading      = ref(false)
const showEscalate = ref(false)
const history      = ref([])
const msgList      = ref(null)
const inputRef     = ref(null)
const supportEmail = import.meta.env.VITE_SUPPORT_EMAIL || 'support@paraiq.com'

function toggleOpen() {
  open.value = !open.value
  if (open.value) nextTick(() => inputRef.value?.focus())
}

async function scrollBottom() {
  await nextTick()
  if (msgList.value) msgList.value.scrollTop = msgList.value.scrollHeight
}

async function send() {
  const text = draft.value.trim()
  if (!text || loading.value) return
  history.value.push({ role: 'user', content: text })
  draft.value = ''
  loading.value = true
  showEscalate.value = false
  await scrollBottom()
  try {
    const { data } = await client.post('/chat/message', {
      message: text,
      history: history.value.slice(0, -1),
    }, { _silent: true })
    history.value.push({ role: 'assistant', content: data.reply })
    if (data.suggest_escalation) showEscalate.value = true
  } catch {
    history.value.push({ role: 'assistant', content: 'Sorry, I hit an error. Please try again or use the escalation button below.' })
    showEscalate.value = true
  } finally {
    loading.value = false
    await scrollBottom()
  }
}

function formatMsg(text) {
  return text
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n(\d+)\. /g, '<br/><strong>$1.</strong> ')
    .replace(/\n/g, '<br/>')
}
</script>

<style scoped>
.cw-bubble {
  position: fixed; bottom: 24px; right: 24px; z-index: 1000;
  width: 48px; height: 48px; border-radius: 50%;
  background: var(--gold); border: none; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  color: #000; font-size: 20px;
  box-shadow: 0 4px 16px rgba(0,0,0,.4);
  transition: transform 0.2s, background 0.2s;
}
.cw-bubble:hover { transform: scale(1.08); }
.cw-bubble--open { background: var(--bg-raised, #1a1a2a); color: var(--text-secondary); border: 1px solid var(--border-dim); }

.cw-panel {
  position: fixed; bottom: 84px; right: 24px; z-index: 999;
  width: 340px; height: 480px;
  background: var(--bg-base); border: 1px solid var(--border-dim);
  border-radius: 12px; display: flex; flex-direction: column;
  overflow: hidden; box-shadow: 0 8px 40px rgba(0,0,0,.5);
}
.cw-slide-enter-active, .cw-slide-leave-active { transition: opacity 0.2s ease, transform 0.2s ease; }
.cw-slide-enter-from, .cw-slide-leave-to { opacity: 0; transform: translateY(12px); }

.cw-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px; border-bottom: 1px solid var(--border-dim);
  background: var(--bg-void, #0a0a14); flex-shrink: 0;
}
.cw-header__info { display: flex; align-items: center; gap: 10px; }
.cw-header__dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #4caf79; box-shadow: 0 0 6px #4caf79; flex-shrink: 0;
}
.cw-header__title { font-size: 13px; font-weight: 500; color: var(--text-primary); }
.cw-header__sub   { font-size: 10px; color: var(--text-tertiary); margin-top: 1px; }
.cw-close {
  background: none; border: none; cursor: pointer;
  color: var(--text-tertiary); font-size: 15px; padding: 4px; border-radius: 4px;
}
.cw-close:hover { color: var(--text-primary); }

.cw-messages {
  flex: 1; overflow-y: auto; padding: 14px 12px;
  display: flex; flex-direction: column; gap: 10px;
}
.cw-msg { display: flex; }
.cw-msg--user { justify-content: flex-end; }
.cw-msg--bot  { justify-content: flex-start; }
.cw-msg__bubble {
  max-width: 82%; padding: 9px 12px; border-radius: 10px;
  font-size: 12.5px; line-height: 1.55;
}
.cw-msg--user .cw-msg__bubble { background: var(--gold); color: #000; border-bottom-right-radius: 3px; }
.cw-msg--bot  .cw-msg__bubble { background: var(--bg-raised, #1a1a2a); color: var(--text-primary); border: 1px solid var(--border-dim); border-bottom-left-radius: 3px; }
.cw-msg__bubble--typing { display: flex; align-items: center; gap: 4px; padding: 12px 14px; }
.cw-msg__bubble--typing span {
  width: 6px; height: 6px; border-radius: 50%; background: var(--text-tertiary);
  animation: cw-bounce 1.2s infinite;
}
.cw-msg__bubble--typing span:nth-child(2) { animation-delay: .18s; }
.cw-msg__bubble--typing span:nth-child(3) { animation-delay: .36s; }
@keyframes cw-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: .4; }
  40% { transform: translateY(-5px); opacity: 1; }
}
.cw-escalate {
  background: var(--bg-raised, #1a1a2a); border: 1px solid var(--border-dim);
  border-radius: 8px; padding: 10px 12px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
}
.cw-escalate__text { font-size: 11.5px; color: var(--text-secondary); }
.cw-escalate__btn {
  display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;
  color: var(--gold); text-decoration: none;
  background: rgba(201,168,76,.1); border: 1px solid rgba(201,168,76,.25);
  border-radius: 5px; padding: 4px 9px; white-space: nowrap;
}
.cw-escalate__btn:hover { background: rgba(201,168,76,.2); }

.cw-input-row {
  display: flex; gap: 6px; padding: 10px 12px;
  border-top: 1px solid var(--border-dim); flex-shrink: 0;
}
.cw-input {
  flex: 1; background: var(--bg-raised, #1a1a2a); border: 1px solid var(--border-dim);
  border-radius: 7px; color: var(--text-primary); font-size: 12.5px;
  padding: 8px 11px; outline: none; transition: border-color 0.12s;
}
.cw-input:focus { border-color: var(--gold); }
.cw-input::placeholder { color: var(--text-tertiary); }
.cw-input:disabled { opacity: .5; }
.cw-send {
  width: 34px; height: 34px; background: var(--gold); border: none;
  border-radius: 7px; color: #000; font-size: 15px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; flex-shrink: 0; transition: opacity 0.15s;
}
.cw-send:disabled { opacity: .4; cursor: not-allowed; }
.cw-send:not(:disabled):hover { opacity: .85; }

.cw-footer { padding: 6px 12px 10px; flex-shrink: 0; }
.cw-footer__escalate {
  background: none; border: none; cursor: pointer; font-size: 11px;
  color: var(--text-tertiary); display: flex; align-items: center; gap: 5px;
}
.cw-footer__escalate:hover { color: var(--text-secondary); }

@media (max-width: 899px) {
  .cw-panel { right: 12px; bottom: 80px; width: calc(100vw - 24px); height: 420px; }
  .cw-bubble { bottom: 20px; right: 16px; }
}
</style>
