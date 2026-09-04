<script setup lang="ts">
import { computed, onMounted, ref } from "vue"

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

const auth = useAuthStore()
const sources = ref<ScanSource[]>([])
const histories = ref<Record<number, ScanRun[]>>({})
const queue = ref<ScanQueueItem[]>([])
const loading = ref(true)
const startingSourceId = ref<number | null>(null)
const errorMessage = ref("")
const notice = ref("")
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

onMounted(() => void loadScanData())
</script>

<template>
  <main class="admin-shell scans-shell">
    <AdminHeader title="Scans" />
    <section class="admin-panel scans-panel">
      <div class="panel-heading">
        <p class="eyebrow">Library operations</p>
        <h2>Source scans</h2>
        <p>Start smart scans and review activity for the library sources you can access.</p>
        <p class="panel-note">Only sources included in your current access scope are shown.</p>
      </div>
      <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
      <p v-if="notice" class="form-success" role="status">{{ notice }}</p>
      <p v-if="loading">Loading scan sources…</p>
      <p v-else-if="!sources.length" class="empty-state">No library sources are available for your access scope.</p>
      <section v-if="!loading && sources.length && auth.can('scans.view')" class="scan-queue-panel">
        <div class="scan-section-heading"><h2>Queue</h2><p v-if="!queue.length">No scans are currently queued.</p></div>
        <div v-if="queue.length" class="scan-rows">
          <div v-for="item in queue" :key="item.id" class="scan-row"><strong>{{ item.source_name }}</strong><span class="scan-status" :class="statusClass(item.status)">{{ statusLabel(item.status) }}</span><span>{{ modeLabel(item.mode) }}</span></div>
        </div>
      </section>
      <div v-if="!loading && sources.length" class="scan-source-list">
        <article v-for="source in sources" :key="source.id" class="scan-source-card">
          <div>
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
.panel-heading p { margin-bottom: .35rem; }.panel-note { color: var(--muted); font-size: .9rem; }
.scan-source-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; }
.scan-source-card, .scan-queue-panel { display: grid; gap: .85rem; padding: 1rem; border: 1px solid var(--line); border-radius: .75rem; background: var(--panel); }
.scan-source-card { grid-template-columns: minmax(0, 1fr) auto; align-items: start; }
.scan-source-card h3, .scan-source-card p { margin: 0; }
.scan-history { grid-column: 1 / -1; display: grid; gap: .45rem; }.scan-rows { display: grid; gap: .45rem; }
.scan-row { display: flex; flex-wrap: wrap; gap: .45rem .75rem; align-items: center; padding: .5rem .65rem; border-radius: .45rem; background: color-mix(in srgb, var(--panel) 80%, var(--line)); font-size: .9rem; }.scan-row small { flex-basis: 100%; color: var(--danger); }
.scan-status { display: inline-flex; width: fit-content; padding: .15rem .45rem; border-radius: 999px; font-size: .8rem; font-weight: 600; }.scan-status.completed { color: var(--success); background: color-mix(in srgb, var(--success) 14%, transparent); }.scan-status.issues { color: #a56200; background: #fff0c9; }.scan-status.active { color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent); }.scan-status.failed { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.scan-section-heading h2, .scan-section-heading p { margin: 0; }
@media (max-width: 640px) { .scan-source-card { grid-template-columns: 1fr; } }
</style>
