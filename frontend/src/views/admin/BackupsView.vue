<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface Schedule {
  id: number; enabled: boolean; frequency: "daily" | "weekly"; time_of_day: string
  weekday: number; timezone: string; destination: string
  retention_days: number; retention_count: number
}
interface Run {
  id: number; status: string; trigger: string; path: string | null
  size_bytes: number | null; started_at: string; finished_at: string | null
  error_message: string | null
}

const schedule = reactive<Schedule>({
  id: 1, enabled: false, frequency: "daily", time_of_day: "03:00",
  weekday: 0, timezone: "Europe/Berlin", destination: "automatic",
  retention_days: 30, retention_count: 14,
})
const runs = ref<Run[]>([])
const errorMessage = ref("")
const scheduleMessage = ref("")
const saving = ref(false)
const running = ref(false)
const restoring = ref(false)
const restoreResult = ref<{ status: string | null; error?: string; backup?: string }>({ status: null })
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

async function load() {
  const [saved, history, restored] = await Promise.all([
    apiRequest<Schedule>("/api/admin/backups/schedule"),
    apiRequest<Run[]>("/api/admin/backups"),
    apiRequest<{ status: string | null; error?: string; backup?: string }>("/api/admin/backups/restore-result"),
  ])
  Object.assign(schedule, saved)
  runs.value = history
  restoreResult.value = restored
}
async function save() {
  saving.value = true
  scheduleMessage.value = ""
  errorMessage.value = ""
  try {
    Object.assign(schedule, await apiRequest<Schedule>("/api/admin/backups/schedule", {
      method: "PUT", body: JSON.stringify(schedule),
    }))
    scheduleMessage.value = "Backup schedule saved successfully."
  } catch (error) { showError(error) }
  finally { saving.value = false }
}
async function runNow() {
  running.value = true
  scheduleMessage.value = ""
  errorMessage.value = ""
  try {
    await apiRequest<Run>("/api/admin/backups/run", { method: "POST" })
    await load()
    scheduleMessage.value = "Manual backup created successfully."
  } catch (error) { showError(error) }
  finally { running.value = false }
}
async function remove(run: Run) {
  if (!confirm(`Delete backup #${run.id} and its history record?`)) return
  errorMessage.value = ""
  try {
    await apiRequest(`/api/admin/backups/${run.id}`, { method: "DELETE" })
    await load()
    scheduleMessage.value = "Backup deleted."
  } catch (error) { showError(error) }
}
async function dismissRestoreResult() {
  try {
    await apiRequest("/api/admin/backups/restore-result", { method: "DELETE" })
    restoreResult.value = { status: null }
  } catch (error) {
    showError(error)
  }
}
async function restore(run: Run) {
  const confirmation = prompt(
    "This replaces the current Meshive database and restarts the container. Type RESTORE to continue.",
  )
  if (confirmation !== "RESTORE") return
  restoring.value = true
  errorMessage.value = ""
  try {
    await apiRequest(`/api/admin/backups/restore/${run.id}`, {
      method: "POST",
      body: JSON.stringify({ confirmation }),
    })
    await waitForRestart()
  } catch (error) {
    restoring.value = false
    showError(error)
  }
}
async function waitForRestart() {
  await new Promise((resolve) => setTimeout(resolve, 5000))
  for (let attempt = 0; attempt < 60; attempt += 1) {
    try {
      const response = await fetch("/api/health", { cache: "no-store" })
      if (response.ok) {
        window.location.reload()
        return
      }
    } catch {
      // The application is expected to be unavailable during the restart.
    }
    await new Promise((resolve) => setTimeout(resolve, 2000))
  }
  restoring.value = false
  errorMessage.value = "Meshive did not return in time. Check the container logs."
}
function showError(error: unknown) {
  errorMessage.value = error instanceof ApiError ? error.message : "Backup operation failed"
}
function bytes(value: number | null) {
  if (value === null) return "—"
  return `${(value / 1024 / 1024).toFixed(1)} MB`
}
onMounted(load)
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Backups" />
    <p class="admin-intro">
      Backups are written below <code>/backups</code>. Mount this path to independent storage.
    </p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
    <p v-if="scheduleMessage" class="success-panel" role="status">{{ scheduleMessage }}</p>
    <section
      v-if="restoring || restoreResult.status"
      :class="['restore-status-card', restoreResult.status || 'running']"
    >
      <button
        v-if="!restoring"
        class="restore-status-dismiss"
        type="button"
        aria-label="Dismiss restore status"
        @click="dismissRestoreResult"
      >×</button>
      <p class="eyebrow">Restore status</p>
      <h2 v-if="restoring">Restore in progress</h2>
      <h2 v-else-if="restoreResult.status === 'completed'">Restore completed</h2>
      <h2 v-else>Restore failed</h2>
      <p v-if="restoring">
        Restoring the database and restarting Meshive. This page will reconnect automatically...
      </p>
      <p v-else-if="restoreResult.status === 'completed'">
        The database was restored successfully from
        <code>{{ restoreResult.backup }}</code>.
      </p>
      <p v-else class="form-error">{{ restoreResult.error }}</p>
    </section>
    <section class="admin-grid">
      <form class="panel source-form" @submit.prevent="save">
        <h2>Automatic schedule</h2>
        <label class="inline-check"><input v-model="schedule.enabled" type="checkbox"> Enable automatic backups</label>
        <label><span>Frequency</span><select v-model="schedule.frequency"><option value="daily">Daily</option><option value="weekly">Weekly</option></select></label>
        <label v-if="schedule.frequency === 'weekly'"><span>Weekday</span><select v-model="schedule.weekday"><option v-for="(day, index) in weekdays" :key="day" :value="index">{{ day }}</option></select></label>
        <label><span>Time</span><input v-model="schedule.time_of_day" type="time" required></label>
        <label><span>Timezone</span><input v-model="schedule.timezone" required></label>
        <label><span>Keep for days</span><input v-model.number="schedule.retention_days" type="number" min="1" max="3650"></label>
        <label><span>Maximum automatic backups</span><input v-model.number="schedule.retention_count" type="number" min="1" max="1000"></label>
        <button class="primary-button" type="submit" :disabled="saving">
          {{ saving ? "Saving..." : "Save schedule" }}
        </button>
      </form>
      <section class="panel">
        <h2>Manual backup</h2>
        <p class="panel-copy">Creates a backup immediately in the <code>manual</code> folder. Manual backups are not removed by automatic retention.</p>
        <button class="primary-button" type="button" :disabled="running" @click="runNow">
          {{ running ? "Creating backup…" : "Backup now" }}
        </button>
      </section>
    </section>
    <section class="panel backup-history">
      <h2>Backup history</h2>
      <div class="user-table-wrap">
        <table class="user-table">
          <thead><tr><th>Started</th><th>Trigger</th><th>Status</th><th>Size</th><th>Path / error</th><th></th></tr></thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id">
              <td>{{ new Date(run.started_at).toLocaleString() }}</td>
              <td>{{ run.trigger }}</td><td>{{ run.status }}</td><td>{{ bytes(run.size_bytes) }}</td>
              <td class="path-value" :title="run.error_message || run.path || undefined">{{ run.error_message || run.path || "—" }}</td>
              <td class="backup-actions">
                <button
                  v-if="run.status === 'completed' && run.path"
                  class="secondary-button"
                  type="button"
                  :disabled="restoring"
                  @click="restore(run)"
                >Restore</button>
                <button class="danger-button" type="button" :disabled="restoring" @click="remove(run)">Delete</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </main>
</template>
