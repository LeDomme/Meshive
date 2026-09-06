<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import { useAuthStore } from "../../stores/auth"

interface ScanSource { id: number; name: string }
interface ScanRun {
  id: number
  library_source_id: number
  status: string
  mode: string
  created_at: string
  models_found: number
  models_added: number
  models_updated: number
  models_missing: number
  error_message: string | null
}
interface ScanQueueItem { id: number; library_source_id: number; source_name: string; status: string; mode: string; position: number | null }
interface ActiveScan { id: number; library_source_id: number; source_name: string; status: string; position: number | null; current_model_name: string | null; models_total: number; models_found: number; models_skipped: number }

const auth = useAuthStore()
const sources = ref<ScanSource[]>([])
const histories = ref<Record<number, ScanRun[]>>({})
const queue = ref<ScanQueueItem[]>([])
const activeScans = ref<ActiveScan[]>([])
const controllingScanId = ref<number | null>(null)
const loading = ref(true)
const startingSourceId = ref<number | null>(null)
const errorMessage = ref("")
const notice = ref("")
const canViewActive = computed(() => auth.can("scans.view") || auth.can("scans.control"))
let activityTimer: number | undefined
let activityRefreshing = false
const expandedHistories = ref<Set<number>>(new Set())
const visibleHistories = computed(() => Object.fromEntries(
  sources.value.map((source) => {
    const history = histories.value[source.id] ?? []
    return [source.id, expandedHistories.value.has(source.id) ? history : history.slice(0, 5)]
  }),
))

function statusLabel(value: string) {
  return ({ completed: "Completed", completed_with_errors: "Completed with issues", cancelled: "Cancelled", pending: "Queued", queued: "Queued", running: "Running", failed: "Failed", error: "Failed" } as Record<string, string>)[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function modeLabel(value: string) {
  return ({ smart: "Smart scan", full: "Full scan", incremental: "Incremental scan", reconcile_images: "Reconcile images", missing_images: "Missing images" } as Record<string, string>)[value] ?? value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase())
}

function statusClass(value: string) {
  if (value === "completed") return "completed"
  if (value === "completed_with_errors") return "issues"
  if (value === "running" || value === "pending" || value === "queued") return "active"
  return "failed"
}

function toggleHistory(sourceId: number) {
  const next = new Set(expandedHistories.value)
  if (next.has(sourceId)) next.delete(sourceId)
  else next.add(sourceId)
  expandedHistories.value = next
}

function showError(error: unknown, fallback: string) {
  errorMessage.value = error instanceof ApiError ? error.message : fallback
}

async function loadScanData() {
  loading.value = true
  errorMessage.value = ""
  try {
    sources.value = await apiRequest<ScanSource[]>("/api/admin/scans/library-sources")
    if (canViewActive.value) {
      try {
        activeScans.value = await apiRequest<ActiveScan[]>("/api/admin/scans/active")
      } catch {
        activeScans.value = []
      }
    }
    if (!auth.can("scans.view")) return
    const historiesBySource = await Promise.all(
      sources.value.map(async (source) => [
        source.id,
        await apiRequest<ScanRun[]>(`/api/admin/library-sources/${source.id}/scans`),
      ] as const),
    )
    histories.value = Object.fromEntries(historiesBySource)
    queue.value = await apiRequest<ScanQueueItem[]>("/api/admin/scans/queue")
  } catch (error) {
    showError(error, "Unable to load scan data")
  } finally {
    loading.value = false
  }
}

async function refreshActivity() {
  if (activityRefreshing || document.hidden) return
  activityRefreshing = true
  try {
    const previousIds = new Set(activeScans.value.map((scan) => scan.id))
    if (canViewActive.value) activeScans.value = await apiRequest<ActiveScan[]>("/api/admin/scans/active")
    if (auth.can("scans.view")) {
      queue.value = await apiRequest<ScanQueueItem[]>("/api/admin/scans/queue")
      if ([...previousIds].some((id) => !activeScans.value.some((scan) => scan.id === id))) {
        const historiesBySource = await Promise.all(sources.value.map(async (source) => [source.id, await apiRequest<ScanRun[]>(`/api/admin/library-sources/${source.id}/scans`)] as const))
        histories.value = Object.fromEntries(historiesBySource)
      }
    }
  } catch {
    // Background refresh failures should not interrupt scan management.
  } finally {
    activityRefreshing = false
  }
}

async function controlScan(scan: ActiveScan, action: "pause" | "resume" | "cancel") {
  if (!auth.can("scans.control") || controllingScanId.value !== null) return
  controllingScanId.value = scan.id
  errorMessage.value = ""
  try {
    await apiRequest(`/api/admin/scans/${scan.id}/${action}`, { method: "POST" })
    await loadScanData()
  } catch (error) {
    showError(error, `Unable to ${action} scan`)
  } finally {
    controllingScanId.value = null
  }
}

function controlLabel(action: "pause" | "resume" | "cancel", scanId: number) {
  if (controllingScanId.value !== scanId) return action[0].toUpperCase() + action.slice(1)
  return `${action[0].toUpperCase()}${action.slice(1)}ing…`
}

async function startScan(source: ScanSource) {
  if (!auth.can("scans.start") || startingSourceId.value !== null) return
  startingSourceId.value = source.id
  errorMessage.value = ""
  notice.value = ""
  try {
    await apiRequest(`/api/admin/library-sources/${source.id}/scan`, {
      method: "POST",
      body: JSON.stringify({ mode: "smart" }),
    })
    notice.value = `Smart scan started for ${source.name}.`
    if (auth.can("scans.view")) await loadScanData()
  } catch (error) {
    showError(error, "Unable to start scan")
  } finally {
    startingSourceId.value = null
  }
}

onMounted(() => {
  void loadScanData()
  activityTimer = window.setInterval(() => void refreshActivity(), 5000)
})

onBeforeUnmount(() => {
  if (activityTimer !== undefined) window.clearInterval(activityTimer)
})
</script>

<template>
  <main class="admin-shell scans-shell">
    <AdminHeader title="Scans" />
    <section class="admin-panel scans-panel">
      <div class="panel-heading">
        <p>Start smart scans and review activity for the library sources you can access.</p>
        <p class="panel-note">Only sources included in your current access scope are shown.</p>
      </div>
      <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
      <p v-if="notice" class="form-success" role="status">{{ notice }}</p>
      <p v-if="loading">Loading scan sources…</p>
      <p v-else-if="!sources.length" class="empty-state">No library sources are available for your access scope.</p>
      <section v-if="!loading && canViewActive" class="panel active-scans-panel">
        <div class="scan-section-heading"><h2>Active scans</h2><p v-if="!activeScans.length">No scans are currently active.</p></div>
        <div v-if="activeScans.length" class="scan-rows">
          <div v-for="scan in activeScans" :key="scan.id" class="active-scan-row">
            <div><strong>{{ scan.source_name }}</strong><p v-if="scan.current_model_name">{{ scan.current_model_name }}</p></div>
            <span class="scan-status" :class="statusClass(scan.status)">{{ statusLabel(scan.status) }}</span>
            <span v-if="scan.position">Queue position {{ scan.position }}</span>
            <div v-if="auth.can('scans.control')" class="scan-controls">
              <button v-if="scan.status === 'running'" class="secondary-button compact-button" type="button" :disabled="controllingScanId !== null" @click="controlScan(scan, 'pause')">{{ controlLabel('pause', scan.id) }}</button>
              <button v-if="scan.status === 'paused'" class="secondary-button compact-button" type="button" :disabled="controllingScanId !== null" @click="controlScan(scan, 'resume')">{{ controlLabel('resume', scan.id) }}</button>
              <button class="danger-button compact-button" type="button" :disabled="controllingScanId !== null" @click="controlScan(scan, 'cancel')">{{ controlLabel('cancel', scan.id) }}</button>
            </div>
          </div>
        </div>
      </section>
      <section v-if="!loading && sources.length && auth.can('scans.view')" class="panel scan-queue-panel">
        <div class="scan-section-heading"><h2>Queue</h2><p v-if="!queue.length">No scans are currently queued.</p></div>
        <div v-if="queue.length" class="scan-rows">
          <div v-for="item in queue" :key="item.id" class="scan-row"><strong>{{ item.source_name }}</strong><span class="scan-status" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span><span>{{ modeLabel(item.mode) }}</span></div>
        </div>
      </section>
      <div v-if="!loading && sources.length" class="scan-source-list">
        <article v-for="source in sources" :key="source.id" class="panel scan-source-card">
          <div class="scan-source-heading">
            <h3>{{ source.name }}</h3>
            <p v-if="auth.can('scans.view')">{{ histories[source.id]?.length ?? 0 }} recent scans</p>
            <p v-else>Scan history is not available for your role.</p>
          </div>
          <button
            v-if="auth.can('scans.start')"
            class="primary-button"
            type="button"
            :disabled="startingSourceId !== null"
            @click="startScan(source)"
          >{{ startingSourceId === source.id ? "Starting…" : "Start smart scan" }}</button>
          <div v-if="auth.can('scans.view') && histories[source.id]?.length" class="scan-history">
            <div v-for="scan in visibleHistories[source.id]" :key="scan.id" class="scan-row"><span class="scan-status" :class="statusClass(scan.status)">{{ statusLabel(scan.status) }}</span><span>{{ modeLabel(scan.mode) }}</span><span>{{ scan.models_found }} models found</span><small v-if="scan.error_message">{{ scan.error_message }}</small></div>
            <button v-if="histories[source.id].length > 5" class="text-button" type="button" @click="toggleHistory(source.id)">{{ expandedHistories.has(source.id) ? "Show fewer scans" : `Show all ${histories[source.id].length} scans` }}</button>
          </div>
          <p v-else-if="auth.can('scans.view')">No scan history yet.</p>
        </article>
      </div>
    </section>
  </main>
</template>

<style scoped>
.scans-panel { display: grid; gap: 1.25rem; }
.panel-heading { display: block; }
.panel-heading h2 { margin: 0 0 .35rem; }
.panel-heading p { margin: 0 0 .35rem; }
.panel-note { color: var(--muted); font-size: .9rem; }
.scan-source-list { display: grid; grid-template-columns: minmax(0, 1fr); gap: 1rem; }
.scan-source-card, .scan-queue-panel { display: grid; gap: 1rem; margin: 0; }
.scan-source-card { grid-template-columns: minmax(0, 1fr) auto; align-items: start; }
.scan-source-heading { display: grid; gap: .3rem; }
.scan-source-card h3, .scan-source-card p { margin: 0; }
.scan-history { grid-column: 1 / -1; display: grid; gap: .45rem; padding-top: 1rem; border-top: 1px solid var(--line); }
.scan-rows { display: grid; gap: .45rem; }
.scan-row { display: grid; grid-template-columns: minmax(8.5rem, auto) minmax(8rem, 1fr) minmax(8rem, 1fr); gap: .45rem .75rem; align-items: center; padding: .55rem .65rem; border-radius: .45rem; background: color-mix(in srgb, var(--panel) 80%, var(--line)); font-size: .9rem; }
.scan-row small { grid-column: 1 / -1; color: var(--danger); }
.scan-status { display: inline-flex; width: fit-content; padding: .15rem .45rem; border-radius: 999px; font-size: .8rem; font-weight: 600; }.scan-status.completed { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); }.scan-status.issues { color: #a56200; background: #fff0c9; }.scan-status.active { color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }.scan-status.failed { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.scan-section-heading { display: grid; gap: .25rem; }
.scan-section-heading h2, .scan-section-heading p { margin: 0; }
.active-scans-panel { display: grid; gap: .85rem; }.active-scan-row { display: grid; grid-template-columns: minmax(10rem, 1fr) auto auto auto; gap: .75rem; align-items: center; padding: .65rem; border-radius: .45rem; background: color-mix(in srgb, var(--panel) 80%, var(--line)); }.active-scan-row p { margin: .2rem 0 0; color: var(--muted); font-size: .85rem; }.scan-controls { display: flex; flex-wrap: wrap; gap: .45rem; }
@media (max-width: 640px) { .scan-source-card, .active-scan-row { grid-template-columns: 1fr; }.scan-row { grid-template-columns: 1fr; gap: .3rem; } }
</style>
