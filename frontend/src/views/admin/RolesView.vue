<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";

import { ApiError, apiRequest } from "../../api";
import AdminHeader from "../../components/AdminHeader.vue";
import { presentPermission } from "../../constants/permissions";

interface Role {
  id: number;
  name: string;
  description: string | null;
  is_system: boolean;
  is_superuser: boolean;
  permission_keys: string[];
  user_count: number;
}
const roles = ref<Role[]>([]);
const permissionKeys = ref<string[]>([]);
const selectedId = ref<number | null>(null);
const errorMessage = ref("");
const successMessage = ref("");
const saving = ref(false);
const form = reactive({
  name: "",
  description: "",
  permission_keys: [] as string[],
});
const selected = computed(
  () => roles.value.find((role) => role.id === selectedId.value) ?? null,
);
const displayedPermissions = computed(() =>
  (selected.value?.permission_keys ?? form.permission_keys).map(
    presentPermission,
  ),
);
const groupedPermissions = computed(() => {
  const groups = new Map<string, ReturnType<typeof presentPermission>[]>();
  for (const key of permissionKeys.value) {
    const permission = presentPermission(key);
    groups.set(permission.group, [
      ...(groups.get(permission.group) ?? []),
      permission,
    ]);
  }
  return [...groups.entries()];
});
function showError(error: unknown) {
  errorMessage.value =
    error instanceof ApiError
      ? error.message
      : "The request could not be completed";
}
function selectRole(role: Role | null) {
  selectedId.value = role?.id ?? null;
  Object.assign(form, {
    name: role?.name ?? "",
    description: role?.description ?? "",
    permission_keys: [...(role?.permission_keys ?? [])],
  });
}
async function load() {
  [roles.value, permissionKeys.value] = await Promise.all([
    apiRequest<Role[]>("/api/admin/roles"),
    apiRequest<string[]>("/api/admin/permissions"),
  ]);
}
async function save() {
  errorMessage.value = "";
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      description: form.description || null,
      permission_keys: form.permission_keys,
    };
    const role = selected.value
      ? await apiRequest<Role>(`/api/admin/roles/${selected.value.id}`, {
          method: "PUT",
          body: JSON.stringify(payload),
        })
      : await apiRequest<Role>("/api/admin/roles", {
          method: "POST",
          body: JSON.stringify(payload),
        });
    await load();
    selectRole(roles.value.find((item) => item.id === role.id) ?? null);
    successMessage.value = "Role saved successfully.";
  } catch (error) {
    showError(error);
  } finally {
    saving.value = false;
  }
}
async function deleteRole() {
  if (
    !selected.value ||
    !window.confirm(`Delete role "${selected.value.name}"?`)
  )
    return;
  errorMessage.value = "";
  saving.value = true;
  try {
    await apiRequest(`/api/admin/roles/${selected.value.id}`, {
      method: "DELETE",
    });
    await load();
    selectRole(null);
    successMessage.value = "Role deleted successfully.";
  } catch (error) {
    showError(error);
  } finally {
    saving.value = false;
  }
}
onMounted(() => {
  load().catch(showError);
});
</script>

<template>
  <main class="admin-shell">
    <AdminHeader title="Roles" />
    <p class="admin-intro">
      System roles are fixed and read-only. Create custom roles to combine
      permissions.
    </p>
    <p v-if="errorMessage" class="form-error error-panel" role="alert">
      {{ errorMessage }}
    </p>
    <p v-if="successMessage" class="success-panel" role="status">
      {{ successMessage }}
    </p>
    <div class="management-layout">
      <section class="panel role-list-panel">
        <div class="panel-heading">
          <div>
            <h2>Roles</h2>
            <p class="panel-copy">Select a role to inspect its permissions.</p>
          </div>
          <button
            class="secondary-button new-role-button"
            type="button"
            @click="selectRole(null)"
          >
            New custom role
          </button>
        </div>
        <button
          v-for="role in roles"
          :key="role.id"
          class="role-card"
          :class="{ selected: selected?.id === role.id }"
          type="button"
          @click="selectRole(role)"
        >
          <span
            ><strong>{{ role.name }}</strong
            ><small>{{ role.description || "No description" }}</small></span
          ><span class="role-card-meta"
            ><span
              class="status-badge"
              :class="role.is_system ? 'system' : 'custom'"
              >{{ role.is_system ? "System role" : "Custom role" }}</span
            ><small
              >{{ role.user_count }} users ·
              {{ role.permission_keys.length }} permissions</small
            ></span
          >
        </button>
      </section>
      <section class="panel role-editor-panel">
        <template v-if="selected?.is_system"
          ><div class="panel-heading">
            <div>
              <h2>{{ selected.name }}</h2>
              <p class="panel-copy">System roles are read-only.</p>
            </div>
            <span class="status-badge system">System role</span>
          </div>
          <p>{{ selected.description }}</p>
          <div class="permission-read-list">
            <article
              v-for="permission in displayedPermissions"
              :key="permission.key"
              class="permission-item"
            >
              <span class="permission-check" aria-hidden="true">✓</span
              ><span
                ><strong>{{ permission.label }}</strong
                ><small>{{ permission.description }}</small></span
              ><span v-if="permission.administrative" class="permission-scope"
                >Administration</span
              >
            </article>
          </div></template
        >
        <form v-else class="role-form" @submit.prevent="save">
          <div class="panel-heading">
            <div>
              <h2>{{ selected ? "Edit custom role" : "New custom role" }}</h2>
              <p class="panel-copy">
                Choose only the permissions this role needs.
              </p>
            </div>
            <span class="status-badge custom">Custom role</span>
          </div>
          <div class="role-form-fields">
            <label
              ><span>Name</span
              ><input v-model="form.name" required maxlength="80" /></label
            ><label
              ><span>Description</span
              ><textarea v-model="form.description" maxlength="2000"></textarea>
            </label>
          </div>
          <div class="permission-groups">
            <fieldset
              v-for="[group, permissions] in groupedPermissions"
              :key="group"
              class="permission-group"
            >
              <legend>{{ group }}</legend>
              <label
                v-for="permission in permissions"
                :key="permission.key"
                class="permission-choice"
                ><input
                  v-model="form.permission_keys"
                  type="checkbox"
                  :value="permission.key"
                /><span
                  ><strong>{{ permission.label }}</strong
                  ><small>{{ permission.description }}</small></span
                ><em v-if="permission.administrative">Administration</em></label
              >
            </fieldset>
          </div>
          <div class="user-actions">
            <button class="primary-button" :disabled="saving" type="submit">
              {{ saving ? "Saving…" : "Save role" }}</button
            ><button
              v-if="selected"
              class="danger-button"
              :disabled="saving"
              type="button"
              @click="deleteRole"
            >
              Delete role
            </button>
          </div>
        </form>
      </section>
    </div>
  </main>
</template>
