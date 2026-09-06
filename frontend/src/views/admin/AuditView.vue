<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface Event { id:number; created_at:string; actor_username:string; action:string; target_type:string; target_label:string }
const events = ref<Event[]>([]), page = ref(1), total = ref(0), action = ref(""), actor = ref(""), fromAt = ref(""), toAt = ref("")
const loading = ref(false), exporting = ref(false), errorMessage = ref("")
const labels: Record<string,string> = {
  "role.created":"Role created", "role.updated":"Role updated", "role.deleted":"Role deleted",
  "user.created":"User created", "user.updated":"User updated", "user.deleted":"User deleted", "user.role_changed":"User role changed", "user.source_access_changed":"User source access changed", "user.status_changed":"User status changed", "user.password_changed":"User password changed", "user.require_password_change_changed":"Password-change requirement changed",
  "source.created":"Source created", "source.updated":"Source updated", "source.deleted":"Source deleted",
  "scan.started":"Scan started", "scan.pause_requested":"Scan pause requested", "scan.resume_requested":"Scan resume requested", "scan.cancel_requested":"Scan cancel requested",
  "backup.started":"Backup started", "backup.completed":"Backup completed", "backup.failed":"Backup failed", "backup.restore_started":"Database restore started", "backup.restore_completed":"Database restore completed", "backup.restore_failed":"Database restore failed",
  "backup.deleted":"Backup deleted", "audit.exported":"Audit log exported",
  "metadata.created":"Metadata created", "metadata.updated":"Metadata updated", "metadata.deleted":"Metadata deleted",
  "tag.created":"Tag created", "tag.updated":"Tag updated", "tag.deleted":"Tag deleted",
  "folder_tag_rule.created":"Folder tag rule created", "folder_tag_rule.updated":"Folder tag rule updated", "folder_tag_rule.deleted":"Folder tag rule deleted",
  "automatic_tag_rule.created":"Automatic tag rule created", "automatic_tag_rule.updated":"Automatic tag rule updated", "automatic_tag_rule.deleted":"Automatic tag rule deleted",
  "tag_assignment_rule.created":"Tag assignment rule created", "tag_assignment_rule.updated":"Tag assignment rule updated", "tag_assignment_rule.deleted":"Tag assignment rule deleted", "tag_assignment_rule.re_evaluated":"Tag assignment rule re-evaluated",
  "model_tag.added":"Model tag added", "model_tag.removed":"Model tag removed",
  "model.primary_image_set":"Primary image set", "model.rescan_queued":"Model rescan queued", "model.image_rebuild_queued":"Archive images rebuild queued", "model.images_reset":"Model images reset", "model.missing_deleted":"Missing model deleted",
}
function iso(value:string) { return value ? new Date(value).toISOString() : "" }
function actionLabel(value:string) { return labels[value] ?? value.replaceAll(".", " ") }
async function load(reset=false) {
  if (loading.value) return
  if (reset) page.value = 1
  loading.value = true; errorMessage.value = ""
  try {
    const query = new URLSearchParams({ page:String(page.value), page_size:"25" })
    if (action.value) query.set("action", action.value)
    if (actor.value) query.set("actor", actor.value)
    if (fromAt.value) query.set("from_at", iso(fromAt.value))
    if (toAt.value) query.set("to_at", iso(toAt.value))
    const data = await apiRequest<{items:Event[]; total:number}>(`/api/admin/audit-events?${query}`)
    events.value = reset ? data.items : [...events.value, ...data.items]
    total.value = data.total
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : "Unable to load audit events" } finally { loading.value = false }
}
function reset() { action.value=""; actor.value=""; fromAt.value=""; toAt.value=""; void load(true) }
async function exportCsv() {
  exporting.value = true; errorMessage.value = ""
  try {
    const query = new URLSearchParams()
    if (action.value) query.set("action", action.value)
    if (actor.value) query.set("actor", actor.value)
    if (fromAt.value) query.set("from_at", iso(fromAt.value))
    if (toAt.value) query.set("to_at", iso(toAt.value))
    const response = await fetch(`/api/admin/audit-events/export?${query}`, { credentials: "include" })
    if (!response.ok) throw new Error("Unable to export audit events")
    const url = URL.createObjectURL(await response.blob())
    const link = document.createElement("a"); link.href = url; link.download = "audit-events.csv"; link.click(); URL.revokeObjectURL(url)
  } catch (error) { errorMessage.value = error instanceof Error ? error.message : "Unable to export audit events" } finally { exporting.value = false }
}
onMounted(() => void load(true))
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Audit log" />
    <p class="admin-intro">Review security and administration changes.</p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p>
    <section class="panel audit-filter-panel"><div class="panel-heading"><div><h2>Filter audit events</h2><p class="panel-copy">Narrow the timeline by event, user or time range.</p></div><button class="secondary-button" type="button" :disabled="loading || exporting" @click="exportCsv">{{ exporting ? "Exporting…" : "Export CSV" }}</button></div><form class="audit-filters" @submit.prevent="load(true)"><label><span>Action</span><select v-model="action" :disabled="loading || exporting"><option value="">All actions</option><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select></label><label><span>Actor</span><input v-model="actor" placeholder="Search username" :disabled="loading || exporting"></label><label><span>From</span><input v-model="fromAt" type="datetime-local" :disabled="loading || exporting"></label><label><span>To</span><input v-model="toAt" type="datetime-local" :disabled="loading || exporting"></label><div class="row-actions"><button class="primary-button" :disabled="loading || exporting">{{ loading ? "Loading…" : "Apply filters" }}</button><button class="secondary-button" type="button" :disabled="loading || exporting" @click="reset">Reset</button></div></form></section>
    <section class="panel audit-events-panel"><div class="panel-heading"><div><h2>Events</h2><p class="panel-copy">{{ total }} event{{ total === 1 ? "" : "s" }} found.</p></div></div><p v-if="!loading && !events.length" class="empty-state">No audit events match these filters.</p><div v-else class="audit-table" :aria-busy="loading"><div class="audit-head"><span>Timestamp</span><span>Actor</span><span>Event</span><span>Target</span></div><article v-for="event in events" :key="event.id" class="audit-row"><span :data-label="'Timestamp'">{{ new Date(event.created_at).toLocaleString() }}</span><strong :data-label="'Actor'">{{ event.actor_username }}</strong><span :data-label="'Event'">{{ actionLabel(event.action) }}</span><span class="audit-target" :data-label="'Target'">{{ event.target_type }} · {{ event.target_label }}</span></article></div><button v-if="events.length < total" class="secondary-button load-more" :disabled="loading" @click="page++; load()">{{ loading ? "Loading…" : "Load more" }}</button></section>
  </main>
</template>

<style scoped>
.audit-filter-panel,.audit-events-panel{margin-top:1.5rem}.audit-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;align-items:end}.audit-filters label{display:grid;gap:.4rem}.audit-filters input,.audit-filters select{min-height:2.5rem}.audit-head,.audit-row{display:grid;grid-template-columns:1.2fr 1fr 1.5fr 1.5fr;gap:1rem;padding:.85rem}.audit-head{color:#94a3b8;font-size:.85rem}.audit-row{border-top:1px solid var(--meshive-border);border-radius:.4rem}.audit-row:hover{background:rgb(8 47 73 / 24%)}.audit-target{overflow-wrap:anywhere}.load-more{margin-top:1rem}@media(max-width:700px){.audit-filters{grid-template-columns:1fr}.audit-head{display:none}.audit-row{grid-template-columns:1fr;gap:.35rem}.audit-row [data-label]::before{content:attr(data-label);display:block;color:#94a3b8;font-size:.75rem;font-weight:600}.audit-row strong{display:block}}</style>
