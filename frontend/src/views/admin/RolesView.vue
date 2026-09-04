<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"

import { ApiError, apiRequest } from "../../api"
import AdminHeader from "../../components/AdminHeader.vue"

interface Role {
  id: number
  name: string
  description: string | null
  is_system: boolean
  is_superuser: boolean
  permission_keys: string[]
  user_count: number
}

const permissionGroups: Record<string, string> = {
  "catalogue.view": "Catalogue", "catalogue.view_maintenance": "Catalogue",
  "archives.view_entries": "Catalogue", "archives.download": "Catalogue",
  "models.primary_image": "Models", "models.tags": "Models", "models.rescan": "Models",
  "models.rebuild_images": "Models", "models.reset_images": "Models", "models.delete_missing": "Models",
  "scans.view": "Scans", "scans.start": "Scans", "scans.control": "Scans",
  "metadata.manage": "Metadata", "tags.manage": "Metadata", "tag_rules.manage": "Metadata",
  "sources.manage": "Sources", "diagnostics.view": "Sources", "backups.manage": "Backups",
  "users.manage": "Access management", "roles.manage": "Access management", "audit.view": "Access management",
  "favorites.manage": "Catalogue",
}

const roles = ref<Role[]>([])
const permissionKeys = ref<string[]>([])
const selectedId = ref<number | null>(null)
const errorMessage = ref("")
const successMessage = ref("")
const saving = ref(false)
const form = reactive({ name: "", description: "", permission_keys: [] as string[] })
const selected = computed(() => roles.value.find((role) => role.id === selectedId.value) ?? null)
const groupedPermissions = computed(() => {
  const groups = new Map<string, string[]>()
  for (const key of permissionKeys.value) {
    const group = permissionGroups[key] ?? "Other"
    groups.set(group, [...(groups.get(group) ?? []), key])
  }
  return [...groups.entries()]
})

function showError(error: unknown) {
  errorMessage.value = error instanceof ApiError ? error.message : "The request could not be completed"
}
function selectRole(role: Role | null) {
  selectedId.value = role?.id ?? null
  Object.assign(form, {
    name: role?.name ?? "", description: role?.description ?? "",
    permission_keys: [...(role?.permission_keys ?? [])],
  })
}
async function load() {
  [roles.value, permissionKeys.value] = await Promise.all([
    apiRequest<Role[]>("/api/admin/roles"), apiRequest<string[]>("/api/admin/permissions"),
  ])
}
async function save() {
  errorMessage.value = ""; successMessage.value = ""; saving.value = true
  try {
    const payload = { name: form.name, description: form.description || null, permission_keys: form.permission_keys }
    const role = selected.value
      ? await apiRequest<Role>(`/api/admin/roles/${selected.value.id}`, { method: "PUT", body: JSON.stringify(payload) })
      : await apiRequest<Role>("/api/admin/roles", { method: "POST", body: JSON.stringify(payload) })
    await load(); selectRole(roles.value.find((item) => item.id === role.id) ?? null)
    successMessage.value = "Role saved successfully."
  } catch (error) { showError(error) } finally { saving.value = false }
}
async function deleteRole() {
  if (!selected.value || !window.confirm(`Delete role "${selected.value.name}"?`)) return
  errorMessage.value = ""; saving.value = true
  try { await apiRequest(`/api/admin/roles/${selected.value.id}`, { method: "DELETE" }); await load(); selectRole(null); successMessage.value = "Role deleted successfully." } catch (error) { showError(error) } finally { saving.value = false }
}
onMounted(() => { load().catch(showError) })
</script>

<template>
  <main class="admin-shell"><AdminHeader title="Roles" />
    <p class="admin-intro">System roles are fixed. Create custom roles to combine permissions.</p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">{{ errorMessage }}</p><p v-if="successMessage" class="success-panel" role="status">{{ successMessage }}</p>
    <div class="admin-user-list"><section class="panel"><h2>Roles</h2><button class="secondary-button" type="button" @click="selectRole(null)">New custom role</button>
      <article v-for="role in roles" :key="role.id" class="admin-user-card"><button class="text-button" type="button" @click="selectRole(role)">{{ role.name }}</button><p>{{ role.description || "No description" }}</p><small>{{ role.is_system ? "System role" : "Custom role" }} · {{ role.permission_keys.length }} permissions · {{ role.user_count }} users</small></article>
    </section>
    <section class="panel"><h2>{{ selected ? selected.name : "New custom role" }}</h2><p v-if="selected?.is_system">System roles are read-only.</p>
      <form v-else class="user-form" @submit.prevent="save"><label><span>Name</span><input v-model="form.name" required maxlength="80"></label><label><span>Description</span><textarea v-model="form.description" maxlength="2000"></textarea></label>
        <fieldset v-for="[group, keys] in groupedPermissions" :key="group"><legend>{{ group }}</legend><label v-for="key in keys" :key="key" class="inline-check"><input v-model="form.permission_keys" type="checkbox" :value="key"> {{ key }}</label></fieldset>
        <button class="primary-button" :disabled="saving" type="submit">{{ saving ? "Saving…" : "Save role" }}</button><button v-if="selected" class="danger-button" :disabled="saving" type="button" @click="deleteRole">Delete role</button>
      </form></section></div>
  </main>
</template>
