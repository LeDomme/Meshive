<script setup lang="ts">
import { onBeforeUnmount, onMounted, reactive, ref } from "vue"
import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"
import { useAuthStore } from "../../stores/auth"

interface LibrarySource {
  id: number
  name: string
  root_path: string
  directory_pattern: string
  model_pattern: string | null
  archive_formats: string[]
  image_formats: string[]
  is_active: boolean
  scan_enabled: boolean
  auto_scan_enabled: boolean
  auto_scan_frequency: "hourly" | "daily" | "weekly"
  auto_scan_time: string
  auto_scan_weekday: number
  auto_scan_timezone: string
}

interface PreviewResponse {
  normalized_path: string
  values: Record<string, string>
  warnings: string[]
}

type ScanMode = "full" | "incremental" | "missing_images" | "reconcile_images" | "smart"

interface ScanRun {
  id: number
  library_source_id: number
  status: string
  mode: ScanMode
  trigger: string
  created_at: string
  models_found: number
  models_added: number
  models_updated: number
  models_missing: number
  models_skipped: number
  archive_images_reused: number
  archive_images_generated: number
  archive_images_removed: number
  automatic_tag_matches: number
  automatic_tags_added: number
  automatic_tags_removed: number
  issues_count: number
  error_message: string | null
  issues?: ScanIssue[]
}

interface ScanIssue {
  id: number
  relative_path: string
  severity: string
  code: string
  message: string
}

interface ScanQueueItem {
  id: number
  library_source_id: number
  source_name: string
  status: "pending" | "running"
  mode: ScanMode
  trigger: string
  target_model_id: number | null
  target_model_name: string | null
  position: number | null
  created_at: string
  started_at: string | null
  cancel_requested: boolean
  pause_requested: boolean
  current_model_name: string | null
  current_phase: string | null
  models_total: number
  models_found: number
  models_skipped: number
}

const sources = ref<LibrarySource[]>([])
const auth = useAuthStore()
const latestScans = ref<Record<number, ScanRun>>({})
const scanQueue = ref<ScanQueueItem[]>([])
const scanModesBySource = ref<Record<number, ScanMode>>({})
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref("")
const preview = ref<PreviewResponse | null>(null)
const editingId = ref<number | null>(null)
const activityClock = ref(Date.now())
let queueTimer: number | undefined
let activityClockTimer: number | undefined

const form = reactive({
  name: "",
  root_path: "/models/",
  directory_pattern: "{franchise}/{model_folder}",
  model_pattern: "{franchise} - {model} - by {creator}",
  relative_path: "",
  is_active: true,
  scan_enabled: true,
  auto_scan_enabled: false,
  auto_scan_frequency: "daily" as "hourly" | "daily" | "weekly",
  auto_scan_time: "02:00",
  auto_scan_weekday: 0,
  auto_scan_timezone: "Europe/Berlin",
})
const weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
const scanModes: Array<{ value: ScanMode; label: string; description: string }> = [
  { value: "smart", label: "Smart scan", description: "Scan new or changed models and skip unchanged healthy models. The first scan after upgrading may inspect models to establish its baseline." },
  { value: "incremental", label: "Incremental scan", description: "Index new models without reprocessing existing ones." },
  { value: "full", label: "Full scan", description: "Check all models and repair missing or stale archive images." },
  { value: "missing_images", label: "Full scan — repair missing images", description: "Check all models but only export missing or stale image variants." },
  { value: "reconcile_images", label: "Reconcile images", description: "Repair missing or stale archive images from the existing catalogue." },
]

async function loadSources() {
  loading.value = true
  errorMessage.value = ""
  try {
    sources.value = await apiRequest<LibrarySource[]>("/api/admin/library-sources")
    for (const source of sources.value) {
      scanModesBySource.value[source.id] ??= "smart"
    }
    if (auth.can("scans.view")) await Promise.all([loadQueue(), ...sources.value.map(loadLatestScan)])
  } catch (error) {
    showError(error)
  } finally {
    loading.value = false
  }
}

async function loadQueue() {
  scanQueue.value = await apiRequest<ScanQueueItem[]>("/api/admin/scans/queue")
}

async function loadLatestScan(source: LibrarySource) {
  const scans = await apiRequest<ScanRun[]>(
    `/api/admin/library-sources/${source.id}/scans`,
  )
  if (scans[0]) {
    latestScans.value[source.id] = await apiRequest<ScanRun>(
      `/api/admin/scans/${scans[0].id}`,
    )
  }
}

async function startScan(source: LibrarySource, mode = scanModesBySource.value[source.id] ?? 'smart') {
  errorMessage.value = ""
  try {
    const scan = await apiRequest<ScanRun>(
      `/api/admin/library-sources/${source.id}/scan`,
      { method: "POST", body: JSON.stringify({ mode }) },
    )
    latestScans.value[source.id] = scan
    window.setTimeout(() => pollScan(source.id, scan.id), 1000)
  } catch (error) {
    showError(error)
  }
}

async function toggleScanPause(item: ScanQueueItem) {
  errorMessage.value = ""
  try {
    await apiRequest<ScanRun>(`/api/admin/scans/${item.id}/${item.pause_requested ? "resume" : "pause"}`, {
      method: "POST",
    })
    await loadQueue()
  } catch (error) {
    showError(error)
  }
}
async function cancelScan(item: ScanQueueItem) {
  errorMessage.value = ""
  try {
    await apiRequest<ScanRun>(`/api/admin/scans/${item.id}/cancel`, { method: "POST" })
    await loadQueue()
  } catch (error) {
    showError(error)
  }
}
async function pollScan(sourceId: number, scanId: number) {
  try {
    const scan = await apiRequest<ScanRun>(`/api/admin/scans/${scanId}`)
    latestScans.value[sourceId] = scan
    await loadQueue()
    if (scan.status === "pending" || scan.status === "running") {
      window.setTimeout(() => pollScan(sourceId, scanId), 1500)
    }
  } catch (error) {
    showError(error)
  }
}

function scanIsActive(sourceId: number) {
  const status = latestScans.value[sourceId]?.status
  return status === "pending" || status === "running"
}

function scanActivityLabel(item: ScanQueueItem) {
  if (item.status === "running" && item.current_phase === "discovering") {
    return "Discovering model directories"
  }
  if (item.status === "running" && item.current_phase === "reconciling_images") {
    return "Reconciling archive images"
  }
  if (item.status === "running" && item.current_phase === "finalizing") {
    return "Finalizing scan"
  }
  if (item.status === "running" && item.current_phase === "targeted_rescan") {
    return item.trigger === "model_image_rebuild"
      ? "Rebuilding archive images"
      : "Rescanning model"
  }
  if (item.target_model_name) {
    return item.trigger === "model_image_rebuild"
      ? "Rebuilding archive images"
      : "Rescanning model"
  }
  return scanModeLabel(item.mode)
}

function scanProgressLabel(item: ScanQueueItem) {
  if (item.status !== "running" || !item.models_total) return ""
  const processed = Math.min(item.models_total, item.models_found + item.models_skipped)
  const current = item.current_phase === "finalizing" ? "" : item.current_model_name ? ` · ${item.current_model_name}` : ""
  const prefix = item.current_phase === "reconciling_images" ? " · " : " · "
  return `${prefix}${processed} / ${item.models_total}${current}`
}
function elapsedScanTime(startedAt: string | null) {
  if (!startedAt) return "Waiting"
  // SQLite currently stores UTC timestamps without an offset. Treat a naive
  // timestamp as UTC rather than letting the browser interpret it as local time.
  const timestamp = /(?:Z|[+-]\d{2}:\d{2})$/i.test(startedAt)
    ? startedAt
    : `${startedAt}Z`
  const seconds = Math.max(
    0,
    Math.floor((activityClock.value - new Date(timestamp).getTime()) / 1000),
  )
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  return minutes
    ? `${minutes}m ${String(remainingSeconds).padStart(2, "0")}s`
    : `${remainingSeconds}s`
}
function scanModeLabel(mode: ScanMode) {
  return scanModes.find((item) => item.value === mode)?.label ?? mode
}

function scanButtonLabel(sourceId: number) {
  const status = latestScans.value[sourceId]?.status
  if (status === "pending") return "Queued"
  if (status === "running") return "Scanning…"
  return "Scan now"
}

function payload() {
  return {
    name: form.name,
    root_path: form.root_path,
    directory_pattern: form.directory_pattern,
    model_pattern: form.model_pattern || null,
    archive_formats: ["7z", "zip", "rar"],
    image_formats: ["jpg", "jpeg", "png", "webp"],
    is_active: form.is_active,
    scan_enabled: form.scan_enabled,
    auto_scan_enabled: form.auto_scan_enabled,
    auto_scan_frequency: form.auto_scan_frequency,
    auto_scan_time: form.auto_scan_time,
    auto_scan_weekday: form.auto_scan_weekday,
    auto_scan_timezone: form.auto_scan_timezone,
  }
}

async function saveSource() {
  saving.value = true
  errorMessage.value = ""
  try {
    const path = editingId.value
      ? `/api/admin/library-sources/${editingId.value}`
      : "/api/admin/library-sources"
    await apiRequest<LibrarySource>(path, {
      method: editingId.value ? "PUT" : "POST",
      body: JSON.stringify(payload()),
    })
    resetForm()
    await loadSources()
  } catch (error) {
    showError(error)
  } finally {
    saving.value = false
  }
}

async function previewPath() {
  preview.value = null
  errorMessage.value = ""
  if (!form.relative_path.trim()) {
    errorMessage.value = "Enter an example path relative to the container path"
    return
  }
  try {
    preview.value = await apiRequest<PreviewResponse>(
      "/api/admin/library-sources/preview",
      {
        method: "POST",
        body: JSON.stringify({
          directory_pattern: form.directory_pattern,
          model_pattern: form.model_pattern || null,
          relative_path: form.relative_path,
        }),
      },
    )
  } catch (error) {
    showError(error)
  }
}

function editSource(source: LibrarySource) {
  editingId.value = source.id
  form.name = source.name
  form.root_path = source.root_path
  form.directory_pattern = source.directory_pattern
  form.model_pattern = source.model_pattern ?? ""
  form.is_active = source.is_active
  form.scan_enabled = source.scan_enabled
  form.auto_scan_enabled = source.auto_scan_enabled
  form.auto_scan_frequency = source.auto_scan_frequency
  form.auto_scan_time = source.auto_scan_time
  form.auto_scan_weekday = source.auto_scan_weekday
  form.auto_scan_timezone = source.auto_scan_timezone
  preview.value = null
  window.scrollTo({ top: 0, behavior: "smooth" })
}

async function removeSource(source: LibrarySource) {
  if (!window.confirm(`Delete the source “${source.name}”?`)) return
  try {
    await apiRequest<void>(`/api/admin/library-sources/${source.id}`, {
      method: "DELETE",
    })
    if (editingId.value === source.id) resetForm()
    await loadSources()
  } catch (error) {
    showError(error)
  }
}

function resetForm() {
  editingId.value = null
  form.name = ""
  form.root_path = "/models/"
  form.directory_pattern = "{franchise}/{model_folder}"
  form.model_pattern = "{franchise} - {model} - by {creator}"
  form.relative_path = ""
  form.is_active = true
  form.scan_enabled = true
  form.auto_scan_enabled = false
  form.auto_scan_frequency = "daily"
  form.auto_scan_time = "02:00"
  form.auto_scan_weekday = 0
  form.auto_scan_timezone = "Europe/Berlin"
  preview.value = null
}

function showError(error: unknown) {
  errorMessage.value =
    error instanceof ApiError ? error.message : "The request could not be completed"
}

onMounted(async () => {
  await loadSources()
  activityClockTimer = window.setInterval(() => { activityClock.value = Date.now() }, 1000)
  queueTimer = window.setInterval(() => {
    void loadQueue().catch(() => undefined)
  }, 3000)
})
onBeforeUnmount(() => {
  if (queueTimer !== undefined) window.clearInterval(queueTimer)
  if (activityClockTimer !== undefined) window.clearInterval(activityClockTimer)
})
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Library sources" />

    <p class="admin-intro">
      Sources must already be mounted below <code>/models</code>. Meshive only
      stores their container paths and never changes source files.
    </p>

    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>

    <section class="admin-grid">
      <form class="panel source-form" @submit.prevent="saveSource">
        <div class="panel-heading">
          <h2>{{ editingId ? "Edit source" : "Add source" }}</h2>
          <button v-if="editingId" class="text-button" type="button" @click="resetForm">
            Cancel edit
          </button>
        </div>

        <label>
          <span>Name</span>
          <input v-model="form.name" required placeholder="Primary library">
        </label>

        <label>
          <span>Container path</span>
          <input v-model="form.root_path" required placeholder="/models/library-one">
        </label>

        <label>
          <span>Directory patterns</span>
          <textarea
            v-model="form.directory_pattern"
            required
            rows="3"
            placeholder="{creator_folder}/{franchise}/{model_folder}"
          />
          <small>Enter one layout per line. More specific layouts should come first.</small>
        </label>

        <label>
          <span>Model-name patterns</span>
          <textarea
            v-model="form.model_pattern"
            rows="3"
            placeholder="{franchise} - {model} - by {creator}"
          />
          <small>
            Enter one pattern per line. The first matching pattern is used.
            <code>{variant}</code> accepts free-form values; put variant patterns
            first and use a literal marker such as
            <code>{variant_identifier} {variant}</code> when layouts could overlap.
            The identifier accepts variant, version, edition, and revision
            without regard to capitalization.
          </small>
        </label>


        <div class="check-row">
          <label><input v-model="form.is_active" type="checkbox"> Active</label>
          <label><input v-model="form.scan_enabled" type="checkbox"> Scanning enabled</label>
        </div>

        <details class="schedule-fields">
          <summary>Automatic scanning</summary>
          <div class="detail-fields">
            <label class="inline-check">
              <input v-model="form.auto_scan_enabled" type="checkbox">
              Enable automatic scans
            </label>
            <label>
              <span>Frequency</span>
              <select v-model="form.auto_scan_frequency">
                <option value="hourly">Hourly</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </label>
            <label v-if="form.auto_scan_frequency === 'weekly'">
              <span>Weekday</span>
              <select v-model="form.auto_scan_weekday">
                <option v-for="(day, index) in weekdays" :key="day" :value="index">
                  {{ day }}
                </option>
              </select>
            </label>
            <label>
              <span>{{ form.auto_scan_frequency === "hourly" ? "Minute past the hour" : "Time" }}</span>
              <input v-model="form.auto_scan_time" type="time" required>
              <small v-if="form.auto_scan_frequency === 'hourly'">
                Only the minute value is used.
              </small>
            </label>
            <label>
              <span>Timezone</span>
              <input v-model="form.auto_scan_timezone" required>
            </label>
          </div>
        </details>

        <button class="primary-button" type="submit" :disabled="saving">
          {{ saving ? "Saving…" : editingId ? "Save changes" : "Add source" }}
        </button>
      </form>

      <section class="panel">
        <h2>Test pattern</h2>
        <p class="panel-copy">
          Enter a model-folder path relative to the container path. Do not include
          the container path itself or an archive filename. Both slash styles are
          accepted.
        </p>
        <label class="standalone-field">
          <span>Example relative path</span>
          <input
            v-model="form.relative_path"
            placeholder="Franchise/Model folder"
          >
        </label>
        <button
          class="secondary-button"
          type="button"
          :disabled="!form.relative_path.trim()"
          @click="previewPath"
        >
          Preview values
        </button>

        <div v-if="preview" class="preview-result">
          <p><strong>Normalized:</strong> {{ preview.normalized_path }}</p>
          <ul v-if="preview.warnings.length" class="preview-warnings" role="status">
            <li v-for="warning in preview.warnings" :key="warning">
              {{ warning }}
            </li>
          </ul>
          <dl>
            <template v-for="(value, key) in preview.values" :key="key">
              <dt>{{ key }}</dt>
              <dd>{{ value }}</dd>
            </template>
          </dl>
        </div>
      </section>
    </section>

    <section class="panel scan-queue-panel">
      <h2>Scan activity</h2>
      <p v-if="scanQueue.length === 0" class="muted">
        No scans are currently running or queued.
      </p>
      <div v-else class="scan-queue-list">
        <article v-for="item in scanQueue" :key="item.id" class="scan-queue-row">
          <div>
            <strong>{{ item.source_name }}</strong>
            <span class="muted">
              {{ scanActivityLabel(item) }}
              <template v-if="item.target_model_name">· {{ item.target_model_name }}</template>
              {{ scanProgressLabel(item) }}
              · {{ elapsedScanTime(item.started_at) }}
            </span>
          </div>
          <div class="scan-queue-actions">
          <span :class="['scan-state', item.status]">
            {{ item.cancel_requested ? "Cancelling" : item.pause_requested ? "Paused" : item.status === "running" ? "Running" : `Queue #${item.position}` }}
          </span>
          <button
            class="secondary-button compact-button"
            type="button"
            :disabled="item.cancel_requested"
            @click="toggleScanPause(item)"
          >
            {{ item.pause_requested ? "Resume" : "Pause" }}
          </button>
          <button
            class="secondary-button compact-button"
            type="button"
            :disabled="item.cancel_requested"
            @click="cancelScan(item)"
          >
            {{ item.cancel_requested ? "Cancelling…" : "Cancel" }}
          </button>
        </div>
        </article>
      </div>
    </section>

    <section class="panel source-list">
      <h2>Configured sources</h2>
      <p v-if="loading" class="muted">Loading sources…</p>
      <p v-else-if="sources.length === 0" class="muted">
        No library sources have been configured.
      </p>
      <article v-for="source in sources" :key="source.id" class="source-row">
        <div>
          <h3>{{ source.name }}</h3>
          <code>{{ source.root_path }}</code>
          <p>{{ source.directory_pattern }}</p>
          <p v-if="source.auto_scan_enabled" class="muted">
            Automatic scan: {{ source.auto_scan_frequency }}
            <template v-if="source.auto_scan_frequency === 'weekly'">
              on {{ weekdays[source.auto_scan_weekday] }}
            </template>
            at
            {{ source.auto_scan_frequency === "hourly"
              ? `minute ${source.auto_scan_time.split(":")[1]}`
              : source.auto_scan_time }}
            ({{ source.auto_scan_timezone }})
          </p>
          <p v-if="latestScans[source.id]" class="scan-summary">
            Scan: <strong>{{ latestScans[source.id].status }}</strong>
            · {{ scanModeLabel(latestScans[source.id].mode) }}
            · {{ latestScans[source.id].models_found }} models
            <template v-if="latestScans[source.id].models_skipped">
              · {{ latestScans[source.id].models_skipped }} skipped
            </template>
            · {{ latestScans[source.id].automatic_tag_matches }} automatic tag matches
            <template v-if="latestScans[source.id].archive_images_reused || latestScans[source.id].archive_images_generated || latestScans[source.id].archive_images_removed">
              · images: {{ latestScans[source.id].archive_images_reused }} reused
              · {{ latestScans[source.id].archive_images_generated }} generated
              <template v-if="latestScans[source.id].archive_images_removed">
                · {{ latestScans[source.id].archive_images_removed }} removed
              </template>
            </template>
            <template
              v-if="latestScans[source.id].automatic_tags_added
                || latestScans[source.id].automatic_tags_removed"
            >
              ({{ latestScans[source.id].automatic_tags_added }} added,
              {{ latestScans[source.id].automatic_tags_removed }} removed)
            </template>
            · {{ latestScans[source.id].issues_count }} issues
          </p>
          <p v-if="latestScans[source.id]?.error_message" class="form-error">
            {{ latestScans[source.id].error_message }}
          </p>
          <details
            v-if="latestScans[source.id]?.issues?.length"
            class="scan-issues"
          >
            <summary>Show scan issues</summary>
            <ul>
              <li
                v-for="issue in latestScans[source.id]?.issues ?? []"
                :key="issue.id"
              >
                <strong>{{ issue.code }}</strong> · {{ issue.relative_path }}<br>
                {{ issue.message }}
              </li>
            </ul>
          </details>
        </div>
        <div class="row-actions">
          <select
            class="scan-mode-control"
            aria-label="Scan mode"
            :disabled="scanIsActive(source.id) || !source.scan_enabled"
            v-model="scanModesBySource[source.id]"
          >
            <option v-for="mode in scanModes" :key="mode.value" :value="mode.value">
              {{ mode.label }}
            </option>
          </select>
          <button
            class="primary-button compact-button"
            type="button"
            :disabled="scanIsActive(source.id) || !source.scan_enabled"
            @click="startScan(source)"
          >
            {{ scanButtonLabel(source.id) }}
          </button>
          <button class="secondary-button" type="button" @click="editSource(source)">
            Edit
          </button>
          <button class="danger-button" type="button" @click="removeSource(source)">
            Delete
          </button>
        </div>
      </article>
    </section>
  </main>
</template>
