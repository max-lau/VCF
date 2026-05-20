<template>
  <div class="mon">

    <!-- Header -->
    <div class="mon__header">
      <div>
        <h1 class="mon__title">System Monitor</h1>
        <p class="mon__sub">Last updated: {{ lastUpdated || '—' }}</p>
      </div>
      <div class="mon__controls">
        <select v-model="statHours" class="mon__select" @change="loadStats">
          <option :value="1">Last 1 hour</option>
          <option :value="6">Last 6 hours</option>
          <option :value="24">Last 24 hours</option>
          <option :value="72">Last 3 days</option>
        </select>
        <button class="mon__refresh" :class="{ spinning: refreshing }" @click="loadAll" aria-label="Refresh">
          <i class="ti ti-refresh"></i>
        </button>
      </div>
    </div>

    <!-- ── System health ───────────────────────────────────────────────── -->
    <div class="mon__section-label">System health</div>
    <div class="mon__cards">
      <div class="mon__card" :class="healthClass(health.cpu, 80, 95)">
        <div class="mon__card-val">{{ health.cpu != null ? health.cpu + '%' : '—' }}</div>
        <div class="mon__card-label">CPU usage</div>
        <div class="mon__card-bar"><div class="mon__card-fill" :style="{ width: (health.cpu||0) + '%' }"></div></div>
      </div>
      <div class="mon__card" :class="healthClass(health.memory?.percent, 80, 90)">
        <div class="mon__card-val">{{ health.memory ? health.memory.percent + '%' : '—' }}</div>
        <div class="mon__card-label">Memory · {{ health.memory ? health.memory.used_gb + ' / ' + health.memory.total_gb + ' GB' : '' }}</div>
        <div class="mon__card-bar"><div class="mon__card-fill" :style="{ width: (health.memory?.percent||0) + '%' }"></div></div>
      </div>
      <div class="mon__card" :class="healthClass(health.disk?.percent, 80, 90)">
        <div class="mon__card-val">{{ health.disk ? health.disk.percent + '%' : '—' }}</div>
        <div class="mon__card-label">Disk · {{ health.disk ? health.disk.free_gb + ' GB free' : '' }}</div>
        <div class="mon__card-bar"><div class="mon__card-fill" :style="{ width: (health.disk?.percent||0) + '%' }"></div></div>
      </div>
      <div class="mon__card mon__card--neutral">
        <div class="mon__card-val">{{ health.uptime_seconds ? formatUptime(health.uptime_seconds) : '—' }}</div>
        <div class="mon__card-label">Server uptime</div>
      </div>
    </div>

    <!-- ── Cloudflare ─────────────────────────────────────────────────── -->
    <div class="mon__section-label">Cloudflare</div>
    <div class="mon__cf-row">
      <div class="mon__cf-card">
        <div class="mon__cf-label">Platform status</div>
        <div class="mon__cf-val" :class="cfStatusClass(cf.public_status?.indicator)">
          <span class="mon__dot" :class="cfDotClass(cf.public_status?.indicator)"></span>
          {{ cf.public_status?.description || '—' }}
        </div>
      </div>
      <div class="mon__cf-card">
        <div class="mon__cf-label">Zone (para-iq.com)</div>
        <div class="mon__cf-val" :class="cf.zone?.status === 'active' ? 'mon__cf--ok' : 'mon__cf--warn'">
          <span class="mon__dot" :class="cf.zone?.status === 'active' ? 'mon__dot--green' : 'mon__dot--amber'"></span>
          {{ cf.zone?.status || '—' }} · {{ cf.zone?.plan || '' }}
        </div>
      </div>
      <div class="mon__cf-card">
        <div class="mon__cf-label">Requests (last hour)</div>
        <div class="mon__cf-val">
          {{ cf.analytics ? cf.analytics.requests_total.toLocaleString() : cf.analytics_error ? 'Unavailable' : '—' }}
          <span v-if="cf.analytics" class="mon__cf-sub"> · {{ Math.round(cf.analytics.requests_cached / cf.analytics.requests_total * 100 || 0) }}% cached</span>
        </div>
      </div>
      <div class="mon__cf-card">
        <div class="mon__cf-label">Threats blocked (last hour)</div>
        <div class="mon__cf-val" :class="(cf.analytics?.threats_total || 0) > 0 ? 'mon__cf--warn' : ''">
          {{ cf.analytics ? cf.analytics.threats_total.toLocaleString() : '—' }}
        </div>
      </div>
      <div class="mon__cf-card">
        <div class="mon__cf-label">Bandwidth (last hour)</div>
        <div class="mon__cf-val">{{ cf.analytics ? formatBytes(cf.analytics.bandwidth_bytes) : '—' }}</div>
      </div>
    </div>

    <!-- ── API stats ──────────────────────────────────────────────────── -->
    <div class="mon__section-label">API performance · last {{ statHours }}h</div>
    <div class="mon__cards">
      <div class="mon__card mon__card--neutral">
        <div class="mon__card-val">{{ stats.total_requests?.toLocaleString() || '—' }}</div>
        <div class="mon__card-label">Total requests</div>
      </div>
      <div class="mon__card" :class="healthClass(stats.error_rate_pct, 5, 10)">
        <div class="mon__card-val">{{ stats.error_rate_pct != null ? stats.error_rate_pct + '%' : '—' }}</div>
        <div class="mon__card-label">5xx error rate · {{ stats.server_errors }} errors</div>
      </div>
      <div class="mon__card" :class="healthClass(stats.avg_response_ms, 500, 1500)">
        <div class="mon__card-val">{{ stats.avg_response_ms != null ? stats.avg_response_ms + ' ms' : '—' }}</div>
        <div class="mon__card-label">Avg response time</div>
      </div>
      <div class="mon__card mon__card--neutral">
        <div class="mon__card-val">{{ stats.client_errors ?? '—' }}</div>
        <div class="mon__card-label">4xx client errors</div>
      </div>
    </div>

    <!-- ── Top endpoints ─────────────────────────────────────────────── -->
    <div v-if="stats.top_endpoints?.length" class="mon__section-label">Top endpoints</div>
    <div v-if="stats.top_endpoints?.length" class="mon__table-wrap">
      <table class="mon__table">
        <thead><tr>
          <th>Endpoint</th><th>Requests</th><th>Avg ms</th><th>Errors</th>
        </tr></thead>
        <tbody>
          <tr v-for="ep in stats.top_endpoints" :key="ep.endpoint">
            <td class="mon__mono">{{ ep.endpoint }}</td>
            <td>{{ ep.count }}</td>
            <td :class="ep.avg_ms > 1000 ? 'mon__warn' : ''">{{ ep.avg_ms }}</td>
            <td :class="ep.errors > 0 ? 'mon__err' : ''">{{ ep.errors }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── PM2 processes ─────────────────────────────────────────────── -->
    <div class="mon__section-label">PM2 processes</div>
    <div class="mon__table-wrap">
      <table class="mon__table">
        <thead><tr>
          <th>Name</th><th>Status</th><th>CPU</th><th>Memory</th><th>Restarts</th><th>PID</th>
        </tr></thead>
        <tbody>
          <tr v-for="p in health.processes" :key="p.name">
            <td class="mon__proc-name">{{ p.name }}</td>
            <td>
              <span class="mon__status-badge" :class="p.status === 'online' ? 'mon__status--ok' : 'mon__status--err'">
                <span class="mon__dot" :class="p.status === 'online' ? 'mon__dot--green' : 'mon__dot--red'"></span>
                {{ p.status }}
              </span>
            </td>
            <td :class="p.cpu > 80 ? 'mon__warn' : ''">{{ p.cpu }}%</td>
            <td>{{ p.memory_mb }} MB</td>
            <td :class="p.restarts > 10 ? 'mon__warn' : ''">{{ p.restarts }}</td>
            <td class="mon__dim">{{ p.pid }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- ── Risk assessments ─────────────────────────────────────────────── -->
    <div class="mon__section-label">
      AI risk assessments
      <span class="mon__count">every 30 min · last {{ riskLog.length }}</span>
    </div>
    <div v-if="!riskLog.length" class="mon__dim" style="font-size:.8rem;margin-bottom:1rem">
      No assessments yet — first run in progress…
    </div>
    <div v-for="r in riskLog" :key="r.id" :class="['mon__risk-row', `mon__risk-row--${r.risk_level}`]">
      <div class="mon__risk-meta">
        <span :class="['mon__risk-badge', `mon__risk--${r.risk_level}`]">{{ r.risk_level }}</span>
        <span class="mon__dim" style="font-size:.72rem">{{ shortTs(r.assessed_at) }}</span>
        <span v-if="r.alerted" class="mon__alerted">
          <i class="ti ti-bell-ringing"></i> alerted
        </span>
      </div>
      <div class="mon__risk-summary">{{ r.summary }}</div>
      <div v-if="r.prediction" class="mon__risk-pred">
        <i class="ti ti-clock-2" style="font-size:11px"></i> {{ r.prediction }}
      </div>
    </div>

    <!-- ── Event log ─────────────────────────────────────────────────── -->
    <div class="mon__section-label">
      Event log
      <span class="mon__count">{{ events.total?.toLocaleString() }} total</span>
    </div>

    <div class="mon__filters">
      <select v-model="evFilter.status" class="mon__select" @change="loadEvents(1)">
        <option value="">All statuses</option>
        <option value="errors">Errors only (4xx/5xx)</option>
        <option value="ok">OK only (2xx/3xx)</option>
      </select>
      <select v-model="evFilter.method" class="mon__select" @change="loadEvents(1)">
        <option value="">All methods</option>
        <option>GET</option><option>POST</option><option>PUT</option><option>DELETE</option>
      </select>
      <input v-model="evFilter.endpoint" class="mon__input" placeholder="Filter endpoint…"
        @keydown.enter="loadEvents(1)" />
      <button class="mon__btn" @click="loadEvents(1)">Apply</button>
      <button class="mon__btn mon__btn--ghost" @click="clearFilters">Clear</button>
    </div>

    <div class="mon__table-wrap">
      <table class="mon__table mon__table--log">
        <thead><tr>
          <th>Time</th><th>Method</th><th>Endpoint</th><th>Status</th><th>ms</th><th>IP</th>
        </tr></thead>
        <tbody>
          <tr v-for="ev in events.events" :key="ev.id" :class="ev.status_code >= 500 ? 'mon__row--err' : ev.status_code >= 400 ? 'mon__row--warn' : ''">
            <td class="mon__dim mon__mono" style="white-space:nowrap">{{ shortTs(ev.timestamp) }}</td>
            <td><span class="mon__method" :class="`mon__method--${ev.method?.toLowerCase()}`">{{ ev.method }}</span></td>
            <td class="mon__mono mon__endpoint" :title="ev.endpoint">{{ ev.endpoint }}</td>
            <td :class="ev.status_code >= 500 ? 'mon__err' : ev.status_code >= 400 ? 'mon__warn' : 'mon__ok'">
              {{ ev.status_code }}
            </td>
            <td :class="ev.response_time_ms > 1000 ? 'mon__warn' : ''">
              {{ ev.response_time_ms != null ? Math.round(ev.response_time_ms) : '—' }}
            </td>
            <td class="mon__dim">{{ ev.client_ip }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div class="mon__pagination">
      <button class="mon__btn" :disabled="events.page <= 1" @click="loadEvents(events.page - 1)">
        <i class="ti ti-chevron-left"></i> Prev
      </button>
      <span class="mon__page-info">
        Page {{ events.page }} of {{ Math.ceil(events.total / events.per_page) || 1 }}
      </span>
      <button class="mon__btn" :disabled="events.page >= Math.ceil(events.total / events.per_page)"
        @click="loadEvents(events.page + 1)">
        Next <i class="ti ti-chevron-right"></i>
      </button>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import client from '@/api/client'

const health     = ref({ cpu: null, memory: null, disk: null, uptime_seconds: null, processes: [] })
const stats      = ref({})
const cf         = ref({})
const events     = ref({ total: 0, page: 1, per_page: 50, events: [] })
const statHours  = ref(24)
const lastUpdated = ref('')
const refreshing = ref(false)
const evFilter   = ref({ status: '', method: '', endpoint: '' })
const riskLog    = ref([])

async function loadRiskLog() {
  const { data } = await client.get('/monitor/risk-log?limit=10', { _silent: true })
  riskLog.value = data.assessments || []
}
let   timer      = null

async function loadHealth() {
  const { data } = await client.get('/monitor/health', { _silent: true })
  health.value = data
}
async function loadStats() {
  const { data } = await client.get(`/monitor/api-stats?hours=${statHours.value}`, { _silent: true })
  stats.value = data
}
async function loadCF() {
  const { data } = await client.get('/monitor/cloudflare', { _silent: true })
  cf.value = data
}
async function loadEvents(page = 1) {
  const params = new URLSearchParams({ page, per_page: 50 })
  if (evFilter.value.status)   params.set('status',   evFilter.value.status)
  if (evFilter.value.method)   params.set('method',   evFilter.value.method)
  if (evFilter.value.endpoint) params.set('endpoint', evFilter.value.endpoint)
  const { data } = await client.get(`/monitor/events?${params}`, { _silent: true })
  events.value = data
}
function clearFilters() {
  evFilter.value = { status: '', method: '', endpoint: '' }
  loadEvents(1)
}
async function loadAll() {
  refreshing.value = true
  try {
    await Promise.all([loadHealth(), loadStats(), loadCF(), loadEvents(1), loadRiskLog()])
    lastUpdated.value = new Date().toLocaleTimeString()
  } finally {
    refreshing.value = false
  }
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function healthClass(val, warn, danger) {
  if (val == null) return 'mon__card--neutral'
  if (val >= danger) return 'mon__card--danger'
  if (val >= warn)   return 'mon__card--warn'
  return 'mon__card--ok'
}
function cfStatusClass(ind) {
  if (!ind || ind === 'none') return 'mon__cf--ok'
  if (ind === 'minor')        return 'mon__cf--warn'
  return 'mon__cf--err'
}
function cfDotClass(ind) {
  if (!ind || ind === 'none') return 'mon__dot--green'
  if (ind === 'minor')        return 'mon__dot--amber'
  return 'mon__dot--red'
}
function formatUptime(s) {
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  return d > 0 ? `${d}d ${h}h` : `${h}h`
}
function formatBytes(b) {
  if (!b) return '0 B'
  if (b > 1e9) return (b / 1e9).toFixed(1) + ' GB'
  if (b > 1e6) return (b / 1e6).toFixed(1) + ' MB'
  return (b / 1e3).toFixed(1) + ' KB'
}
function shortTs(ts) {
  if (!ts) return '—'
  return ts.replace('T', ' ').replace(/\.\d+.*$/, '').replace('Z', '')
}

onMounted(() => {
  loadAll()
  timer = setInterval(() => { loadHealth(); loadStats() }, 30000)
})
onUnmounted(() => clearInterval(timer))
</script>

<style scoped>
.mon { padding: 2rem; max-width: 1100px; }

.mon__header {
  display: flex; align-items: flex-start; justify-content: space-between;
  margin-bottom: 1.5rem; flex-wrap: wrap; gap: .75rem;
}
.mon__title {
  font-family: var(--font-display); font-size: 1.6rem;
  color: var(--gold); margin: 0;
}
.mon__sub { font-size: .8rem; color: var(--text-tertiary); margin-top: 3px; }
.mon__controls { display: flex; align-items: center; gap: .6rem; }
.mon__select {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: .82rem; padding: .35rem .65rem;
}
.mon__refresh {
  background: none; border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-secondary); cursor: pointer; font-size: 16px;
  padding: .35rem .6rem; transition: color .15s, border-color .15s;
}
.mon__refresh:hover { color: var(--gold); border-color: rgba(201,168,76,.4); }
.mon__refresh.spinning i { display: inline-block; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.mon__section-label {
  font-size: .68rem; color: var(--text-tertiary); text-transform: uppercase;
  letter-spacing: .09em; font-weight: 600; margin: 1.5rem 0 .6rem;
  display: flex; align-items: center; gap: .6rem;
}
.mon__count {
  font-weight: 400; font-size: .68rem;
  background: var(--bg-overlay); border-radius: 20px; padding: 1px 8px;
  color: var(--text-secondary);
}

/* ── Health cards ─────────────────────────────────────────────────────────── */
.mon__cards {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px,1fr)); gap: 10px;
}
.mon__card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 14px 16px;
  border-left: 3px solid transparent;
}
.mon__card--ok      { border-left-color: #4caf79; }
.mon__card--warn    { border-left-color: #ffb74d; }
.mon__card--danger  { border-left-color: var(--red, #e03131); }
.mon__card--neutral { border-left-color: var(--border); }
.mon__card-val   { font-family: var(--font-display); font-size: 1.8rem; font-weight: 300; color: var(--gold); }
.mon__card-label { font-size: .72rem; color: var(--text-tertiary); margin-top: 4px; }
.mon__card-bar   { height: 3px; background: rgba(255,255,255,.07); border-radius: 2px; margin-top: 10px; overflow: hidden; }
.mon__card-fill  { height: 100%; background: var(--gold); border-radius: 2px; transition: width .4s ease; }

/* ── Cloudflare ──────────────────────────────────────────────────────────── */
.mon__cf-row {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(180px,1fr)); gap: 8px;
}
.mon__cf-card {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px;
}
.mon__cf-label { font-size: .68rem; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
.mon__cf-val   { font-size: .82rem; color: var(--text-primary); display: flex; align-items: center; gap: 6px; }
.mon__cf-sub   { font-size: .72rem; color: var(--text-tertiary); }
.mon__cf--ok   { color: #4caf79; }
.mon__cf--warn { color: #ffb74d; }
.mon__cf--err  { color: #ff7070; }

.mon__dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; display: inline-block;
}
.mon__dot--green { background: #4caf79; box-shadow: 0 0 5px #4caf79; }
.mon__dot--amber { background: #ffb74d; box-shadow: 0 0 5px #ffb74d; }
.mon__dot--red   { background: #ff7070; box-shadow: 0 0 5px #ff7070; }

/* ── Tables ──────────────────────────────────────────────────────────────── */
.mon__table-wrap { overflow-x: auto; margin-bottom: .5rem; }
.mon__table {
  width: 100%; border-collapse: collapse;
  font-size: .78rem; font-family: inherit;
}
.mon__table th {
  text-align: left; font-size: .66rem; color: var(--text-tertiary);
  text-transform: uppercase; letter-spacing: .06em;
  padding: .4rem .6rem; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.mon__table td {
  padding: .45rem .6rem; border-bottom: 1px solid rgba(255,255,255,.04);
  color: var(--text-primary); vertical-align: middle;
}
.mon__table--log td { font-size: .75rem; }
.mon__row--err  td { background: rgba(224,49,49,.04); }
.mon__row--warn td { background: rgba(255,183,77,.04); }
.mon__proc-name { font-weight: 500; color: var(--text-primary); }
.mon__mono    { font-family: var(--font-mono); font-size: .72rem; }
.mon__dim     { color: var(--text-tertiary); }
.mon__ok      { color: #4caf79; }
.mon__warn    { color: #ffb74d; }
.mon__err     { color: #ff7070; }
.mon__endpoint { max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.mon__status-badge {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: .7rem; padding: 2px 7px; border-radius: 20px;
}
.mon__status--ok  { background: rgba(76,175,121,.12); color: #4caf79; }
.mon__status--err { background: rgba(224,49,49,.12);  color: #ff7070; }

.mon__method {
  font-size: .68rem; font-weight: 700; padding: 2px 6px;
  border-radius: 3px; font-family: var(--font-mono);
}
.mon__method--get    { background: rgba(74,158,255,.15);  color: #4a9eff; }
.mon__method--post   { background: rgba(76,175,121,.15);  color: #4caf79; }
.mon__method--put    { background: rgba(255,183,77,.15);  color: #ffb74d; }
.mon__method--delete { background: rgba(224,49,49,.15);   color: #ff7070; }
.mon__method--patch  { background: rgba(179,119,255,.15); color: #b377ff; }

/* ── Filters ─────────────────────────────────────────────────────────────── */
.mon__filters {
  display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: .75rem; align-items: center;
}
.mon__input {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-primary); font-size: .82rem;
  padding: .35rem .65rem; flex: 1; min-width: 160px; outline: none;
}
.mon__input:focus { border-color: var(--gold); }
.mon__btn {
  background: var(--gold); border: none; border-radius: 6px;
  color: #000; cursor: pointer; font-size: .78rem; font-weight: 600;
  padding: .35rem .9rem; transition: opacity .15s;
  display: inline-flex; align-items: center; gap: 4px;
}
.mon__btn:hover:not(:disabled) { opacity: .85; }
.mon__btn:disabled { opacity: .4; cursor: not-allowed; }
.mon__btn--ghost {
  background: none; border: 1px solid var(--border);
  color: var(--text-secondary); font-weight: 400;
}
.mon__btn--ghost:hover { border-color: var(--gold); color: var(--gold); }

/* ── Pagination ──────────────────────────────────────────────────────────── */
.mon__risk-row {
  background: var(--bg-card); border: 1px solid var(--border);
  border-radius: 8px; padding: 12px 14px; margin-bottom: 8px;
  border-left: 3px solid transparent;
}
.mon__risk-meta {
  display: flex; align-items: center; gap: 10px; margin-bottom: 6px;
}
.mon__risk-badge {
  font-size: .68rem; font-weight: 700; text-transform: uppercase;
  padding: 2px 8px; border-radius: 20px; letter-spacing: .05em;
}
.mon__risk--ok       { background: rgba(76,175,121,.15);  color: #4caf79; border-left-color: #4caf79; }
.mon__risk--watch    { background: rgba(74,158,255,.15);  color: #4a9eff; border-left-color: #4a9eff; }
.mon__risk--warning  { background: rgba(255,183,77,.15);  color: #ffb74d; border-left-color: #ffb74d; }
.mon__risk--critical { background: rgba(224,49,49,.15);   color: #ff7070; border-left-color: #ff7070; }
.mon__risk-summary { font-size: .82rem; color: var(--text-primary); margin-bottom: 4px; }
.mon__risk-pred    { font-size: .75rem; color: var(--text-tertiary); line-height: 1.5; }
.mon__alerted {
  font-size: .68rem; color: #ffb74d;
  display: flex; align-items: center; gap: 3px;
}

.mon__pagination {
  display: flex; align-items: center; gap: .75rem;
  margin-top: .75rem; justify-content: flex-end;
}
.mon__page-info { font-size: .78rem; color: var(--text-tertiary); }
</style>
