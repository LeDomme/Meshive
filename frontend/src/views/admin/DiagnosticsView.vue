<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface StorageStatus { path: string; readable: boolean; writable: boolean; total_bytes?: number; free_bytes?: number; error?: string }
interface Diagnostics { application: { version: string; environment: string }; database: { backend: string; reachable: boolean; size_bytes?: number; error?: string }; storage: Record<string, StorageStatus>; archive_backend: { command: string; available: boolean }; scanner: { max_concurrent_scans: number; running: number; pending: number }; scheduler: { thread_alive: boolean; last_check_at: string | null; last_success_at: string | null; last_error_at: string | null; last_error: string | null }; catalogue: Record<string, number | null> }

const diagnostics = ref<Diagnostics | null>(null)
const errorMessage = ref("")

async function load() {
  errorMessage.value = ""
  try {
    diagnostics.value = await apiRequest<Diagnostics>("/api/admin/diagnostics")
  } catch {
    errorMessage.value = "Diagnostics could not be loaded."
  }
}

onMounted(load)

function bytes(value?: number) {
  if (value == null) return "Unavailable"
  if (value < 1024) return `${value} B`
  const units = ["KB", "MB", "GB", "TB", "PB"]
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)) - 1, units.length - 1)
  return `${(value / 1024 ** (index + 1)).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[index]}`
}

function storageAccess(storage: StorageStatus) {
  if (storage.readable && storage.writable) return "Readable and writable"
  if (storage.readable) return "Readable, read-only"
  return "Unavailable"
}

function date(value: string | null) { return value ? new Date(value).toLocaleString() : "Not recorded" }

function label(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()) }
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Diagnostics" />
    <p class="admin-intro">Review application, storage and scheduler health.</p>
    <section class="admin-content panel diagnostics-panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">System status</p>
          <h2>Diagnostics</h2>
          <p class="panel-copy">Lightweight status checks only; no library or cache traversal is performed.</p>
        </div>
        <button class="secondary-button" type="button" @click="load">Refresh</button>
      </div>
      <p v-if="errorMessage" class="error-message">{{ errorMessage }}</p>
      <div v-else-if="diagnostics" class="diagnostics-grid">
        <section class="diagnostics-card"><h3>Application</h3><dl><dt>Version</dt><dd>{{ diagnostics.application.version }}</dd><dt>Environment</dt><dd>{{ diagnostics.application.environment }}</dd></dl></section>
        <section class="diagnostics-card"><h3>Database</h3><dl><dt>Backend</dt><dd>{{ diagnostics.database.backend }}</dd><dt>Status</dt><dd>{{ diagnostics.database.reachable ? "Reachable" : "Unavailable" }}</dd><dt>Size</dt><dd>{{ bytes(diagnostics.database.size_bytes) }}</dd></dl><p v-if="diagnostics.database.error" class="error-message">{{ diagnostics.database.error }}</p></section>
        <section v-for="(storage, name) in diagnostics.storage" :key="name" class="diagnostics-card"><h3>{{ label(name) }} storage</h3><dl><dt>Path</dt><dd>{{ storage.path }}</dd><dt>Access</dt><dd>{{ storageAccess(storage) }}</dd><dt>Capacity</dt><dd>{{ bytes(storage.total_bytes) }}</dd><dt>Free space</dt><dd>{{ bytes(storage.free_bytes) }}</dd></dl><p v-if="storage.error" class="error-message">{{ storage.error }}</p></section>
        <section class="diagnostics-card"><h3>Archive backend</h3><dl><dt>Command</dt><dd>{{ diagnostics.archive_backend.command }}</dd><dt>Status</dt><dd>{{ diagnostics.archive_backend.available ? "Available" : "Unavailable" }}</dd></dl></section>
        <section class="diagnostics-card"><h3>Scanner</h3><dl><dt>Maximum concurrent scans</dt><dd>{{ diagnostics.scanner.max_concurrent_scans }}</dd><dt>Running</dt><dd>{{ diagnostics.scanner.running }}</dd><dt>Pending</dt><dd>{{ diagnostics.scanner.pending }}</dd></dl></section>
        <section class="diagnostics-card"><h3>Scheduler</h3><dl><dt>Status</dt><dd>{{ diagnostics.scheduler.thread_alive ? "Running" : "Stopped" }}</dd><dt>Last check</dt><dd>{{ date(diagnostics.scheduler.last_check_at) }}</dd><dt>Last success</dt><dd>{{ date(diagnostics.scheduler.last_success_at) }}</dd><dt>Last error</dt><dd>{{ diagnostics.scheduler.last_error ?? "None" }}</dd></dl></section>
        <section class="diagnostics-card"><h3>Catalogue</h3><dl><template v-for="(value, name) in diagnostics.catalogue" :key="name"><dt>{{ label(name) }}</dt><dd>{{ value ?? "Unavailable" }}</dd></template></dl></section>
      </div>
      <p v-else class="muted">Loading diagnostics…</p>
    </section>
  </main>
</template>
