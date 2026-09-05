<script setup lang="ts">
import { onMounted, ref } from "vue"
import { apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface Event { id: number; created_at: string; actor_username: string; action: string; target_type: string; target_label: string }
const events = ref<Event[]>([]); const page = ref(1); const total = ref(0); const action = ref(""); const actor = ref("")
const labels: Record<string, string> = { "role.created": "Role created", "role.updated": "Role updated", "role.deleted": "Role deleted", "user.created": "User created", "user.updated": "User updated", "user.deleted": "User deleted", "user.role_changed": "User role changed", "user.source_access_changed": "User source access changed", "user.status_changed": "User status changed", "user.password_changed": "User password changed", "user.require_password_change_changed": "Password-change requirement changed" }
async function load(reset = false) { if (reset) page.value = 1; const q = new URLSearchParams({ page: String(page.value), page_size: "25" }); if (action.value) q.set("action", action.value); if (actor.value) q.set("actor", actor.value); const data = await apiRequest<{items: Event[]; total: number}>(`/api/admin/audit-events?${q}`); events.value = reset ? data.items : [...events.value, ...data.items]; total.value = data.total }
onMounted(() => load(true))
</script>
<template><main class="admin-shell"><AdminHeader title="Audit log" /><p class="admin-intro">Review security and administration changes.</p><section class="panel"><form class="filter-bar" @submit.prevent="load(true)"><label>Action<input v-model="action" placeholder="role.updated"></label><label>Actor<input v-model="actor" placeholder="Username"></label><button class="secondary-button">Filter</button></form><p v-if="!events.length" class="muted">No audit events match these filters.</p><div v-else class="audit-list"><article v-for="event in events" :key="event.id" class="source-row"><span>{{ new Date(event.created_at).toLocaleString() }}</span><strong>{{ event.actor_username }}</strong><span>{{ labels[event.action] ?? event.action.replaceAll('.', ' ') }}</span><span>{{ event.target_type }}: {{ event.target_label }}</span></article></div><button v-if="events.length < total" class="secondary-button" @click="page++; load()">Load more</button></section></main></template>
