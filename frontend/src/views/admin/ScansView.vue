<script setup lang="ts">
import { onMounted, ref } from "vue"

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
      </div>
      <p v-if="errorMessage" class="form-error" role="alert">{{ errorMessage }}</p>
      <p v-if="notice" class="form-success" role="status">{{ notice }}</p>
      <p v-if="loading">Loading scan sources…</p>
      <p v-else-if="!sources.length" class="empty-state">No library sources are available for your access scope.</p>
      <div v-else class="scan-source-list">
        <article v-for="source in sources" :key="source.id" class="scan-source-card">
          <div>
            <h3>{{ source.name }}</h3>
            <p v-if="auth.can('scans.view')">{{ histories[source.id]?.length ?? 0 }} recent scans</p>
          </div>
          <button
            v-if="auth.can('scans.start')"
            class="primary-button"
            type="button"
            :disabled="startingSourceId !== null"
            @click="startScan(source)"
          >{{ startingSourceId === source.id ? "Starting…" : "Start scan" }}</button>
          <ul v-if="auth.can('scans.view') && histories[source.id]?.length" class="scan-history">
            <li v-for="scan in histories[source.id]" :key="scan.id">
              <strong>{{ scan.status }}</strong> · {{ scan.mode }} · {{ scan.models_found }} models found
              <span v-if="scan.error_message"> · {{ scan.error_message }}</span>
            </li>
          </ul>
          <p v-else-if="auth.can('scans.view')">No scan history yet.</p>
        </article>
      </div>
      <section v-if="auth.can('scans.view') && queue.length" class="scan-queue">
        <h2>Queue</h2>
        <ul>
          <li v-for="item in queue" :key="item.id">{{ item.source_name }} · {{ item.status }} · {{ item.mode }}</li>
        </ul>
      </section>
    </section>
  </main>
</template>

<style scoped>
.scans-panel { display: grid; gap: 1.25rem; }
.panel-heading p { margin-bottom: 0; }
.scan-source-list { display: grid; gap: 1rem; }
.scan-source-card { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: .75rem 1rem; align-items: start; padding: 1rem; border: 1px solid var(--line); border-radius: .75rem; }
.scan-source-card h3, .scan-source-card p { margin: 0; }
.scan-history { grid-column: 1 / -1; margin: 0; padding-left: 1.25rem; }
.scan-queue { border-top: 1px solid var(--line); padding-top: 1rem; }
@media (max-width: 640px) { .scan-source-card { grid-template-columns: 1fr; } }
</style>
